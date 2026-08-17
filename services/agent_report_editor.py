# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""
Agentic Report Editor — the "Claude on Word" edit engine for the Report Composer.

Same multi-round ReAct architecture as services/agent_deck_editor.py (which owns
presentations/printables), specialised for the report document model: an ordered
list of PAGES whose content is rich HTML (Tiptap), plus document metadata
(title, letterheadConfig, headerConfig, footerConfig).

The ENTIRE document + chat message go to the LLM; it works in rounds calling
tools, then finishes. Mutations stream to the frontend as operations the
ReportComposer applies to useReportPages state (Tiptap re-renders from the
updated page.content).

Reuses the deck editor's shared helpers (review gate, history summary, SSE
framing, round parsing, vault data tools) — one behaviour, three composers.
"""

from typing import Dict, Any, Optional, List
import copy
import logging
import json
import asyncio
import re
import uuid

from services.edit_orchestrator import llm_call
from services.agent_deck_editor import (
    _is_review_only_request,
    _is_review_followup,
    _summarize_history,
    _sse,
    _parse_round,
    _exec_read_tool as _deck_exec_read_tool,  # vault tools (list/compute/search) are deck-agnostic
)

logger = logging.getLogger(__name__)

MAX_ROUNDS = 50  # LLM-round ceiling; the real work cap is MAX_TOOL_CALLS (50).
# See agent_deck_editor — anti-spin/anti-churn/read-pressure guards terminate
# unproductive loops long before either ceiling.
# A whole-document round can take MINUTES (glm-5.1 reasoning emitting tens of
# thousands of tokens). Emit a keepalive status this often while the LLM runs so
# the SSE stream never goes silent (frozen UI / dropped idle proxy connection).
_HEARTBEAT_SECS = 8

READ_TOOLS = {"inspect_pages", "list_vault_files", "compute_data", "compute_chart", "search_context", "search_internet"}
MAX_TOOL_CALLS = 50  # total executed tool calls per turn (reads + mutations)
MUTATION_TOOLS = {
    "edit_page", "patch_page", "add_page", "delete_page", "reorder_pages",
    "update_title", "update_letterhead", "update_header_footer",
}
TERMINAL_TOOLS = {"ask_user", "finish"}
# Tools that rewrite a page's CONTENT. Re-emitting one against a page already
# edited THIS turn is the "keeps updating the same page" churn: the model can't
# see the rendered page, judges its own output "still off", and edits again every
# round. We let the first edit through, then finish.
CONTENT_EDIT_TOOLS = {"edit_page", "patch_page"}

# Strip tags for compact text overviews.
_TAG_RE = re.compile(r"<[^>]+>")


def _add_page_sig(args: Dict[str, Any]) -> str:
    """Stable content signature for an add_page op — suppress the SAME page being
    added more than once in a turn. GLM sometimes re-emits an add it already
    applied instead of calling finish, turning "add one page" into several; two
    adds with the same title/html are a model loop, not a request for duplicates."""
    title = str(args.get("title") or "").strip().lower()
    html = str(args.get("html") or "").strip().lower()
    return f"{title}|{html[:800]}"


def _page_text(page: Dict[str, Any], limit: int = 200) -> str:
    text = _TAG_RE.sub(" ", page.get("content") or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _build_overview(pages: List[Dict[str, Any]]) -> str:
    lines = []
    for i, p in enumerate(pages):
        html_len = len(p.get("content") or "")
        lines.append(
            f'[{i}] id="{p.get("id")}" "{(p.get("title") or "Untitled")[:60]}" — '
            f"{html_len} chars HTML | starts: \"{_page_text(p, 120)}\""
        )
    return "\n".join(lines)


# Redact raw image data/links in page HTML so NO image bytes reach the LLM. The
# frontend markerizes images to {{IMG_n}} before sending; this is a defensive net
# for any raw base64 data-URI or http(s) src that slips through (also kills token
# bloat). Marker srcs ({{...}}) are left intact so the frontend can restore them.
_RAW_IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=)(["\'])(data:[^"\']*|https?://[^"\']*)\2', re.IGNORECASE)


def _redact_raw_images(html: str) -> str:
    if not html or ("data:" not in html and "http" not in html):
        return html
    return _RAW_IMG_SRC_RE.sub(r'\1"{{IMG_PLACEHOLDER}}"', html)


def _build_full_doc(pages: List[Dict[str, Any]]) -> str:
    out = []
    for i, p in enumerate(pages):
        out.append({
            "index": i,
            "id": p.get("id"),
            "title": p.get("title") or "",
            "html": _redact_raw_images(p.get("content") or ""),
        })
    return json.dumps(out, ensure_ascii=False)


def build_report_system_prompt() -> str:
    return """You are an expert enterprise document editor agent working INSIDE a live report editor — \
