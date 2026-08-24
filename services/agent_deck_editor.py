# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Agentic Whole-Deck Editor — the "Claude on PowerPoint" edit engine.

This module replaces the old single-page / multi-page scope-selected edit flow
with a single agentic path: the ENTIRE deck (every slide / every page, plus
deck-level metadata — style, header/footer, slide numbers, goal) is sent to the
LLM in ONE shot together with the user's chat message. The model decides — on
its own — what to change and returns a list of OPERATIONS:

    edit_slide / add_slide / delete_slide / duplicate_slide / reorder_slides /
    update_style / update_header_footer / update_slide_numbers

The frontend applies the operations to its local deck state. No scope radio, no
"this slide vs all slides" toggle — the model auto-detects intent and target
from the message and the deck it can see.

Works for BOTH presentations (16:9) and printables (A4) via CanvasConfig — the
only difference is canvas dimensions and the noun ("slide" vs "page").

Design rules (consistent with the rest of the codebase):
- Fail loud: a malformed LLM plan raises / yields an error event, never a silent
  no-op that looks like success.
- Reuses validate_element_positions + _fix_numbered_step_numbers from the
  existing edit_orchestrator so geometry stays in-bounds.
- Pins GLM-5.1 through the edit_orchestrator.llm_call wrapper.
"""

from typing import Dict, Any, Optional, List, Tuple
import copy
import logging
import json
import asyncio
import re
import uuid

from services.edit_orchestrator import (
    CanvasConfig,
    PRESENTATION_CANVAS,
    PRINTABLE_CANVAS,
    validate_element_positions,
    _fix_numbered_step_numbers,
    extract_json_from_response,
    retrieve_vault_context,
    llm_call,
)

logger = logging.getLogger(__name__)

# NOTE: pure chat replies go in `chat_message`, NOT an operation — there is
# deliberately no "message" op. Allowed mutation kinds = MUTATION_TOOLS; both
# the loop and the one-shot path dispatch through _apply_op_to_deck.

# ─── Review-turn detection ───────────────────────────────────────────────────
# "review it / any suggestions?" turns must NOT mutate — the agent presents
# findings and the user approves before anything changes. The system prompt asks
# for this, but prompt-only compliance is unreliable, so the loop also HARD
# BLOCKS mutation tools on turns that read as review-only. A turn is review-only
# when it carries a review/critique/suggest signal AND no explicit edit/approval
# verb ("review the titles and fix them" still edits directly).
_REVIEW_SIGNAL_RE = re.compile(
    r"\b(review|critique|criticise|criticize|feedback|assess|evaluate|audit|"
    r"suggest(?:ion)?s?|recommend(?:ation)?s?|what\s+(?:can|could|should)\b.*\bimprov\w*|"
    r"how\s+can\s+i\s+improve|any\s+improvements?|rate\s+(?:my|this|the))\b",
    re.IGNORECASE,
)
_EDIT_SIGNAL_RE = re.compile(
    r"\b(apply|go\s+ahead|do\s+it|proceed|implement|execute|fix|correct|change|update|"
    r"edit|add|remove|delete|rewrite|redesign|rework|make|set|turn|translate|replace|"
    r"reorder|move|resize|recolor|shorten|expand)\b",
    re.IGNORECASE,
)


def _is_review_only_request(instruction: str) -> bool:
    text = instruction or ""
    return bool(_REVIEW_SIGNAL_RE.search(text)) and not bool(_EDIT_SIGNAL_RE.search(text))


def _is_review_followup(instruction: str, chat_history: Optional[List[Dict[str, Any]]]) -> bool:
    """The turn AFTER the agent asked "where should I focus the review?" — the
    user's short answer ("Design & layout") carries no review keyword, but the
    turn is still a review and must not mutate."""
    if not chat_history:
        return False
    last_assistant = next(
        (m for m in reversed(chat_history) if (m.get("role") or "") == "assistant"), None,
    )
    if not last_assistant:
        return False
    last_text = last_assistant.get("text") or ""
    # Require an explicit review/focus question — a generic edit clarification
    # that merely mentions "suggestions" must NOT lock the next turn into
    # review mode (it would block the edit the user is about to confirm).
    if "?" not in last_text or not re.search(r"\b(review|focus)\b", last_text, re.IGNORECASE):
        return False
    text = instruction or ""
    return len(text) < 80 and not _EDIT_SIGNAL_RE.search(text)


# ═══════════════════════════════════════════════════════════════════════════
# Deck → prompt serialization
# ═══════════════════════════════════════════════════════════════════════════

def _noun(canvas: CanvasConfig) -> Tuple[str, str]:
    """Return (singular, plural) noun for the surface."""
    return ("slide", "slides") if canvas.content_type == "presentation" else ("page", "pages")


# Keys on an element that can carry raw image data / links.
_IMG_SRC_KEYS = ("src", "backgroundImage", "backgroundImageUrl", "imageUrl", "url")


def _safe_img_src(value: Any) -> Any:
    """Defensive guard so NO image bytes or links ever reach the LLM. The frontend
    is supposed to replace image srcs with markers ({{UserMedia_*}} / {{IMG_*}})
    before sending, but if a raw base64 data-URI or http(s) URL slips through we
    redact it to a placeholder (also saves huge token bloat). Markers pass through
    untouched so the frontend can still restore the real image after the edit."""
    if not isinstance(value, str):
        return value
    s = value.strip()
    if s.startswith("{{") and s.endswith("}}"):
        return value  # already a marker
    if s.startswith("data:") or s.startswith("http://") or s.startswith("https://"):
        logger.warning("🖼️ [AGENT] redacted a non-marker image src before prompting (frontend should markerize)")
        return "{{IMG_PLACEHOLDER}}"
    return value


def _compact_slide(slide: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Project a slide down to the fields the model needs to reason + edit.

    Keeps element ids and full geometry/content so the model can return a clean
    replacement element list. Image src values are expected to already be
    markers ({{UserMedia_*}} / {{IMG_*}}); any raw base64/URL that slips through
    is redacted (see _safe_img_src) so no image data ever reaches the LLM.
    """
    elements = slide.get("elements", []) or []
    compact_elements = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        # Pass the element through largely intact — the model needs to be able
        # to reproduce it. Drop only bulky/runtime-only keys.
        ce = {k: v for k, v in el.items() if k not in ("_fabricRef", "thumbnail")}
        for _k in _IMG_SRC_KEYS:
            if _k in ce:
                ce[_k] = _safe_img_src(ce[_k])
        compact_elements.append(ce)

    return {
        "index": index,
        "id": slide.get("id"),
        "title": slide.get("title", "") or "",
        "outline": slide.get("outline") or slide.get("sectionTopic") or "",
        "layout": slide.get("layout", "content"),
        "backgroundColor": slide.get("backgroundColor", "#ffffff"),
        "hidden": bool(slide.get("hidden", False)),
        "elements": compact_elements,
    }


def _build_deck_json(slides: List[Dict[str, Any]]) -> str:
    """Serialize the whole deck to JSON for the prompt."""
    compact = [_compact_slide(s, i) for i, s in enumerate(slides)]
    return json.dumps(compact, ensure_ascii=False)


def _summarize_history(chat_history: Optional[List[Dict[str, Any]]], limit: int = 6) -> str:
    # Keep history minimal — it sits in the volatile prompt suffix (uncached,
    # re-sent every round). 6 = last ~3 exchanges: enough for the review→approve
    # flow (agent re-reads its own review on "apply") and short follow-ups, no more.
    if not chat_history:
        return ""
    parts = []
    for m in chat_history[-limit:]:
        role = (m.get("role") or m.get("actionType") or "user").strip()
        role = "User" if role in ("user",) else "Assistant"
        text = (m.get("text") or m.get("content") or "").strip()
        if text:
            # Assistant turns may carry a full deck review the user is about to
            # approve — keep them long enough to act on ("yes, do it").
            cap = 1500 if role == "Assistant" else 500
            parts.append(f"{role}: {text[:cap]}")
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# System prompt
# ═══════════════════════════════════════════════════════════════════════════

def build_agent_system_prompt(canvas: CanvasConfig) -> str:
    singular, plural = _noun(canvas)
    w, h = canvas.width, canvas.height

    return f"""You are an expert {singular} editor working INSIDE a live {canvas.content_type} editor — \
think of yourself like Claude editing a PowerPoint/document directly in chat. You are given the \
ENTIRE document (every {singular}) plus its deck-level settings (style, header/footer, {singular} numbers, goal), \
and a chat message from the user. You decide what to change and return a precise list of OPERATIONS.

CANVAS: every {singular} is {w}×{h} px ({canvas.format_label}). Keep every element fully inside \
0..{w} (x) and 0..{h} (y). Elements must not overflow the canvas or heavily overlap.

═══ HOW TO THINK ═══
1. Read the user's message and the document. Auto-detect intent and TARGET — do NOT ask which {singular}.
   • "this {singular}", "here", "current" → the {singular} the user is viewing (marked CURRENT below).
   • "all {plural}", "every {singular}", "the whole deck", "throughout" → apply to ALL {plural}.
   • A topic/section reference (e.g. "the pricing {singular}") → the matching {singular}(s) by content.
   • "add/new {singular}", "insert a {singular} about X" → add_slide.
   • "delete/remove this {singular}" / "drop the X {singular}" → delete_slide.
   • "move/reorder", "make X the first {singular}" → reorder_slides.
   • Style/theme/font/color for the whole document → update_style.
   • Header, footer, logo, page/{singular} numbers → update_header_footer / update_slide_numbers.
   • A pure question / greeting with no edit → return an empty operations list and answer in chat_message.
2. Only emit operations for things you ACTUALLY change. Never re-emit unchanged {plural}.
3. Be surgical but complete: when you edit a {singular}, return its FULL new element list.

═══ OPERATIONS (return as JSON) ═══
edit_slide — replace the content of an existing {singular}:
  {{"op":"edit_slide","slide_id":"<id>","title":"<opt>","outline":"<opt>","backgroundColor":"<opt>",
    "elements":[ ...FULL new element list for this {singular}... ]}}
  • Preserve element "id" for elements you keep so the canvas can diff. New elements: invent a unique id.
  • Preserve user media EXACTLY: any element whose src starts with "{{{{UserMedia_" — keep src + position unchanged.
  • Preserve "video" elements unchanged (you cannot generate video).
  • For images you WANT (re)generated, use an element of type "image_placeholder" with an "imageDescription"
    string (and x/y/width/height). The app generates the actual picture. Do not invent base64/URLs.
  • For charts use type "chart" with a Chart.js "chartConfig" ({{type,data,options}}).

add_slide — create a brand-new {singular}:
  {{"op":"add_slide","after_slide_id":"<id or null>","position":"end|start",
    "title":"...","outline":"...","layout":"content","backgroundColor":"#ffffff","elements":[ ... ]}}
  • Place it after after_slide_id when given; else honor position; default = after CURRENT.

delete_slide:        {{"op":"delete_slide","slide_id":"<id>"}}
duplicate_slide:     {{"op":"duplicate_slide","slide_id":"<id>"}}
reorder_slides:      {{"op":"reorder_slides","order":["<id>","<id>", ...]}}   (every existing id, new order)
update_style:        {{"op":"update_style","style":{{ ...only changed keys... }}}}
   • style keys: fontFamily, textPrimary, textSecondary, accentColor, {canvas.bg_key}
update_header_footer:{{"op":"update_header_footer","header_footer":{{
     "show_header":true,"header_text":"...","show_footer":true,"footer_text":"...",
     "show_logo":false,"align":"center","color":"#64748b","font_size":12 }}}}
update_slide_numbers:{{"op":"update_slide_numbers","slide_numbers":{{
     "show":true,"format":"n_of_total","position":"bottom-right","prefix":"",
     "color":"#94a3b8","font_size":12,"start_at":1 }}}}
   • format ∈ "n" | "n_of_total" | "{singular}_n". position ∈ bottom-right|bottom-center|bottom-left.

═══ ELEMENT SHAPES (reference) ═══
text:   {{"id","type":"text","x","y","width","height","content","fontSize","fontWeight","fill","textAlign"}}
card:   {{"id","type":"card","x","y","width","height","title","description","iconName","backgroundColor"}}
icon:   {{"id","type":"icon","x","y","width","height","iconName","fill"}}
shape:  {{"id","type":"shape","x","y","width","height","shapeType","fill"}}
chart:  {{"id","type":"chart","x","y","width","height","chartConfig":{{...}}}}
image:  {{"id","type":"image_placeholder","x","y","width","height","imageDescription","imageType":"photo"}}
numbered_step: {{"id","type":"numbered_step","x","y","width","height","number","label"}}

═══ OUTPUT — STRICT JSON, NOTHING ELSE ═══
{{"chat_message":"<one short, friendly sentence describing what you did or answering the user>",
  "operations":[ ...zero or more operations... ]}}

Never wrap the JSON in prose or markdown fences. If nothing should change, return an empty operations \
list and put your answer in chat_message. Do not hallucinate data — if the user asks for data you don't \
have and no vault context is provided, say so in chat_message instead of inventing numbers."""


def build_agent_user_prompt(
    canvas: CanvasConfig,
    instruction: str,
    slides: List[Dict[str, Any]],
    current_index: int,
    deck_meta: Dict[str, Any],
    chat_history: Optional[List[Dict[str, Any]]],
    vault_context: str = "",
) -> str:
    singular, plural = _noun(canvas)
    deck_json = _build_deck_json(slides)
    history = _summarize_history(chat_history)

    style = deck_meta.get("style") or {}
    header_footer = deck_meta.get("header_footer") or {}
    slide_numbers = deck_meta.get("slide_numbers") or {}
    goal = deck_meta.get("goal") or ""
    doc_type = deck_meta.get("content_type") or deck_meta.get("presentation_type") or "informative"

    current_marker = ""
    if 0 <= current_index < len(slides):
        cid = slides[current_index].get("id")
        current_marker = f'The user is currently viewing {singular} index {current_index} (id="{cid}").'

    parts = [
        f"DOCUMENT GOAL: {goal or 'N/A'}",
        f"DOCUMENT TYPE: {doc_type}",
        f"TOTAL {plural.upper()}: {len(slides)}",
        current_marker,
        "",
        f"DECK STYLE: {json.dumps(style, ensure_ascii=False)}",
        f"HEADER/FOOTER: {json.dumps(header_footer, ensure_ascii=False)}",
        f"{singular.upper()} NUMBERS: {json.dumps(slide_numbers, ensure_ascii=False)}",
    ]
    if vault_context:
        parts += ["", "GROUNDING CONTEXT (use ONLY for facts/data — do not copy verbatim):", vault_context[:6000]]
    if history:
        parts += ["", "RECENT CONVERSATION:", history]
    parts += [
        "",
        f"FULL DOCUMENT ({plural}, in order):",
        deck_json,
        "",
        f'USER MESSAGE: "{instruction}"',
        "",
        "Return the strict JSON object now.",
    ]
    return "\n".join(p for p in parts if p is not None)


# ═══════════════════════════════════════════════════════════════════════════
# Plan parsing
# ═══════════════════════════════════════════════════════════════════════════

def _parse_plan(raw_text: str) -> Dict[str, Any]:
    """Parse the LLM response into {chat_message, operations}. Raises on garbage."""
    cleaned = extract_json_from_response(raw_text or "")
    data = json.loads(cleaned)  # raises JSONDecodeError on failure (caller handles)
    if isinstance(data, list):
        data = {"operations": data, "chat_message": ""}
    if not isinstance(data, dict):
        raise ValueError("plan is not an object")
    ops = data.get("operations") or data.get("ops") or []
    if not isinstance(ops, list):
        ops = []
    return {"chat_message": data.get("chat_message") or data.get("message") or "", "operations": ops}


# ═══════════════════════════════════════════════════════════════════════════
# Core entrypoints
# ═══════════════════════════════════════════════════════════════════════════