like Claude editing a Word document directly in chat. The document is an ordered list of PAGES whose \
content is clean HTML (p, h1-h4, strong, em, ul/ol/li, table/tr/td, blockquote, img). You work in \
ROUNDS, calling tools, until the task is done.

═══ HOW TO WORK ═══
- Each round, return ONE JSON object: {"reasoning":"<short>","actions":[ {"tool":"<name>","args":{...}}, ... ]}
- Batch related actions in one round. Read-tool results come back as observations and you get another round.
- If the prompt contains the FULL DOCUMENT (every page's HTML), you have everything — do NOT call inspect_pages.
- Mutations apply EXACTLY as you emit them — never re-inspect to "verify" your own edits. Finish promptly.
- ONE EDIT PASS PER PAGE, THEN FINISH: make ALL your changes to a page in ONE round, then call finish IN THE \
SAME round. You CANNOT see the rendered page — only its HTML — so do NOT re-edit the same page across rounds \
trying to "improve" it; looping edits on one page just churns it. Likewise emit exactly ONE add_page per new \
page and finish — re-emitting an add you already applied creates DUPLICATE pages and is a bug. If you have an \
alternative approach in mind, offer it as a finish suggestion so the USER decides — never redo applied work.
- MAX 5 PAGES PER ROUND — HARD RULE: never emit more than 5 full-page mutations (edit_page / add_page) in a \
single round; a larger batch OVERFLOWS your output limit and the entire round fails. For big restructures work \
in waves of ≤5 pages across rounds (your 50-tool-call budget is ample). patch_page find/replace edits are \
small and don't count toward the 5.
- PREFER SURGICAL EDITS: patch_page (find/replace inside a page's HTML) for wording, numbers, small inserts — \
it cannot disturb the rest of the page. Use edit_page (full new HTML) only when restructuring a whole page.
- TARGET RESOLUTION: "this page"/"here" → the page marked CURRENTLY VIEWING. A topic reference → match by \
title/content. "the whole report" → all pages.
- Letterhead, headers, footers and page numbers are DOCUMENT SETTINGS (update_letterhead / \
update_header_footer) — never write them as page content.
- CLARIFY BEFORE GUESSING: when a request is ambiguous in a way that materially changes the outcome, use \
ask_user ONCE with quick-reply options, then act on the answer. Clear requests: act immediately.
- When finished, call finish with a one-line summary and 2–3 suggested NEW improvements.

═══ IMAGES, LOGOS & SVG ═══
- Existing images arrive with PLACEHOLDER srcs like src="{{IMG_3}}" — the real image data is held by the app. \
NEVER alter, invent or expand a {{IMG_n}} marker. Keep the whole <img> tag to keep the image; move the tag to \
move the image to another spot or page; drop the tag ONLY when the user asked to remove that image. Tags with \
data-user-media="true" are the user's own uploads — sacred unless explicitly asked.
- The editor's schema STRIPS raw <svg> elements from page HTML — never emit a bare <svg> tag in content.
- You CAN render NEW vector graphics (logos, diagrams, simple illustrations): author the SVG yourself and \
embed it as a data-URI image, which the editor preserves and exports crisply:
  <img src="data:image/svg+xml;utf8,<URL-ENCODED SVG MARKUP>" width="200" alt="logo"/>
  (URL-encode the SVG: % # < > " characters must be encoded; single quotes inside the SVG.)
- NEVER invent external image URLs (no placeholder.com, no guessed paths). There is no photo-generation \
pipeline in this editor — for photographic imagery, tell the user to insert an image manually or use an \
SVG illustration instead.
- The letterhead logo is config (update_letterhead.logoUrl), not page content. logoUrl value "__KEEP__" means \
a logo is already set — leave it out of your op to keep it.

═══ DATA GROUNDING — NEVER INVENT FACTS ═══
This document is typically BUILT FROM the user's vault. NEVER invent numbers, statistics, dates, names, \
quotes or domain claims. PRESERVE existing data values verbatim when rewording. When an edit INTRODUCES or \
CHANGES factual content: if vault folders are attached use the data tools (list_vault_files → compute_data \
for Excel/CSV calculations, search_context for document facts); otherwise do NOT fabricate — keep existing \
values, write qualitative content, or ask_user. Pure style/structure/tone edits need no vault lookup.

═══ READ TOOLS ═══
inspect_pages    {"page_ids":["<id>", ...]}  → full HTML of those pages (["all"] = whole document)
list_vault_files {"query?":"..."}            → available structured files (schema+samples) + unstructured docs
compute_data     {"instruction":"..."}       → REAL pandas calculations on vault Excel/CSV; never estimate what you can compute
compute_chart    {"chart_type":"bar|line|pie|...","query":"..."} → validated Chart.js config; embed it in page HTML \
inside <chart-config>...</chart-config> tags (JSON inside the tag)
search_context   {"query":"..."}             → relevant passages from unstructured vault docs
search_internet  {"query":"..."}             → current, real-time info from the live internet (billed). \
GROUNDING ORDER — STRICT: (1) the USER REQUEST itself, (2) the vault tools, (3) ONLY IF the needed fact is \
in neither — search_internet (current market data, competitor info, recent events). NEVER for content \
already in the document, vault, or user's message.

═══ MUTATION TOOLS (applied live) ═══
patch_page ★PREFERRED★ {"page_id":"<id>","find":"<exact HTML/text substring>","replace":"<replacement>","all?":false}
   • Exact substring match against the page's HTML. Keep `find` short but unique. Fails (observation) if not found.
edit_page   {"page_id":"<id>","title?":"...","html":"<FULL new page HTML>"}   — full replacement, restructuring only.
add_page    {"after_page_id?":"<id>","position?":"start|end","title":"...","html":"<page HTML>"}
delete_page {"page_id":"<id>"}
reorder_pages {"order":["<id>", ...]}   (every existing id, new order)
update_title {"title":"..."}            — the document title
update_letterhead {"letterhead":{"enabled":true,"companyName":"","address":"line1\\nline2","phone":"","email":"","website":"","logoUrl":"","showRule":true,"allPages":false}}
update_header_footer {"header?":{"enabled":true,"leftContent":"","centerContent":"","rightContent":"","showOnFirstPage":false,"showLogo":false,"logoUrl":""},"footer?":{"enabled":true,"leftContent":"","centerContent":"","rightContent":"Page {page} of {total}","showOnFirstPage":true}}
   • Placeholders available in header/footer content: {date} {page} {total} {title} {author}.

═══ REVIEW WORKFLOW (review / critique / suggest requests) ═══
You can review through ANY lens the user needs — strategic, content & wording, structure & flow, data \
credibility, formatting, audience fit. The USER'S DIRECTION decides the lens. If they gave NO direction \
(bare "review it"), ask_user ONCE with focus options. Reviews NEVER mutate: ground findings in the real \
document (page numbers, quoted text, concrete proposed rewrites), then finish — suggestions should include \
"Apply all suggested fixes" when you proposed fixes. If the user then agrees, your review is in RECENT \
CONVERSATION — execute it with mutation tools without re-asking.

═══ TERMINAL TOOLS (end the turn) ═══
ask_user {"question":"...","options":["<quick reply>", ...]}    ← use for genuine ambiguity only
finish   {"summary":"<what you did / your review>","suggestions":["<next step>", ...]}

Return ONLY the strict JSON object for THIS round — no prose, no markdown fences."""


def _build_user_prompt(
    instruction: str,
    overview: str,
    meta: Dict[str, Any],
    chat_history: Optional[List[Dict[str, Any]]],
    scratchpad: List[str],
    current_index: int,
    current_id: Optional[str],
) -> str:
    history = _summarize_history(chat_history)
    # CACHE-OPTIMIZED ORDER (see agent_deck_editor._build_loop_user_prompt): stable
    # prefix (title/goal + FULL DOCUMENT) first; volatile content (chrome that edits
    # mutate, the view marker, history, scratchpad, USER REQUEST) last. The request
    # stays last so the cacheable prefix isn't busted every turn.
    parts = [
        f"DOCUMENT TITLE: {meta.get('title') or 'Untitled Report'}",
        f"DOCUMENT GOAL: {meta.get('goal') or 'N/A'}",
        "",
        overview,
        "",
        f"LETTERHEAD: {json.dumps(meta.get('letterheadConfig') or {}, ensure_ascii=False)}",
        f"HEADER: {json.dumps(meta.get('headerConfig') or {}, ensure_ascii=False)}",
        f"FOOTER: {json.dumps(meta.get('footerConfig') or {}, ensure_ascii=False)}",
        f'CURRENTLY VIEWING: page index {current_index}' + (f' (id="{current_id}")' if current_id else ''),
    ]
    if history:
        parts += ["", "RECENT CONVERSATION:", history]
    if scratchpad:
        parts += ["", "YOUR WORK SO FAR THIS TURN:", "\n\n".join(scratchpad)]
    parts += ["", f'USER REQUEST: "{instruction}"', "", "Return your JSON for the next round now."]
    return "\n".join(parts)


def _new_page_id() -> str:
    return f"page_srv_{uuid.uuid4().hex[:10]}"


def _apply_op(
    op: Dict[str, Any],
    pages: List[Dict[str, Any]],
    meta: Dict[str, Any],
    current_index: int,
) -> Optional[Dict[str, Any]]:
    """Apply one mutation to the server-side copy; return the cleaned op to
    stream, or None if invalid (caller reports the rejection as an observation)."""
    kind = op.get("op")
    idx_by_id = {p.get("id"): i for i, p in enumerate(pages)}

    if kind in ("edit_page", "patch_page", "delete_page") and op.get("page_id") not in idx_by_id:
        return None

    if kind == "patch_page":
        find = op.get("find")
        if not isinstance(find, str) or not find:
            return None
        p = pages[idx_by_id[op["page_id"]]]
        content = p.get("content") or ""
        if find not in content:
            op["_error"] = "find_not_found"
            return None
        replace = op.get("replace") if isinstance(op.get("replace"), str) else ""
        p["content"] = content.replace(find, replace) if op.get("all") else content.replace(find, replace, 1)
        return op

    if kind == "edit_page":
        if not isinstance(op.get("html"), str):
            return None
        p = pages[idx_by_id[op["page_id"]]]
        # GUARD: a full rewrite must not silently drop the user's own uploaded
        # images. Collect user-media img markers from the old content; if any is
        # missing from the new html, reject — the model must either keep the tag
        # or remove it explicitly via patch_page (which proves intent).
        old_content = p.get("content") or ""
        user_media_srcs = re.findall(
            r'<img\b[^>]*data-user-media="true"[^>]*?src=["\']([^"\']+)["\']', old_content,
        ) + re.findall(
            r'<img\b[^>]*?src=["\']([^"\']+)["\'][^>]*data-user-media="true"', old_content,
        )
        dropped = [s for s in set(user_media_srcs) if s not in op["html"]]
        if dropped:
            op["_error"] = "dropped_user_media"
            op["_dropped"] = dropped
            return None
        p["content"] = op["html"]
        if op.get("title"):
            p["title"] = op["title"]
        return op

    if kind == "add_page":
        if not isinstance(op.get("html"), str):
            return None
        new_id = _new_page_id()
        op["id"] = new_id
        new_page = {"id": new_id, "title": op.get("title") or "New Page", "content": op["html"]}
        if op.get("after_page_id") in idx_by_id:
            insert_at = idx_by_id[op["after_page_id"]] + 1
        elif op.get("position") == "start":
            insert_at = 0
        elif op.get("position") == "end":
            insert_at = len(pages)
        else:
            insert_at = (current_index + 1) if 0 <= current_index < len(pages) else len(pages)
        # Stamp resolved position so the frontend inserts at the same spot.
        if insert_at <= 0:
            op["position"] = "start"
            op["after_page_id"] = None
        else:
            op["after_page_id"] = pages[insert_at - 1].get("id")
            op["position"] = None
        pages.insert(insert_at, new_page)
        return op

    if kind == "delete_page":
        if len(pages) <= 1:
            return None
        pages.pop(idx_by_id[op["page_id"]])
        return op

    if kind == "reorder_pages":
        order = op.get("order")
        if not isinstance(order, list):
            return None
        valid = set(idx_by_id.keys())
        # Dedupe (LLMs occasionally repeat an id) AND append forgotten ids so the
        # streamed order is always a clean permutation the frontend can apply.
        filtered = list(dict.fromkeys(pid for pid in order if pid in valid))
        for pid in valid:
            if pid not in filtered:
                filtered.append(pid)
        op["order"] = filtered
        pages.sort(key=lambda p: filtered.index(p["id"]) if p["id"] in filtered else 1e9)
        return op

    if kind == "update_title":
        if not op.get("title"):
            return None
        meta["title"] = op["title"]
        return op

    if kind == "update_letterhead":
        if not isinstance(op.get("letterhead"), dict):
            return None
        meta.setdefault("letterheadConfig", {}).update(op["letterhead"])
        return op

    if kind == "update_header_footer":
        touched = False
        if isinstance(op.get("header"), dict):
            meta.setdefault("headerConfig", {}).update(op["header"])
            touched = True
        if isinstance(op.get("footer"), dict):
            meta.setdefault("footerConfig", {}).update(op["footer"])
            touched = True
        return op if touched else None

    return None


async def _exec_read_tool(
    tool: str, args: Dict[str, Any], pages: List[Dict[str, Any]],
    user_id: str, folder_ids: Optional[List[str]],
) -> str:
    if tool == "inspect_pages":
        ids = args.get("page_ids") or []
        by_id = {p.get("id"): i for i, p in enumerate(pages)}
        if any(str(pid).lower() in ("all", "*") for pid in ids):
            ids = [p.get("id") for p in pages]
        budget = 40000
        used = 0
        blobs: List[str] = []
        omitted: List[str] = []
        for pid in ids:
            if pid not in by_id:
                continue
            p = pages[by_id[pid]]
            html = p.get("content") or ""
            # A single page larger than the whole budget would bloat every later
            # round's prompt (the scratchpad keeps it). Send an explicitly
            # LABELLED prefix instead — never a silent mid-HTML cut.
            if len(html) > budget:
                blob = json.dumps({
                    "index": by_id[pid], "id": pid, "title": p.get("title") or "",
                    "html_prefix": html[:20000], "truncated": True, "total_chars": len(html),
                    "note": "PAGE TOO LARGE for full inspection — html_prefix is the FIRST 20000 chars only. "
                            "Use patch_page with find strings from this portion; do NOT edit_page (you cannot "
                            "see the full content).",
                }, ensure_ascii=False)
            else:
                blob = json.dumps({"index": by_id[pid], "id": pid, "title": p.get("title") or "",
                                   "html": html}, ensure_ascii=False)
            if blobs and used + len(blob) > budget:
                omitted.append(str(pid))
                continue
            blobs.append(blob)
            used += len(blob)
        if not blobs:
            return "inspect_pages: no matching ids."
        result = "inspect_pages →\n[" + ",".join(blobs) + "]"
        if omitted:
            result += (
                f"\nNOT INCLUDED (size budget): {', '.join(omitted)}. Inspect the omitted ids next round "
                f"before editing them — never edit a page you haven't fully read."
            )
        return result

    # Vault data tools are deck-agnostic — reuse the deck editor's implementations.
    if tool in ("list_vault_files", "compute_data", "search_context", "search_internet"):
        return await _deck_exec_read_tool(tool, args, [], user_id, folder_ids)

    if tool == "compute_chart":
        # Same engine as the deck tool, but with report-correct embed phrasing
        # (reports embed charts in <chart-config> tags, not chart elements).
        obs = await _deck_exec_read_tool(tool, args, [], user_id, folder_ids)
        return obs.replace(
            'Embed it VERBATIM as the "chartConfig" of a chart element:',
            "Embed the JSON VERBATIM inside <chart-config>...</chart-config> tags in the page HTML:",
        )

    return f"{tool}: unknown read tool."


async def agent_edit_report_streaming(
    instruction: str,
    pages: List[Dict[str, Any]],
    user_id: str,
    current_index: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
    chat_history: Optional[List[Dict[str, Any]]] = None,
    folder_ids: Optional[List[str]] = None,
    selected_text: Optional[str] = None,
):
    """Multi-round agent loop over the report (SSE). Event types match the deck
    editor: status / operations / ask_user / finish / error / complete."""
    meta = dict(metadata or {})
    doc_pages = copy.deepcopy(pages or [])

    if not instruction or not instruction.strip():
        yield _sse({"type": "finish", "chat_message": "Tell me what you'd like to change.", "suggestions": []})
        yield _sse({"type": "complete"})
        return
    if not doc_pages:
        yield _sse({"type": "finish", "chat_message": "There are no pages to edit yet.", "suggestions": []})
        yield _sse({"type": "complete"})
        return

    review_only = _is_review_only_request(instruction) or _is_review_followup(instruction, chat_history)
    if review_only:
        logger.info("🔍 [AGENT-REPORT] review-only turn — mutations blocked")

    system_prompt = build_report_system_prompt()
    scratchpad: List[str] = []
    added_sigs: set = set()   # add_page content sigs applied THIS turn (dup guard)
    mutated_ids: set = set()  # page ids already content-edited THIS turn (anti-churn)
    consecutive_read_rounds = 0  # read-pressure guard: stop research from eating the edit budget
    tool_calls_used = 0  # total executed tool calls this turn (cap: MAX_TOOL_CALLS)
    total_ops = 0
    current_id = doc_pages[current_index].get("id") if 0 <= current_index < len(doc_pages) else None

    try:
        for round_no in range(MAX_ROUNDS):
            # TOOL-CALL BUDGET: end the turn gracefully once the model has spent
            # its executed tool calls (reads + mutations). Applied work is already
            # streamed; this just stops an endless turn.
            if tool_calls_used >= MAX_TOOL_CALLS:
                logger.info(f"🧮 [AGENT-REPORT] tool-call budget exhausted ({tool_calls_used}/{MAX_TOOL_CALLS}) — finishing")
                yield _sse({
                    "type": "finish",
                    "chat_message": "Reached the work limit for one request — applied everything so far. "
                                    "Send a follow-up to continue.",
                    "suggestions": ["Continue where you left off"],
                })
                yield _sse({"type": "complete", "operation_count": total_ops})
                return
            full_doc = _build_full_doc(doc_pages)
            if len(full_doc) <= 40000:
                overview = (
                    "FULL DOCUMENT — every page with its COMPLETE HTML (reflects all edits so far; "
                    "do NOT call inspect_pages):\n" + full_doc
                )
            else:
                overview = (
                    "DOCUMENT OVERVIEW (titles + first lines only; use inspect_pages for full HTML):\n"
                    + _build_overview(doc_pages)
                )
            cur_idx = next((i for i, p in enumerate(doc_pages) if p.get("id") == current_id), 0)
            user_prompt = _build_user_prompt(
                instruction, overview, meta, chat_history, scratchpad,
                current_index=cur_idx, current_id=current_id,
            )
            if selected_text:
                user_prompt += (
                    f"\n\nUSER SELECTION: the user has this text selected in the editor — \"this\"/\"it\" "
                    f"refers to it:\n\"{selected_text[:600]}\""
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
                    f"direction, ask_user once for the focus (with options). Ground findings in the real "
                    f"document (page numbers, quoted text, concrete proposed fixes). Then finish — include "
                    f'"Apply all suggested fixes" in suggestions when you proposed fixes. Do NOT edit anything.'
                )
            elif folder_ids:
                user_prompt += (
                    "\n\nVAULT ATTACHED: the user's vault folders are connected — this document's facts come "
                    "from them. For NEW or CHANGED factual content use the data tools (list_vault_files → "
                    "compute_data / compute_chart, search_context); never invent figures."
                )

            rnd = None
            retry_feedback = ""
            for attempt in range(4):  # parity with deck editor — retries are cheap (cache-hit)
                llm_task = asyncio.create_task(asyncio.to_thread(
                    llm_call, system_prompt, user_prompt + retry_feedback,
                    # 64K per ROUND — see agent_deck_editor: bounds overflow
                    # rounds to ~4 min; compliant ≤5-page waves fit easily.
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
                    logger.warning(f"⚠️ [AGENT-REPORT] round {round_no} unparseable (attempt {attempt + 1}/4): {e}")
                    # Truncated output ≠ malformed JSON — re-asking for valid JSON
                    # would re-attempt the same overflow. Instruct a smaller batch.
                    if "Unterminated" in str(e) or len(str(raw)) > 300_000:
                        retry_feedback = (
                            "\n\nYOUR PREVIOUS RESPONSE WAS CUT OFF — you emitted more output than fits in one "
                            "round. Do NOT retry the same batch. Emit AT MOST 3 full-page mutations in THIS "
                            "round's JSON and continue the remaining pages in later rounds. Return ONE complete, "
                            "strict JSON object."
                        )
                    else:
                        retry_feedback = (
                            "\n\nYOUR PREVIOUS RESPONSE WAS NOT VALID JSON. Return ONE complete JSON object "
                            '{"reasoning":"...","actions":[...]} — no markdown fences, no commentary.'
                        )
            if rnd is None:
                yield _sse({"type": "error", "message": "I couldn't structure that step. Please rephrase."})
                return

            if rnd["reasoning"]:
                # Show the model's full reasoning (up to 150K chars), not a 200-char teaser.
                yield _sse({"type": "status", "stage": "thinking", "round": round_no, "message": rnd["reasoning"][:150000]})

            actions = rnd["actions"]
            if not actions:
                yield _sse({"type": "finish", "chat_message": rnd["reasoning"] or "Done.", "suggestions": []})
                yield _sse({"type": "complete", "operation_count": total_ops})
                return

            round_obs: List[str] = []
            applied_ops: List[Dict[str, Any]] = []
            round_edited_ids: set = set()  # page ids content-edited THIS round
            page_muts_this_round = 0  # full-page mutations this round (wave cap: 5)
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
                    round_obs.append(await _exec_read_tool(tool, args, doc_pages, user_id, folder_ids))
                    read_used = True
                    continue
                if tool in MUTATION_TOOLS:
                    if review_only:
                        round_obs.append(
                            f"{tool}: BLOCKED — this turn is a REVIEW. Finish with findings + suggestions; "
                            f"the user approves before edits."
                        )
                        continue
                    # WAVE CAP — server-side enforcement of the MAX-5 prompt rule
                    # (see agent_deck_editor): apply the first 5 full-page
                    # mutations, defer the rest to the next round.
                    if tool in ("edit_page", "add_page"):
                        if page_muts_this_round >= 5:
                            round_obs.append(
                                f"{tool}: DEFERRED — max 5 full-page mutations per round already applied. "
                                f"Re-emit this page's mutation in the NEXT round."
                            )
                            continue
                        page_muts_this_round += 1
                    # Anti-churn HARD BLOCK: a content edit targeting a page already
                    # edited in a PREVIOUS round of this turn is the model failing to
                    # finish and redoing its own work. Reject it outright (streaming
                    # a second pass caused double work — e.g. double image changes in
                    # the deck editors); the round becomes no-progress and finishes.
                    if tool in CONTENT_EDIT_TOOLS:
                        _tgt = args.get("page_id")
                        if _tgt and _tgt in mutated_ids:
                            round_obs.append(
                                f"{tool}: BLOCKED — page {_tgt} was ALREADY edited this turn and the edit "
                                f"is applied exactly as you emitted it. Do NOT redo it. Call finish now."
                            )
                            continue
                    # Duplicate-add guard: if the model re-emits an add_page whose
                    # content was already added THIS turn (it failed to finish and
                    # looped), suppress it instead of stacking a duplicate page.
                    sig = None
                    if tool == "add_page":
                        sig = _add_page_sig(args)
                        if sig in added_sigs:
                            round_obs.append(
                                "add_page: SUPPRESSED — a page with this exact content was already added "
                                "earlier THIS TURN. Not adding a duplicate. The change is done — call finish."
                            )
                            continue
                    op = {"op": tool, **args}
                    live_idx = next((i for i, p in enumerate(doc_pages) if p.get("id") == current_id), 0)
                    cleaned = _apply_op(op, doc_pages, meta, live_idx)
                    if cleaned is not None:
                        if sig is not None:
                            added_sigs.add(sig)
                        if tool in CONTENT_EDIT_TOOLS:
                            tgt = cleaned.get("page_id") or args.get("page_id")
                            if tgt:
                                round_edited_ids.add(tgt)
                        applied_ops.append(cleaned)
                        tool_calls_used += 1
                        round_obs.append(f"{tool}: applied.")
                    elif op.get("_error") == "find_not_found":
                        round_obs.append(
                            f"patch_page: FAILED — `find` text not present in page {args.get('page_id')}. "
                            f"Re-check the exact HTML (inspect or read the FULL DOCUMENT above) and retry."
                        )
                    elif op.get("_error") == "dropped_user_media":
                        round_obs.append(
                            f"edit_page: BLOCKED — your rewrite drops the user's uploaded image(s) "
                            f"{op.get('_dropped')}. Include those <img> tags verbatim in the new html, or — "
                            f"ONLY if the user asked to remove them — remove via patch_page targeting the tag."
                        )
                    else:
                        round_obs.append(f"{tool}: invalid/ignored.")
                    continue
                round_obs.append(f"{tool}: unknown tool, ignored.")

            if applied_ops:
                total_ops += len(applied_ops)
                yield _sse({"type": "operations", "operations": applied_ops})

            # Anti-spin: a non-terminal round that applied no mutation and ran no
            # read tool made NO progress — typically the model re-emitting an
            # already-applied (now duplicate-suppressed) add_page. Re-prompting
            # would churn to MAX_ROUNDS and risk more duplicates, so finish now.
            if not terminal and not applied_ops and not read_used:
                logger.info(f"🛑 [AGENT-REPORT] round {round_no} made no progress — auto-finishing")
                yield _sse({
                    "type": "finish",
                    "chat_message": "Done." if total_ops else "No changes were needed.",
                    "suggestions": [],
                })
                yield _sse({"type": "complete", "operation_count": total_ops})
                return

            if terminal:
                tname, targs = terminal
                if tname == "ask_user":
                    yield _sse({
                        "type": "ask_user",
                        "chat_message": targs.get("question", "Could you clarify what you'd like?"),
                        "options": [o for o in (targs.get("options") or []) if isinstance(o, str)][:4],
                    })
                else:
                    suggestions = [s for s in (targs.get("suggestions") or []) if isinstance(s, str)][:3]
                    if review_only and suggestions and not any("apply" in s.lower() for s in suggestions):
                        suggestions = ["Apply all suggested fixes"] + suggestions[:2]
                    yield _sse({
                        "type": "finish",
                        "chat_message": targs.get("summary") or "Done.",
                        "suggestions": suggestions,
                    })
                yield _sse({"type": "complete", "operation_count": total_ops})
                return

            # Anti-churn: the model just content-edited a page it ALREADY edited
            # earlier this turn. It can't see the rendered page — it re-reads its
            # own HTML, judges it "still off", and edits again every round (up to
            # MAX_ROUNDS of visible re-updates on the same page). The edit it just
            # made is applied and streamed; we stop here instead of re-prompting.
            # Different pages each round are fine — only re-touching one trips this.
            rechurn_ids = round_edited_ids & mutated_ids
            mutated_ids |= round_edited_ids
            if rechurn_ids and not terminal:
                logger.info(
                    f"🛑 [AGENT-REPORT] round {round_no} re-edited already-edited "
                    f"page(s) {sorted(rechurn_ids)} — auto-finishing to stop churn"
                )
                yield _sse({
                    "type": "finish",
                    "chat_message": "Updated the page — let me know if you'd like further changes.",
                    "suggestions": [],
                })
                yield _sse({"type": "complete", "operation_count": total_ops})
                return

            # READ-PRESSURE GUARD (see agent_deck_editor): after 3 consecutive
            # read-only rounds, warn the model how many rounds remain and to start
            # applying edits before the budget runs out.
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

            action_summary = ", ".join(a.get("tool", "?") for a in actions if isinstance(a, dict))
            entry = f"ROUND {round_no}: actions=[{action_summary}].\nObservations:\n" + "\n".join(round_obs)
            # Cap any single entry so one giant observation can't survive the
            # whole-entry trimmer below and bloat every later round.
            if len(entry) > 45000:
                entry = entry[:45000] + "\n…[observation truncated — re-read what you need with a narrower tool call]"
            scratchpad.append(entry)
            _TRIM_MARKER = "[earlier rounds trimmed]"
            trimmed = False
            while sum(len(s) for s in scratchpad) > 60000:
                drop_idx = 1 if scratchpad and scratchpad[0] == _TRIM_MARKER else 0
                if len(scratchpad) <= drop_idx + 1:
                    break
                scratchpad.pop(drop_idx)
                trimmed = True
            if trimmed and (not scratchpad or scratchpad[0] != _TRIM_MARKER):
                scratchpad.insert(0, _TRIM_MARKER)

        yield _sse({
            "type": "finish",
            "chat_message": "Made the changes I could. Let me know if you'd like more.",
            "suggestions": [],
        })
        yield _sse({"type": "complete", "operation_count": total_ops})

    except Exception as e:
        detail = str(getattr(e, "detail", "")) or str(e)
        if "insufficient_credits" in detail.lower() or "negative balance" in detail.lower():
            yield _sse({"type": "error", "status_code": 402, "message": "Insufficient credits."})
            return
        logger.error(f"❌ [AGENT-REPORT] {e}")
        yield _sse({"type": "error", "message": detail or "Edit failed."})