async def agent_edit_deck(
    instruction: str,
    slides: List[Dict[str, Any]],
    user_id: str,
    canvas: CanvasConfig,
    current_index: int = 0,
    deck_meta: Optional[Dict[str, Any]] = None,
    chat_history: Optional[List[Dict[str, Any]]] = None,
    folder_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Non-streaming agentic deck edit. Returns {success, chat_message, operations}."""
    deck_meta = deck_meta or {}
    singular, _ = _noun(canvas)

    if not instruction or not instruction.strip():
        return {"success": True, "chat_message": "Tell me what you'd like to change.", "operations": []}
    if not slides:
        return {"success": True, "chat_message": f"There are no {singular}s to edit yet.", "operations": []}

    # Optional vault grounding — only when the caller passed folders.
    vault_context = ""
    if folder_ids:
        try:
            vault_context = await retrieve_vault_context(user_id, instruction, folder_ids, top_k=3)
        except Exception as e:
            logger.warning(f"🔍 [AGENT-EDIT] vault retrieval failed (continuing without): {e}")

    system_prompt = build_agent_system_prompt(canvas)
    user_prompt = build_agent_user_prompt(
        canvas, instruction, slides, current_index, deck_meta, chat_history, vault_context,
    )

    logger.info(
        f"🤖 [AGENT-EDIT-{canvas.content_type}] {len(slides)} {singular}s | msg='{instruction[:60]}'"
    )

    # 128K output (context-window bounded) + low reasoning — glm-5.1 reasoning can
    # eat 15-25K tokens before the JSON and a whole-deck plan is large; 50K truncated.
    raw = await asyncio.to_thread(
        llm_call,
        system_prompt,
        user_prompt,
        user_id=user_id,
        max_tokens=128000,
        temperature=0.3,
        json_mode=True,
        reasoning_effort="low",
    )

    try:
        plan = _parse_plan(raw)
    except Exception as e:
        logger.error(f"❌ [AGENT-EDIT] unparseable plan: {e} | raw[:300]={str(raw)[:300]}")
        # Fail loud to the caller — do NOT pretend success.
        return {
            "success": False,
            "error": "plan_parse_failed",
            "chat_message": "I couldn't structure that change. Please rephrase and try again.",
            "operations": [],
        }

    # Apply the plan through the SAME stateful engine the loop uses
    # (_apply_op_to_deck on a deck copy) so multi-op plans stay consistent:
    # deletes don't reappear in a later reorder, added/duplicated slides get
    # their server-stamped ids, and clamped geometry is what gets streamed.
    deck_copy = copy.deepcopy(slides)
    meta_copy = dict(deck_meta)
    added_sigs: set = set()  # de-dupe repeated identical add_slide ops in one plan
    operations: List[Dict[str, Any]] = []
    for raw_op in plan["operations"]:
        if not isinstance(raw_op, dict) or raw_op.get("op") not in MUTATION_TOOLS:
            logger.warning(f"🧩 [AGENT-EDIT] dropping unknown op: {raw_op.get('op') if isinstance(raw_op, dict) else raw_op}")
            continue
        if raw_op.get("op") == "add_slide":
            sig = _add_slide_sig(raw_op)
            if sig in added_sigs:
                logger.info("🧩 [AGENT-EDIT] dropping duplicate add_slide (same content this turn)")
                continue
            added_sigs.add(sig)
        cleaned = _apply_op_to_deck(dict(raw_op), deck_copy, meta_copy, canvas, current_index)
        if cleaned is not None:
            operations.append(cleaned)

    # Review-only turns never mutate — drop any ops the model emitted anyway,
    # and say so instead of relaying a message that claims edits were made.
    chat_message = plan["chat_message"]
    if _is_review_only_request(instruction) and operations:
        logger.info(f"🔍 [AGENT-EDIT] review-only turn — dropping {len(operations)} op(s)")
        operations = []
        chat_message = (chat_message + " (No changes were applied — this was a review; "
                        "say 'apply' to make the edits.)") if chat_message else ""
    logger.info(f"✅ [AGENT-EDIT] {len(operations)} operation(s): {[o.get('op') for o in operations]}")
    return {
        "success": True,
        "chat_message": chat_message or _default_message(operations, canvas),
        "operations": operations,
    }


def _default_message(operations: List[Dict[str, Any]], canvas: CanvasConfig) -> str:
    singular, plural = _noun(canvas)
    if not operations:
        return "No changes were needed."
    counts: Dict[str, int] = {}
    for o in operations:
        counts[o.get("op")] = counts.get(o.get("op"), 0) + 1
    bits = []
    label = {
        "edit_slide": f"edited {{n}} {singular}(s)",
        "update_elements": f"updated {{n}} {singular}(s)",
        "remove_elements": "removed elements",
        "add_slide": f"added {{n}} {singular}(s)",
        "delete_slide": f"removed {{n}} {singular}(s)",
        "duplicate_slide": f"duplicated {{n}} {singular}(s)",
        "reorder_slides": f"reordered the {plural}",
        "update_style": "updated the theme",
        "update_header_footer": "updated the header/footer",
        "update_slide_numbers": f"updated {singular} numbers",
    }
    for op, n in counts.items():
        tmpl = label.get(op, op)
        bits.append(tmpl.format(n=n) if "{n}" in tmpl else tmpl)
    return "Done — " + ", ".join(bits) + "."


def _sse(event: Dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def agent_edit_deck_streaming(
    instruction: str,
    slides: List[Dict[str, Any]],
    user_id: str,
    canvas: CanvasConfig,
    current_index: int = 0,
    deck_meta: Optional[Dict[str, Any]] = None,
    chat_history: Optional[List[Dict[str, Any]]] = None,
    folder_ids: Optional[List[str]] = None,
):
    """SSE-streaming agentic deck edit. Yields status events then a single
    `operations` event the frontend applies."""
    singular, _ = _noun(canvas)
    yield _sse({"type": "status", "stage": "thinking", "message": f"Reading your {len(slides)} {singular}(s)…"})

    try:
        result = await agent_edit_deck(
            instruction=instruction,
            slides=slides,
            user_id=user_id,
            canvas=canvas,
            current_index=current_index,
            deck_meta=deck_meta,
            chat_history=chat_history,
            folder_ids=folder_ids,
        )
    except Exception as e:
        from fastapi import HTTPException
        detail = str(getattr(e, "detail", "")) or str(e)
        if "insufficient_credits" in detail.lower() or "negative balance" in detail.lower():
            yield _sse({"type": "error", "status_code": 402, "message": "Insufficient credits."})
            return
        logger.error(f"❌ [AGENT-EDIT-STREAM] {e}")
        yield _sse({"type": "error", "message": detail or "Edit failed."})
        return

    if not result.get("success"):
        yield _sse({"type": "error", "message": result.get("chat_message", "Edit failed.")})
        return

    yield _sse({
        "type": "operations",
        "chat_message": result["chat_message"],
        "operations": result["operations"],
    })
    yield _sse({"type": "complete", "operation_count": len(result["operations"])})


# ═══════════════════════════════════════════════════════════════════════════
# AGENT LOOP — a real multi-round agent (read tools + mutation tools +
# ask_user / finish) instead of the one-shot planner above.
#
# Each round the model returns {reasoning, actions:[{tool,args}]} as strict JSON
# (ReAct-over-JSON-mode — robust with GLM, which leaks native tool-calls). Read
# tools (inspect_slides / search_context) produce observations and the loop
# continues; mutation tools are applied to a server-side deck copy AND streamed
# to the frontend live; ask_user / finish end the turn. Clarifying questions and
# suggested follow-ups come back as clickable chips in the UI.
# ═══════════════════════════════════════════════════════════════════════════

MAX_ROUNDS = 50  # LLM-round ceiling. The REAL work cap is MAX_TOOL_CALLS (50):
# data-grounded restructures legitimately spend many rounds on vault/internet
# reads before editing (observed live: 6/8 rounds on reads under the old cap of
# 8 → edits never fit). Rounds are cheap now that the prompt prefix caches
# (~62K cached per round), and the anti-spin / anti-churn / read-pressure
# guards terminate unproductive loops long before either ceiling.
# A single whole-deck round can take several MINUTES (glm-5.1 reasoning emitting
# tens of thousands of tokens). Emit a keepalive status this often while the LLM
# runs so the SSE stream never goes silent — otherwise the UI looks frozen and an
# idle proxy can drop the connection before the first real event.
_HEARTBEAT_SECS = 8

READ_TOOLS = {"inspect_slides", "search_context", "list_vault_files", "compute_data", "compute_chart", "search_internet"}
# Total tool-call budget per turn (reads + mutations combined). Rounds are the
# LLM-call ceiling; tool calls are the work ceiling — whichever hits first ends
# the turn gracefully.
MAX_TOOL_CALLS = 50
MUTATION_TOOLS = {
    "edit_slide", "update_elements", "remove_elements",
    "add_slide", "delete_slide", "duplicate_slide",
    "reorder_slides", "update_style", "update_header_footer", "update_slide_numbers",
}
TERMINAL_TOOLS = {"ask_user", "finish"}
# Tools that rewrite a slide's CONTENT/layout. Re-emitting one of these against a
# slide already edited THIS turn is the "keeps updating the same slide" churn:
# the model can't see the rendered canvas, judges the JSON geometry "still off",
# and edits again every round. We let the first edit through, then finish.
CONTENT_EDIT_TOOLS = {"edit_slide", "update_elements", "remove_elements"}


def build_loop_system_prompt(canvas: CanvasConfig) -> str:
    singular, plural = _noun(canvas)
    w, h = canvas.width, canvas.height
    return f"""You are an expert {singular} editor agent working INSIDE a live {canvas.content_type} editor \
— like Claude editing PowerPoint directly in chat. You work in ROUNDS, calling tools, until the task is done.

CANVAS: every {singular} is {w}×{h}px ({canvas.format_label}). Keep elements inside 0..{w} (x), 0..{h} (y).

You are given the FULL DOCUMENT every round — every {singular} with every element, complete (it reflects all \
edits applied so far). You therefore have everything you need to edit precisely; you do NOT need inspect_slides \
(it exists only as a fallback). Never edit from memory — edit from the FULL DOCUMENT in this prompt.

═══ HOW TO WORK ═══
- Each round, return ONE JSON object: {{"reasoning":"<short>","actions":[ {{"tool":"<name>","args":{{...}}}}, ... ]}}
- You may batch several mutation actions in one round. After read tools you'll get observations and another round.
- EDIT FROM THE FULL DOCUMENT: the complete element list of every {singular} is already in this prompt — never \
rewrite a {singular} from a partial view (you'd lose content). Do NOT call inspect_slides; you already have it all.
- BE EFFICIENT: inspect ALL the {plural} you plan to touch in ONE round, then apply ALL mutations in the next. \
Mutations are applied EXACTLY as you emit them — they cannot silently fail, so NEVER re-inspect to "verify" your \
own edits. Finish as soon as the work is done.
- MAX 5 {plural} PER ROUND — HARD RULE: never emit more than 5 full-{singular} mutations (edit_slide / add_slide / \
duplicate_slide) in a single round. A larger batch OVERFLOWS your output limit and the ENTIRE round fails, wasting \
minutes. For big restructures work in WAVES: ≤5 {plural} per round across multiple rounds (your 50-tool-call \
budget is ample — e.g. a 19→10 restructure = deletes+wave of 5, then wave of 5, then finish). Small \
update_elements patches don't count toward the 5.
- ONE ADD = ONE {singular}, FINISH IMMEDIATELY: when the user asks to add/insert a {singular}, emit exactly ONE \
add_slide (batch several ONLY if the user explicitly asked for multiple {plural}). The instant your mutation is \
applied you MUST call finish IN THE SAME round — the FULL DOCUMENT and YOUR WORK SO FAR already reflect it. NEVER \
spend another round re-adding, re-editing or "double-checking" a change you already made; re-emitting an add you \
already applied creates DUPLICATE {plural} and is a bug.
- ONE EDIT PASS PER {singular}, THEN FINISH: when you edit or fix a {singular} (layout, geometry, content), make \
ALL your changes to it in ONE round, then call finish IN THE SAME round. You CANNOT see the rendered canvas — only \
this JSON — so do NOT re-edit the same {singular} across rounds trying to "improve" or "verify" the layout; the \
geometry numbers in the FULL DOCUMENT already are the result, and looping edits on one {singular} just churns it \
without ever looking better. Get it right once, then finish.
- IMAGES: ONE imageDescription per turn. Writing a new imageDescription triggers a REAL (paid) image generation \
the user must evaluate — you cannot see the result, so a second rewrite in the same turn is a blind coin-flip \
that wastes a generation, NOT an improvement. Write your single best description, finish, and offer any \
alternative visual concept as a finish suggestion (e.g. "Try a different visual concept for this image") so \
the USER decides whether to generate another take.
- PREFER SURGICAL EDITS: use update_elements / remove_elements for content, color, text and style changes — they \
touch only what you list and cannot break the layout. Use edit_slide (full replacement) ONLY when restructuring \
a {singular}'s layout, and only after fully inspecting it.
- GEOMETRY CARE: never move or resize elements unless the user asked. When you DO place elements, every box must \
satisfy y + height ≤ {h - 30} and x + width ≤ {w - 20}, with no overlaps between boxes.
- TARGET RESOLUTION: "this {singular}" / "here" / "current" → the {singular} marked CURRENTLY VIEWING. A topic \
reference ("the pricing {singular}") → match by title/outline in the overview. "all {plural}" / "the whole deck" → all.
- Header/footer text and {singular} numbers are DECK SETTINGS (update_header_footer / update_slide_numbers) — \
never add them as text elements on individual {plural}, and remove any manual ones you find.
- CLARIFY BEFORE GUESSING: when a request is ambiguous in a way that materially changes the outcome — unclear \
target, unclear focus, multiple plausible readings ("make it shorter" — which {plural}? how short? / "review it" \
— through which lens?) — use ask_user ONCE with quick-reply options, then act on the answer. For clear requests, \
act immediately without asking.
- When finished, call finish with a one-line summary and 2–3 suggested NEW improvements (never "verify/review \
the changes" — they are already applied exactly).

═══ DATA GROUNDING — NEVER INVENT FACTS ═══
This document is typically BUILT FROM the user's vault documents — the vault is the source of truth for its \
facts and figures. Hard rules:
- NEVER invent numbers, statistics, percentages, dates, names, quotes, sources, or domain claims. A fabricated \
figure in an enterprise {canvas.content_type} is worse than a blank one.
- PRESERVE existing data values verbatim unless the user asked to change them or vault data contradicts them. \
Rewording a sentence must not alter the numbers inside it.
- When an edit INTRODUCES or CHANGES factual content: if vault folders are attached, GET THE REAL DATA — \
list_vault_files to see what exists, compute_data for numbers/aggregations from Excel/CSV (actual code \
execution, not estimation), compute_chart for chart data, search_context for facts from documents. If no \
vault is attached or it has nothing relevant, do NOT fabricate — keep existing values, write qualitative \
content without made-up figures, or ask_user for the data.
- Pure styling, layout, structure and tone edits need no vault lookup.

═══ REVIEW WORKFLOW (review / critique / suggest requests) ═══
You are a senior enterprise presentation consultant — you can review through ANY lens the user needs: \
strategic narrative, executive readiness, persuasion & impact, content & wording, data credibility, \
storytelling/flow, design & layout, brand consistency, audience fit, or all of it. The USER'S DIRECTION \
decides the lens, not a fixed checklist.
1. If the user NAMED a focus or angle (even loosely — "for better impact", "from a strategic point of view", \
"is the layout ok?"), review exactly along that direction.
2. If the request is broad with NO direction (just "review it"), use ask_user ONE time to ask where to \
focus, with options such as ["Overall impact — everything", "Strategic story & messaging", "Content & wording", \
"Design & layout"]. Review along whatever they answer.
3. Reviews NEVER mutate. Ground every finding in the REAL document: cite {singular} numbers, quote actual \
text when wording is the issue, and propose concrete improvements (rewrites, restructures, additions) the \
user could approve. Decide for yourself whether vault grounding (search_context) would strengthen the \
review — e.g. fact-checking figures against source documents.
4. Call finish: summary = your review (as many findings as it deserves); suggestions = actionable next \
steps, including "Apply all suggested fixes" whenever you proposed concrete fixes.
5. If the user then AGREES (e.g. "yes", "do it", "apply", "go ahead", or clicks a suggestion) — your own \
review is in RECENT CONVERSATION. Execute it (including your proposed rewrites) with mutation tools and \
finish. Do NOT re-ask or re-review.

═══ READ TOOLS ═══
inspect_slides   {{"slide_ids":["<id>", ...]}}  → full element JSON for those {plural}
list_vault_files {{"query?":"..."}}             → what data exists: structured files (Excel/CSV/JSON with \
schema + sample values per column) AND unstructured docs (filenames, summaries, tags). Call this first when \
you need data and don't know what's available.
compute_data     {{"instruction":"..."}}        → REAL CALCULATIONS on the structured files: your instruction \
is turned into Python (pandas) and executed against the actual Excel/CSV data in a sandbox; you get the \
computed output back. Use for sums, trends, top-N, comparisons — never estimate what you can compute.
compute_chart    {{"chart_type":"bar|line|pie|...","query":"..."}} → computes a VALIDATED Chart.js config \
from the structured data; embed the returned config verbatim as a chart element's "chartConfig".
search_context   {{"query":"..."}}              → relevant passages from unstructured vault docs (RAG).
search_internet  {{"query":"..."}}              → current, real-time information from the live internet (billed). \
GROUNDING ORDER — STRICT: (1) the USER REQUEST itself, (2) the vault (list_vault_files / compute_data / \
search_context), (3) ONLY IF the needed fact is in neither — search_internet. Use it for genuinely external \
facts: current market sizes, competitor data, recent events, live statistics. NEVER use it for content already \
in the document, the vault, or the user's message.

═══ MUTATION TOOLS (applied live) ═══
update_elements ★PREFERRED for edits★ {{"slide_id":"<id>","elements":[ {{"id":"<element id>", ...ONLY the changed keys...}}, ... ]}}
   • Merge-patch: listed elements get the listed keys changed; everything else (positions, other elements) stays exactly as-is.
   • e.g. recolor 5 shapes → 5 entries with just {{"id","fill"}}. Rewrite a paragraph → {{"id","content"}}.
remove_elements {{"slide_id":"<id>","element_ids":["<id>", ...]}}   — delete specific elements, rest untouched.
edit_slide   FULL REPLACEMENT — layout restructuring only. {{"slide_id":"<id>","title?":"","outline?":"","backgroundColor?":"","elements":[ ...FULL new list... ]}}
   • Preserve element "id"s you keep. Preserve user media (src starting "{{{{UserMedia_") and "video" elements verbatim.
   • For (re)generated images use type "image_placeholder" with an "imageDescription". For charts use "chart" + chartConfig.
add_slide    {{"after_slide_id?":"<id>","position?":"start|end","title":"","outline":"","layout":"content","backgroundColor":"#ffffff","elements":[ ... ]}}
delete_slide {{"slide_id":"<id>"}}
duplicate_slide {{"slide_id":"<id>"}}
reorder_slides  {{"order":["<id>", ...]}}        (every existing id, new order)
update_style    {{"style":{{ ...changed keys: fontFamily,textPrimary,textSecondary,accentColor,{canvas.bg_key} }}}}
update_header_footer {{"header_footer":{{"show_header":true,"header_text":"","show_footer":true,"footer_text":"","align":"center","color":"#64748b","font_size":12}}}}
update_slide_numbers {{"slide_numbers":{{"show":true,"format":"n_of_total|n|{singular}_n","position":"bottom-right|bottom-center|bottom-left","prefix":"","color":"#94a3b8","font_size":12,"start_at":1}}}}

═══ TERMINAL TOOLS (end the turn) ═══
ask_user {{"question":"<what you need to know>","options":["<quick reply>", ...]}}   ← use sparingly
finish   {{"summary":"<what you did, one line>","suggestions":["<next step>", ...]}}

═══ ELEMENT SHAPES ═══
text {{"id","type":"text","x","y","width","height","content","fontSize","fontWeight","fill","textAlign"}}
card {{"id","type":"card","x","y","width","height","title","description","iconName","backgroundColor"}}
icon {{"id","type":"icon","x","y","width","height","iconName","fill"}}  shape {{"id","type":"shape","x","y","width","height","shapeType","fill"}}
chart {{"id","type":"chart","x","y","width","height","chartConfig":{{...}}}}  image {{"id","type":"image_placeholder","x","y","width","height","imageDescription","imageType":"photo"}}
svg  {{"id","type":"svg_diagram","x","y","width","height","svgContent":"<svg viewBox='0 0 800 500'>…</svg>","diagramKind","diagramTitle","fillColor"}}
   • You CAN author SVG yourself — logos, org charts, process flows, cycles, funnels, simple graphics. Keep the \
drawing inside the viewBox and the element's width/height. For photographic imagery use image_placeholder \
(a real image is generated from your imageDescription); for vector/diagram/logo work use svg_diagram. \
PRESERVE existing svgContent byte-for-byte unless the user asked to change that diagram.

Return ONLY the strict JSON object for THIS round — no prose, no markdown fences."""


def _build_loop_user_prompt(
    canvas: CanvasConfig,
    instruction: str,
    overview: str,
    deck_meta: Dict[str, Any],
    chat_history: Optional[List[Dict[str, Any]]],
    scratchpad: List[str],
    current_index: int = 0,
    current_id: Optional[str] = None,
) -> str:
    singular, plural = _noun(canvas)
    style = deck_meta.get("style") or {}
    header_footer = deck_meta.get("header_footer") or {}
    slide_numbers = deck_meta.get("slide_numbers") or {}
    goal = deck_meta.get("goal") or ""
    doc_type = deck_meta.get("content_type") or deck_meta.get("presentation_type") or "informative"
    history = _summarize_history(chat_history)

    # CACHE-OPTIMIZED ORDER. The provider caches the longest identical PREFIX and
    # stops at the first differing token, so stable content goes FIRST and volatile
    # content LAST. Stable prefix = doc goal/type + the FULL DOCUMENT (unchanged
    # until an edit). Volatile suffix = deck chrome that edits mutate, the
    # CURRENTLY-VIEWING marker (changes on scroll / as indices shift), history,
    # scratchpad, and the USER REQUEST. The request MUST stay last — moving it
    # earlier would bust the prefix cache every turn. (Truncation, if it ever
    # fires, cuts the tail — the input cap is set high enough that it does not for
    # any real deck, so the request is never lost.)
    parts = [
        f"DOCUMENT GOAL: {goal or 'N/A'}",
        f"DOCUMENT TYPE: {doc_type}",
        "",
        overview,
        "",
        f"DECK STYLE: {json.dumps(style, ensure_ascii=False)}",
        f"HEADER/FOOTER: {json.dumps(header_footer, ensure_ascii=False)}",
        f"{singular.upper()} NUMBERS: {json.dumps(slide_numbers, ensure_ascii=False)}",
        f'CURRENTLY VIEWING: {singular} index {current_index}' + (f' (id="{current_id}")' if current_id else ''),
    ]
    if history:
        parts += ["", "RECENT CONVERSATION:", history]
    if scratchpad:
        parts += ["", "YOUR WORK SO FAR THIS TURN:", "\n\n".join(scratchpad)]
    parts += [
        "",
        f'USER REQUEST: "{instruction}"',
        "",
        "Return your JSON for the next round now.",
    ]
    return "\n".join(parts)


def _new_slide_id(tag: str = "srv") -> str:
    return f"slide_{tag}_{uuid.uuid4().hex[:10]}"


def _add_slide_sig(args: Dict[str, Any]) -> str:
    """Stable content signature for an add_slide op. Used to suppress the SAME
    slide being added more than once in a single turn — GLM sometimes fails to
    call finish and re-emits the same add across rounds, turning "add one slide"
    into three. Two adds with the same title/outline/text are a model loop, not a
    real request for duplicates."""
    title = str(args.get("title") or "").strip().lower()
    outline = str(args.get("outline") or "").strip().lower()
    texts: List[str] = []
    for el in (args.get("elements") or []):
        if isinstance(el, dict):
            for k in ("content", "title", "label", "description"):
                v = el.get(k)
                if isinstance(v, str) and v.strip():
                    texts.append(v.strip().lower())
    body = " ".join(texts)
    return f"{title}|{outline}|{body[:500]}"


def _apply_op_to_deck(
    op: Dict[str, Any],
    deck_slides: List[Dict[str, Any]],
    deck_meta: Dict[str, Any],
    canvas: CanvasConfig,
    current_index: int,
) -> Optional[Dict[str, Any]]:
    """Validate one mutation op, apply it to the server-side deck copy, and return
    the (possibly id-augmented) op to stream to the frontend, or None if invalid."""
    kind = op.get("op")
    id_index = {s.get("id"): i for i, s in enumerate(deck_slides)}

    if kind in ("edit_slide", "update_elements", "remove_elements", "delete_slide", "duplicate_slide"):
        if op.get("slide_id") not in id_index:
            return None

    if kind in ("edit_slide", "add_slide"):
        elements = op.get("elements")
        if not isinstance(elements, list):
            return None
        _fix_numbered_step_numbers(elements)
        original = deck_slides[id_index[op["slide_id"]]].get("elements") if kind == "edit_slide" else None
        validate_element_positions(elements, canvas, original_elements=original, is_layout_change=True)

    if kind == "edit_slide":
        s = deck_slides[id_index[op["slide_id"]]]
        s["elements"] = op["elements"]
        if op.get("title"):
            s["title"] = op["title"]
        if op.get("outline"):
            s["outline"] = op["outline"]
        if op.get("backgroundColor"):
            s["backgroundColor"] = op["backgroundColor"]
        return op

    if kind == "update_elements":
        # Surgical merge-patch: only the provided keys of the listed elements
        # change; everything else (including geometry) is untouched. This is the
        # PREFERRED edit path — full re-emission (edit_slide) risks destroying
        # layout the model didn't perfectly reproduce.
        patches = op.get("elements")
        if not isinstance(patches, list) or not patches:
            return None
        s = deck_slides[id_index[op["slide_id"]]]
        existing = {e.get("id"): e for e in s.get("elements", []) if isinstance(e, dict)}
        applied_ids = []
        for p in patches:
            pid = p.get("id") if isinstance(p, dict) else None
            if pid in existing:
                el = existing[pid]
                # REGENERATION = new pixels, SAME box. The element-shape
                # reference forces the model to re-emit x/y/width/height on
                # image_placeholder patches, and those regurgitated numbers are
                # often wrong — the regenerated image then lands at a different
                # size/position than the box the user had. When the patch
                # changes an image's description, drop its geometry keys so the
                # live geometry survives the merge (and gets echoed back to the
                # frontend below). A geometry-only patch still moves/resizes.
                is_imageish = el.get("type") in ("image", "image_placeholder") \
                    or p.get("type") in ("image", "image_placeholder")
                desc = p.get("imageDescription")
                if is_imageish and isinstance(desc, str) and desc.strip() \
                        and desc != el.get("imageDescription"):
                    p = {k: v for k, v in p.items() if k not in ("x", "y", "width", "height")}
                el.update({k: v for k, v in p.items() if k != "id"})
                applied_ids.append(pid)
        if not applied_ids:
            return None
        validate_element_positions(s.get("elements", []), canvas, is_layout_change=True)
        # Stream CLAMPED values to the frontend: validation ran on the merged
        # server copy, but the raw patches still carry any out-of-bounds
        # geometry the model emitted. Rebuild each patch from the merged
        # element (patched keys + geometry, post-clamp) so both decks agree.
        merged_by_id = {e.get("id"): e for e in s.get("elements", []) if isinstance(e, dict)}
        applied_set = set(applied_ids)
        rebuilt = []
        for p in patches:
            pid = p.get("id") if isinstance(p, dict) else None
            if pid in applied_set and pid in merged_by_id:
                keys = (set(p.keys()) | {"x", "y", "width", "height"}) - {"id"}
                rebuilt.append({"id": pid, **{k: merged_by_id[pid][k] for k in keys if k in merged_by_id[pid]}})
        op["elements"] = rebuilt
        if op.get("title"):
            s["title"] = op["title"]
        op["applied_ids"] = applied_ids
        return op

    if kind == "remove_elements":
        ids = op.get("element_ids")
        if not isinstance(ids, list) or not ids:
            return None
        s = deck_slides[id_index[op["slide_id"]]]
        rm = set(ids)
        before = len(s.get("elements", []))
        s["elements"] = [e for e in s.get("elements", []) if e.get("id") not in rm]
        if len(s["elements"]) == before:
            return None  # nothing matched — don't echo a no-op to the frontend
        return op

    if kind == "add_slide":
        new_id = _new_slide_id("new")
        op["id"] = new_id  # frontend uses this id so later reorder ops line up
        new_slide = {
            "id": new_id,
            "title": op.get("title", "New " + ("Slide" if canvas.content_type == "presentation" else "Page")),
            "outline": op.get("outline", ""),
            "layout": op.get("layout", "content"),
            "backgroundColor": op.get("backgroundColor", "#ffffff"),
            "elements": op["elements"],
        }
        if op.get("after_slide_id") in id_index:
            insert_at = id_index[op["after_slide_id"]] + 1
        elif op.get("position") == "start":
            insert_at = 0
        elif op.get("position") == "end":
            insert_at = len(deck_slides)
        else:
            insert_at = (current_index + 1) if 0 <= current_index < len(deck_slides) else len(deck_slides)
        # Stamp the resolved position by id so the frontend inserts at the exact
        # same spot (keeps both deck copies aligned for any later reorder op).
        if insert_at <= 0:
            op["position"] = "start"
            op["after_slide_id"] = None
        else:
            op["after_slide_id"] = deck_slides[insert_at - 1].get("id")
            op["position"] = None
        deck_slides.insert(insert_at, new_slide)
        return op

    if kind == "delete_slide":
        if len(deck_slides) <= 1:
            return None
        deck_slides.pop(id_index[op["slide_id"]])
        return op

    if kind == "duplicate_slide":
        src = deck_slides[id_index[op["slide_id"]]]
        new_id = _new_slide_id("dup")
        op["new_id"] = new_id
        # DEEP copy — a shallow {**src} would share the elements list/dicts with
        # the source, so a later update_elements on either slide (which patches
        # element dicts in place) would silently mutate both.
        dup = copy.deepcopy(src)
        dup["id"] = new_id
        deck_slides.insert(id_index[op["slide_id"]] + 1, dup)
        return op

    if kind == "reorder_slides":
        order = op.get("order")
        if not isinstance(order, list):
            return None
        valid = set(id_index.keys())
        filtered = [sid for sid in order if sid in valid]
        for sid in valid:
            if sid not in filtered:
                filtered.append(sid)
        op["order"] = filtered
        deck_slides.sort(key=lambda s: filtered.index(s["id"]) if s["id"] in filtered else 1e9)
        return op

    if kind == "update_style":
        if isinstance(op.get("style"), dict):
            deck_meta.setdefault("style", {}).update(op["style"])
            return op
        return None

    if kind == "update_header_footer":
        if isinstance(op.get("header_footer"), dict):
            deck_meta.setdefault("header_footer", {}).update(op["header_footer"])
            return op
        return None

    if kind == "update_slide_numbers":
        if isinstance(op.get("slide_numbers"), dict):
            deck_meta.setdefault("slide_numbers", {}).update(op["slide_numbers"])
            return op
        return None

    return None


async def _exec_read_tool(
    tool: str, args: Dict[str, Any], deck_slides: List[Dict[str, Any]],
    user_id: str, folder_ids: Optional[List[str]],
) -> str:
    """Run a read tool and return an observation string for the scratchpad."""
    if tool == "search_internet":
        query = str(args.get("query") or "").strip()
        if not query:
            return "search_internet: missing 'query'."
        try:
            from citra_internet_service import execute_internet_search
            result = await asyncio.to_thread(
                execute_internet_search, query,
                context="", user_id=user_id, user_email=user_id, max_tokens=4000,
            )
            return f"search_internet results for {query!r}:\n{(result or '').strip()[:8000]}"
        except Exception as e:
            logger.error(f"🌐 [AGENT] search_internet failed: {e}")
            return f"search_internet: FAILED — {e}"
    if tool == "inspect_slides":
        ids = args.get("slide_ids") or []
        by_id = {s.get("id"): i for i, s in enumerate(deck_slides)}
        # "all" / "*" → whole-document review pass.
        if any(str(sid).lower() in ("all", "*") for sid in ids):
            ids = [s.get("id") for s in deck_slides]
        # Return EVERY requested slide IN FULL — no size budget, no omission.
        # Editing from a partial view of the document silently degrades quality,
        # so we never hide a requested slide. An oversized request fails LOUD at
        # the LLM call (RULE #1) rather than us quietly trimming what the model
        # can see.
        out_blobs: List[str] = []
        for sid in ids:
            if sid not in by_id:
                continue
            out_blobs.append(json.dumps(_compact_slide(deck_slides[by_id[sid]], by_id[sid]), ensure_ascii=False))
        if not out_blobs:
            return "inspect_slides: no matching ids."
        return "inspect_slides →\n[" + ",".join(out_blobs) + "]"

    if tool == "search_context":
        if not folder_ids:
            return "search_context: no vault folders selected — no grounding available."
        try:
            ctx = await retrieve_vault_context(user_id, args.get("query", ""), folder_ids, top_k=3)
            return f"search_context → {ctx[:3000]}" if ctx else "search_context: no relevant results."
        except Exception as e:
            return f"search_context: retrieval failed ({e})."

    # ── Vault data plumbing — the SAME primitives first-time generation uses ──

    if tool == "list_vault_files":
        if not folder_ids:
            return "list_vault_files: no vault folders selected."
        parts = []
        try:
            from services.structured_file_listing import list_structured_files, format_schema_preview_for_prompt
            listing = await list_structured_files(user_id, folder_ids)
            entries = listing.get("entries") or []
            if entries:
                parts.append(
                    "STRUCTURED FILES (Excel/CSV/JSON — query them with compute_data / compute_chart):\n"
                    + format_schema_preview_for_prompt(entries, listing.get("truncated_files"))
                )
            else:
                parts.append("STRUCTURED FILES: none in the selected folders.")
        except Exception as e:
            logger.warning(f"📂 [AGENT-LOOP] structured listing failed: {e}")
            parts.append(f"STRUCTURED FILES: listing failed ({e}).")
        try:
            from services.unstructured_file_listing import prefetch_unstructured_metadata_for_outline
            meta = await prefetch_unstructured_metadata_for_outline(
                user_id=user_id, folder_ids=folder_ids, query=args.get("query", "") or "document overview",
            )
            parts.append(
                "UNSTRUCTURED FILES (docs/PDFs — pull passages with search_context):\n" + meta
                if meta else "UNSTRUCTURED FILES: none relevant in the selected folders."
            )
        except Exception as e:
            logger.warning(f"📂 [AGENT-LOOP] unstructured listing failed: {e}")
            parts.append(f"UNSTRUCTURED FILES: listing failed ({e}).")
        return "list_vault_files →\n" + "\n\n".join(parts)

    if tool == "compute_data":
        if not folder_ids:
            return "compute_data: no vault folders selected — cannot compute."
        instruction = (args.get("instruction") or "").strip()
        if not instruction:
            return "compute_data: missing 'instruction'."
        try:
            from services.structured_sandbox import run_structured_sandbox
            result = await run_structured_sandbox(
                user_id, folder_ids, instruction, log_prefix="AGENT-EDIT",
            )
            if result.get("success") and result.get("stdout"):
                return "compute_data →\n" + str(result["stdout"])[:6000]
            return f"compute_data: failed ({result.get('error') or 'no output'}). " \
                   f"stderr: {str(result.get('stderr') or '')[:500]}"
        except Exception as e:
            logger.warning(f"🧮 [AGENT-LOOP] compute_data failed: {e}")
            return f"compute_data: execution failed ({e})."

    if tool == "compute_chart":
        if not folder_ids:
            return "compute_chart: no vault folders selected — cannot compute."
        try:
            from services.edit_orchestrator import generate_chart_data
            result = await generate_chart_data(
                chart_type=args.get("chart_type") or "bar",
                query=args.get("query") or "",
                user_id=user_id,
                folder_ids=folder_ids,
            )
            if result.get("success") and result.get("chart_config"):
                cfg = json.dumps(result["chart_config"], ensure_ascii=False)
                src = result.get("source_document") or result.get("source") or "vault"
                return (
                    f"compute_chart → validated Chart.js config (source: {src}). Embed it VERBATIM as the "
                    f'"chartConfig" of a chart element:\n{cfg[:6000]}'
                )
            return f"compute_chart: failed ({result.get('message') or 'no config'})."
        except Exception as e:
            logger.warning(f"📊 [AGENT-LOOP] compute_chart failed: {e}")
            return f"compute_chart: failed ({e})."

    return f"{tool}: unknown read tool."


def _parse_round(raw_text: str) -> Dict[str, Any]:
    cleaned = extract_json_from_response(raw_text or "")
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("round is not an object")
    actions = data.get("actions")
    if not isinstance(actions, list):
        # tolerate a single {tool,args} at top level
        if data.get("tool"):
            actions = [{"tool": data.get("tool"), "args": data.get("args", {})}]
        else:
            actions = []
    return {"reasoning": data.get("reasoning") or "", "actions": actions}


async def agent_edit_deck_loop_streaming(
    instruction: str,
    slides: List[Dict[str, Any]],
    user_id: str,
    canvas: CanvasConfig,
    current_index: int = 0,
    deck_meta: Optional[Dict[str, Any]] = None,
    chat_history: Optional[List[Dict[str, Any]]] = None,
    folder_ids: Optional[List[str]] = None,
    selected_element_ids: Optional[List[str]] = None,
):
    """Multi-round agent loop (SSE). Streams status / operations / ask_user /
    finish events. Read tools loop; mutation tools apply live; ask_user & finish
    end the turn."""
    deck_meta = dict(deck_meta or {})
    deck_slides = [dict(s) for s in (slides or [])]
    singular, _ = _noun(canvas)

    if not instruction or not instruction.strip():
        yield _sse({"type": "finish", "chat_message": "Tell me what you'd like to change.", "suggestions": []})
        yield _sse({"type": "complete"})
        return
    if not deck_slides:
        yield _sse({"type": "finish", "chat_message": f"There are no {singular}s to edit yet.", "suggestions": []})
        yield _sse({"type": "complete"})
        return

    system_prompt = build_loop_system_prompt(canvas)
    scratchpad: List[str] = []
    added_sigs: set = set()  # add_slide content signatures applied THIS turn (dup guard)
    mutated_ids: set = set()  # slide ids already content-edited THIS turn (anti-churn guard)
    consecutive_read_rounds = 0  # read-pressure guard: stop research from eating the edit budget
    tool_calls_used = 0  # total executed tool calls this turn (cap: MAX_TOOL_CALLS)
    total_ops = 0
    # Track the viewed slide BY ID — indices shift as add/delete/reorder ops apply.
    current_id = deck_slides[current_index].get("id") if 0 <= current_index < len(deck_slides) else None

    _singular, _ = _noun(canvas)

    # Review-only turn: the agent may inspect, ask for a focus, and finish with
    # findings + suggestions — but mutation tools are HARD BLOCKED. The user
    # approves (next turn) before anything changes. Also covers the turn right
    # after the agent asked where to focus the review.
    review_only = _is_review_only_request(instruction) or _is_review_followup(instruction, chat_history)
    if review_only:
        # No status event here — the frontend already shows its own pre-send
        # line, and emitting another near-identical one reads as a duplicate.
        logger.info("🔍 [AGENT-LOOP] review-only turn — mutations blocked")

    try:
        for round_no in range(MAX_ROUNDS):
            # TOOL-CALL BUDGET: end the turn gracefully once the model has spent
            # its 50 executed tool calls (reads + mutations). Work applied so far
            # is already streamed; this just stops an endless turn.
            if tool_calls_used >= MAX_TOOL_CALLS:
                logger.info(f"🧮 [AGENT-LOOP] tool-call budget exhausted ({tool_calls_used}/{MAX_TOOL_CALLS}) — finishing")
                yield _sse({
                    "type": "finish",
                    "chat_message": "Reached the work limit for one request — applied everything so far. "
                                    "Send a follow-up to continue.",
                    "suggestions": ["Continue where you left off"],
                })
                yield _sse({"type": "complete", "operation_count": total_ops})
                return
            # FULL-DETAIL MODE — ALWAYS. Send every element of every slide each
            # round so the model never edits from a partial view of the
            # document. We deliberately do NOT fall back to a compact overview
            # for large decks: truncating what the model can see silently
            # degrades edit quality. If a deck is large enough to exceed the
            # model context, the LLM call fails LOUD (RULE #1) rather than us
            # quietly trimming. Recomputed each round so it reflects applied
            # mutations.
            full_json = _build_deck_json(deck_slides)
            overview = (
                f"FULL DOCUMENT — every {_singular} with EVERY element, COMPLETE "
                f"(reflects all edits so far; do NOT call inspect_slides):\n{full_json}"
            )
            cur_idx = next((i for i, s in enumerate(deck_slides) if s.get("id") == current_id), 0)
            user_prompt = _build_loop_user_prompt(
                canvas, instruction, overview, deck_meta, chat_history, scratchpad,
                current_index=cur_idx, current_id=current_id,
            )
            if selected_element_ids:
                user_prompt += (
                    f"\n\nUSER SELECTION: the user has element id(s) {json.dumps(selected_element_ids)} "
                    f"selected on the canvas — \"this\" / \"it\" refers to THOSE elements. Prefer "
                    f"update_elements targeting exactly these ids unless the request clearly means more."
                )
            if review_only:
                vault_note = (
                    " The user's vault folders are attached — list_vault_files / compute_data / search_context "
                    "are available if checking the source data would strengthen the review (your call)."
                    if folder_ids else ""
                )
                user_prompt += (
                    f"\n\n⚠ THIS TURN IS A REVIEW — mutation tools are DISABLED and will be rejected.{vault_note}\n"
                    f"Follow the REVIEW WORKFLOW: review along the user's stated direction; if they gave NO "
                    f"direction, ask_user once for the focus (with options) instead of guessing. Ground findings "
                    f"in the real document ({_singular} numbers, quoted text, concrete proposed fixes). Then "
                    f'finish — include "Apply all suggested fixes" in suggestions when you proposed fixes. '
                    f"Do NOT edit anything this turn."
                )
            elif folder_ids:
                user_prompt += (
                    "\n\nVAULT ATTACHED: the user's vault folders are connected — this document's facts come "
                    "from them. For NEW or CHANGED factual content use the data tools (list_vault_files → "
                    "compute_data / compute_chart for Excel/CSV calculations, search_context for document "
                    "facts); never invent figures."
                )
            # glm-5.1 in reasoning mode burns 15-25K tokens on internal reasoning
            # before emitting JSON, and a whole-deck edit re-emits many full slides
            # — 50K truncated the op JSON mid-stream on large decks. 128K (bounded
            # by the model context window minus the prompt) + reasoning_effort="low".
            rnd = None
            retry_feedback = ""
            _MAX_PARSE_ATTEMPTS = 4  # retries are cheap (prefix cache-hit) and GLM
            # needs 2-3 shots on quote-escaping ~30% of rounds; 3 proved fatal live
            for attempt in range(_MAX_PARSE_ATTEMPTS):
                llm_task = asyncio.create_task(asyncio.to_thread(
                    llm_call, system_prompt, user_prompt + retry_feedback,
                    # 64K per ROUND (not 128K): a compliant wave (≤5 slides ≈ 30K)
                    # + glm reasoning (15-25K) fits easily, while an overflow
                    # attempt (model ignoring the MAX-5 rule and emitting the
                    # whole deck — observed 668K chars) now fails in ~4 min
                    # instead of 15+, and the CUT-OFF retry redirects it.
                    user_id=user_id, max_tokens=64000, temperature=0.3,
                    json_mode=True, reasoning_effort="low",
                ))
                while not llm_task.done():
                    done, _ = await asyncio.wait({llm_task}, timeout=_HEARTBEAT_SECS)
                    if not done:
                        yield _sse({"type": "status", "stage": "thinking", "round": round_no,
                                    "message": f"Working on your changes… (step {round_no + 1} · {tool_calls_used}/{MAX_TOOL_CALLS} actions)", "heartbeat": True})
                raw = llm_task.result()
                try:
                    rnd = _parse_round(raw)
                    break
                except Exception as e:
                    logger.warning(
                        f"⚠️ [AGENT-LOOP] round {round_no} unparseable "
                        f"(attempt {attempt + 1}/{_MAX_PARSE_ATTEMPTS}): {e} | {str(raw)[:200]}"
                    )
                    # Feed the EXACT parse error back so GLM can self-correct the
                    # precise break (usually an unescaped " inside a string value),
                    # not just "try again" — same self-correction pattern the MCP
                    # NL→SQL planner uses.
                    # TRUNCATION is different from malformed JSON: the model emitted
                    # MORE than the output limit fits (observed live: a whole-deck
                    # restructure = 525K chars vs a 128K-token provider ceiling —
                    # physically impossible). Re-asking for "valid JSON" would just
                    # re-attempt the same overflow (21 min per attempt); instead
                    # instruct a SMALLER batch this round.
                    _truncated = "Unterminated" in str(e) or len(str(raw)) > 300_000
                    if _truncated:
                        retry_feedback = (
                            "\n\nYOUR PREVIOUS RESPONSE WAS CUT OFF — you emitted more output than fits in "
                            "one round. Do NOT retry the same batch. Emit AT MOST 3 full-{0} mutations in "
                            "THIS round's JSON (plus deletes/reorders, which are tiny), and continue the "
                            "remaining {0}s in later rounds. Return ONE complete, strict JSON object."
                        ).format(singular)
                    else:
                        retry_feedback = (
                            "\n\nYOUR PREVIOUS RESPONSE FAILED TO PARSE AS JSON.\n"
                            f"Parser error: {e}\n"
                            'Return ONE complete, strict JSON object {"reasoning":"...","actions":[...]} '
                            "— no markdown fences, no commentary before or after. Every double-quote that "
                            "appears INSIDE a string value must be escaped as \\\" (or use single quotes for "
                            "quoted phrases in prose), and there must be no literal newlines inside string values."
                        )
            if rnd is None:
                logger.error(f"❌ [AGENT-LOOP] round {round_no} unparseable after retry")
                yield _sse({"type": "error", "message": "I couldn't structure that step. Please rephrase."})
                return

            if rnd["reasoning"]:
                # Show the model's full reasoning (up to 150K chars) so the user can
                # see what it's planning — not a clipped 200-char teaser.
                yield _sse({"type": "status", "stage": "thinking", "round": round_no, "message": rnd["reasoning"][:150000]})

            actions = rnd["actions"]
            if not actions:
                # No action and no terminal — treat as done to avoid a spin.
                yield _sse({"type": "finish", "chat_message": rnd["reasoning"] or "Done.", "suggestions": []})
                yield _sse({"type": "complete", "operation_count": total_ops})
                return

            round_obs: List[str] = []
            applied_ops: List[Dict[str, Any]] = []
            round_edited_ids: set = set()  # slide ids content-edited THIS round
            slide_muts_this_round = 0  # full-slide mutations this round (wave cap: 5)
            terminal = None
            read_used = False

            for action in actions:
                if not isinstance(action, dict):
                    continue
                tool = action.get("tool")
                args = action.get("args") or {}

                if tool in TERMINAL_TOOLS:
                    terminal = (tool, args)
                    break
                if tool in READ_TOOLS:
                    tool_calls_used += 1
                    obs = await _exec_read_tool(tool, args, deck_slides, user_id, folder_ids)
                    round_obs.append(obs)
                    read_used = True
                    continue
                if tool in MUTATION_TOOLS:
                    if review_only:
                        round_obs.append(
                            f"{tool}: BLOCKED — this turn is a REVIEW. Do not edit; call finish with your "
                            f"numbered findings as summary and actionable fixes as suggestions "
                            f'(first: "Apply all suggested fixes"). The user will approve before edits.'
                        )
                        continue
                    # WAVE CAP — server-side enforcement of the MAX-5 prompt rule:
                    # more than 5 full-{singular} mutations in one round risks the
                    # output overflow that truncates the whole round. Apply the
                    # first 5, defer the rest to the next round.
                    if tool in ("edit_slide", "add_slide", "duplicate_slide"):
                        if slide_muts_this_round >= 5:
                            round_obs.append(
                                f"{tool}: DEFERRED — max 5 full-{singular} mutations per round already "
                                f"applied. Re-emit this {singular}'s mutation in the NEXT round."
                            )
                            continue
                        slide_muts_this_round += 1
                    # Anti-churn HARD BLOCK: a content edit targeting a {singular}
                    # already edited in a PREVIOUS round of this turn is the model
                    # failing to finish and redoing its own work (it can't see the
                    # render). Previously we streamed that second edit and THEN
                    # auto-finished — but for image elements each pass triggers a
                    # fresh image generation, so one "change the image" command
                    # produced TWO different images. Now the re-edit is rejected
                    # outright; the round becomes no-progress and auto-finishes.
                    # (Multiple edits to the same {singular} WITHIN one round stay
                    # allowed — round_edited_ids only merges into mutated_ids at
                    # round end.)
                    if tool in CONTENT_EDIT_TOOLS:
                        _tgt = args.get("slide_id")
                        if _tgt and _tgt in mutated_ids:
                            round_obs.append(
                                f"{tool}: BLOCKED — {singular} {_tgt} was ALREADY edited this turn and the "
                                f"edit is applied exactly as you emitted it. Do NOT redo it. Call finish now."
                            )
                            continue
                    # Duplicate-add guard: if the model re-emits an add_slide whose
                    # content was already added THIS turn (it failed to finish and
                    # looped), suppress it instead of stacking a duplicate {singular}.
                    sig = None
                    if tool == "add_slide":
                        sig = _add_slide_sig(args)
                        if sig in added_sigs:
                            round_obs.append(
                                f"add_slide: SUPPRESSED — a {singular} with this exact content was already "
                                f"added earlier THIS TURN. Not adding a duplicate. The change is done — call finish."
                            )
                            continue
                    op = {"op": tool, **args}
                    live_idx = next((i for i, s in enumerate(deck_slides) if s.get("id") == current_id), 0)
                    cleaned_op = _apply_op_to_deck(op, deck_slides, deck_meta, canvas, live_idx)
                    if cleaned_op is not None:
                        if sig is not None:
                            added_sigs.add(sig)
                        if tool in CONTENT_EDIT_TOOLS:
                            tgt = cleaned_op.get("slide_id") or args.get("slide_id")
                            if tgt:
                                round_edited_ids.add(tgt)
                        applied_ops.append(cleaned_op)
                        tool_calls_used += 1
                        round_obs.append(f"{tool}: applied.")
                    else:
                        round_obs.append(f"{tool}: invalid/ignored.")
                    continue
                round_obs.append(f"{tool}: unknown tool, ignored.")

            # Stream this round's mutations to the frontend.
            if applied_ops:
                total_ops += len(applied_ops)
                yield _sse({"type": "operations", "operations": applied_ops})

            logger.info(
                f"🔁 [AGENT-LOOP] round {round_no}: "
                f"actions=[{', '.join(a.get('tool', '?') for a in actions if isinstance(a, dict))}] "
                f"applied={len(applied_ops)} read={read_used} "
                f"terminal={terminal[0] if terminal else None}"
            )

            # Anti-spin: a non-terminal round that applied no mutation and ran no
            # read tool made NO progress — typically the model re-emitting an
            # already-applied (now duplicate-suppressed) add_slide. Re-prompting
            # would churn to MAX_ROUNDS and risk more duplicates, so finish now.
            if not terminal and not applied_ops and not read_used:
                logger.info(f"🛑 [AGENT-LOOP] round {round_no} made no progress — auto-finishing")
                yield _sse({
                    "type": "finish",
                    "chat_message": "Done." if total_ops else "No changes were needed.",
                    "suggestions": [],
                })
                yield _sse({"type": "complete", "operation_count": total_ops})
                return

            # Terminal tool → end the turn.
            if terminal:
                tname, targs = terminal
                if tname == "ask_user":
                    yield _sse({
                        "type": "ask_user",
                        "chat_message": targs.get("question", "Could you clarify what you'd like?"),
                        "options": [o for o in (targs.get("options") or []) if isinstance(o, str)][:4],
                    })
                else:  # finish
                    suggestions = [s for s in (targs.get("suggestions") or []) if isinstance(s, str)][:3]
                    # A review that proposed fixes must offer the approval chip.
                    if review_only and suggestions and not any("apply" in s.lower() for s in suggestions):
                        suggestions = ["Apply all suggested fixes"] + suggestions[:2]
                    yield _sse({
                        "type": "finish",
                        "chat_message": targs.get("summary") or _default_message(applied_ops, canvas),
                        "suggestions": suggestions,
                    })
                yield _sse({"type": "complete", "operation_count": total_ops})
                return

            # Anti-churn: the model just content-edited a slide it ALREADY edited
            # earlier this turn. It can't see the rendered canvas — it re-reads the
            # JSON, judges the layout "still off", and edits again every round
            # (MAX_ROUNDS of visible re-updates on the same slide). The edit it just
            # made is applied and streamed; we stop here instead of re-prompting for
            # yet another pass. Different slides each round are fine — only re-touching
            # an already-edited slide trips this.
            rechurn_ids = round_edited_ids & mutated_ids
            mutated_ids |= round_edited_ids
            if rechurn_ids and not terminal:
                logger.info(
                    f"🛑 [AGENT-LOOP] round {round_no} re-edited already-edited "
                    f"{_singular}(s) {sorted(rechurn_ids)} — auto-finishing to stop churn"
                )
                yield _sse({
                    "type": "finish",
                    "chat_message": f"Updated the {_singular} — let me know if you'd like further changes.",
                    "suggestions": [],
                })
                yield _sse({"type": "complete", "operation_count": total_ops})
                return

            # READ-PRESSURE GUARD: reads and edits share the round budget, and a
            # data-grounded restructure can burn most of it on search_context
            # (observed live: 6/8 rounds of reads, edits never fit). After 3
            # consecutive read-only rounds, tell the model exactly how many
            # rounds remain and to start applying edits.
            if read_used and not applied_ops:
                consecutive_read_rounds += 1
                calls_left = MAX_TOOL_CALLS - tool_calls_used
                if consecutive_read_rounds >= 3 and calls_left > 0:
                    round_obs.append(
                        f"⚠ BUDGET: {consecutive_read_rounds} consecutive rounds spent on reading and "
                        f"{tool_calls_used}/{MAX_TOOL_CALLS} tool calls already used — only {calls_left} "
                        f"remain for this ENTIRE request (reads AND edits combined). Batch ANY remaining "
                        f"lookups into the next round together with your first mutations — START APPLYING "
                        f"EDITS NOW, or the turn will end before the changes are made."
                    )
            else:
                consecutive_read_rounds = 0

            # Record this round for the next prompt; trim oldest WHOLE entries if
            # the scratchpad grows too large (never cut an entry mid-JSON).
            action_summary = ", ".join(a.get("tool", "?") for a in actions if isinstance(a, dict))
            scratchpad.append(
                f"ROUND {round_no}: actions=[{action_summary}].\nObservations:\n" + "\n".join(round_obs)
            )
            _TRIM_MARKER = "[earlier rounds trimmed]"
            trimmed = False
            while sum(len(s) for s in scratchpad) > 60000:
                # Drop the oldest REAL entry (never the marker — popping it and
                # re-inserting would loop forever). Always keep the newest entry.
                drop_idx = 1 if scratchpad and scratchpad[0] == _TRIM_MARKER else 0
                if len(scratchpad) <= drop_idx + 1:
                    break
                scratchpad.pop(drop_idx)
                trimmed = True
            if trimmed and (not scratchpad or scratchpad[0] != _TRIM_MARKER):
                scratchpad.insert(0, _TRIM_MARKER)

        # Exhausted rounds without finishing.
        yield _sse({
            "type": "finish",
            "chat_message": "Made the changes I could. Let me know if you'd like more.",
            "suggestions": [],
        })
        yield _sse({"type": "complete", "operation_count": total_ops})

    except Exception as e:
        from fastapi import HTTPException
        detail = str(getattr(e, "detail", "")) or str(e)
        if "insufficient_credits" in detail.lower() or "negative balance" in detail.lower():
            yield _sse({"type": "error", "status_code": 402, "message": "Insufficient credits."})
            return
        logger.error(f"❌ [AGENT-LOOP] {e}")
        yield _sse({"type": "error", "message": detail or "Edit failed."})
