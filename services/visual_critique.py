"""
visual_critique.py
==================
Vision-based critique loop for generated slides / pages.

Why this exists
---------------
The server post-processor only catches mechanical issues (text overlap,
out-of-canvas elements, low contrast against parent bg). It can't see:
  - White-text-on-dark-card collisions where parent_bg detection failed.
  - Icons rendered ON TOP of body text (different zIndex, but visually clash).
  - Charts with axis labels obscuring data.
  - SVG diagrams that look empty / clustered in one corner.
  - Stat numbers that overflow their slot at the renderer's actual font.
  - Generally "ugly" output that's technically valid JSON.

This module sends the rendered slide PNG + element JSON to a vision-capable
LLM, asks "anything broken / amateurish?", and gets back a structured
patch list the server applies to produce a fixed elements array.

How it's called
---------------
The CLIENT captures the canvas via fabric's ``toDataURL('image/png')`` after
the slide finishes rendering, then POSTs to ``/presentation/critique-slide``
with::

    {
      "elements":   [...],            # current element list
      "screenshot": "data:image/png;base64,...",
      "slide_info": {"title":"...","content_hint":"..."},  # optional context
      "canvas":     {"width":960, "height":540}
    }

The endpoint returns::

    {
      "success": true,
      "elements": [...],              # patched element list
      "patches_applied": N,
      "issues": [ "white-on-white kicker", "icon overlaps body", ... ]
    }

The client then replaces its local elements with the returned list.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Max bytes we'll send to the vision model. PNG screenshots of a single
# 960x540 slide are typically 50-150 KB. We cap at 1.5 MB to be safe and
# downscale via the Vision API's own resizing.
_MAX_SCREENSHOT_BYTES = 1_500_000


def _build_system_prompt() -> str:
    """Tight system prompt — no teaching. The model is a vision designer;
    it knows what looks bad.

    We do NOT rely on `response_format=json_object` because not every vision
    model on OpenRouter supports it (e.g. z-ai/glm-4.6v has no
    `response_format` in its supported_parameters list). The prompt
    instead demands JSON output and the parser tolerates surrounding text.
    """
    return (
        "You are a slide-design QA reviewer. You will be shown a rendered "
        "slide and its element JSON. Identify VISUAL issues and ALWAYS look "
        "for the following common failure modes (in order of importance):\n"
        "  1. TITLE / HEADING WRAPS AND OVERFLOWS its bounding box (height "
        "too small for the text at the given fontSize). When this happens "
        "the wrapped line(s) render BELOW the box and visually overlap the "
        "element immediately under it (cards, paragraphs, images). Patch "
        "fix: reduce the title's `fontSize` (e.g. 44→34) OR increase its "
        "`height` so the second line fits inside the box. Watch especially "
        "for big serif titles overlapping coloured cards/panels below.\n"
        "  2. TEXT OVERFLOWS its bounding box vertically (long paragraph "
        "in too-short height) and bleeds onto neighbours. Fix: reduce "
        "`fontSize` or increase `height`.\n"
        "  3. Two adjacent elements physically overlap in the screenshot "
        "(icon on top of text, two text blocks intersecting). Fix: move "
        "the smaller / non-essential one (`x` or `y`).\n"
        "  4. Invisible text from poor contrast against the background or "
        "card it sits on. Fix: change `fill` / `color` to a contrasting hex.\n"
        "  5. Elements clipped at the canvas edge (x<0 or x+width>960, "
        "y<0 or y+height>540). Fix: clamp position.\n"
        "  6. Garbled chart axes, broken SVG diagrams, empty cards.\n"
        "Ignore matters of taste (colour preference, font choice, layout "
        "balance unless something is genuinely broken).\n\n"
        "OUTPUT FORMAT (CRITICAL): Respond with ONE JSON object and nothing "
        "else. No prose, no markdown fences, no commentary. Start your "
        "response with `{` and end with `}`. Shape:\n"
        "{\n"
        '  "issues": [\n'
        '    {"id": "<element id or null>", "kind": "overlap|overflow|invisible|cutoff|empty|broken|other", "desc": "<short>"}\n'
        '  ],\n'
        '  "patches": [\n'
        '    {"action": "set",    "id": "<element id>", "fields": {"x":N,"y":N,"fontSize":N,"height":N,"fill":"#RRGGBB",...}},\n'
        '    {"action": "delete", "id": "<element id>"},\n'
        '    {"action": "add",    "element": {<full element with type/x/y/width/height/zIndex/...>}}\n'
        '  ]\n'
        "}\n\n"
        "Rules:\n"
        "- Only patch what's actually broken in the IMAGE. Don't restructure for taste.\n"
        "- Prefer `set` over `delete`. Prefer `delete` over `add`.\n"
        "- Keep patches minimal: change ≤6 elements total.\n"
        "- For overlap fixes, move/resize — don't change content.\n"
        "- For overflow (title or body text wrapping outside its box), "
        "set a smaller `fontSize` and/or larger `height` on the offending "
        "element. The box rendered in the screenshot is where the text was "
        "MEANT to fit; lines below it indicate overflow.\n"
        "- For invisible-text fixes, set `fill` (or `color`) to a colour "
        "that contrasts with what the text actually sits on in the image.\n"
        "- Empty `issues` and empty `patches` means the slide is fine — "
        'still return the JSON `{"issues":[],"patches":[]}`.'
    )


def _slim_element_for_prompt(el: Dict[str, Any]) -> Dict[str, Any]:
    """Strip large payloads from an element before serialising for the vision
    LLM. The model sees the visual via the screenshot — it does NOT need raw
    base64 image data, full SVG markup, or chart datasets in the JSON. It
    only needs to know each element's type, bounds, and a brief identifier
    so it can refer to it in patches.

    Without this, a single resolved image element (a ~4MB base64 data URI =
    ~2M tokens) blows the 131K context budget for the entire critique call.
    """
    if not isinstance(el, dict):
        return el
    slim = dict(el)

    # Image elements: src often holds a data:image/...;base64,... URI worth
    # 1-5 MB. Replace with a short marker.
    src = slim.get("src")
    if isinstance(src, str) and (src.startswith("data:") or len(src) > 200):
        slim["src"] = "<image data omitted — see screenshot>"

    # SVG diagrams: svgContent can be 5-20 KB of inline markup. The vision
    # model sees the rendered SVG via the screenshot; it only needs to know
    # the element exists, its bounds, and its title/kind.
    svg = slim.get("svgContent")
    if isinstance(svg, str) and len(svg) > 400:
        slim["svgContent"] = f"<svg omitted — {len(svg)} chars, see screenshot>"

    # Chart elements: chartConfig (Chart.js) carries the full dataset, labels,
    # colour arrays, options, scales — easily 500-2000 chars per chart. The
    # critique cares about VISUAL defects (axis overlap, title cutoff, legend
    # collision), not the underlying numbers. Strip the config and keep only
    # the chart type as a hint.
    chart_cfg = slim.get("chartConfig")
    if isinstance(chart_cfg, dict):
        chart_type = chart_cfg.get("type") or "chart"
        slim["chartConfig"] = f"<chart data omitted — type={chart_type}, see screenshot>"

    # imageDescription can also be very long for some generators — cap it.
    desc = slim.get("imageDescription")
    if isinstance(desc, str) and len(desc) > 200:
        slim["imageDescription"] = desc[:200] + "…"

    return slim


def _build_user_prompt(
    elements: List[Dict[str, Any]],
    slide_info: Optional[Dict[str, Any]],
    canvas: Optional[Dict[str, Any]],
) -> str:
    cw = (canvas or {}).get("width", 960)
    ch = (canvas or {}).get("height", 540)
    title = (slide_info or {}).get("title", "")
    slim_elements = [_slim_element_for_prompt(el) for el in elements]
    return (
        f"Canvas: {cw}x{ch}px. Title: {title!r}\n"
        f"Elements ({len(slim_elements)}):\n"
        f"{json.dumps(slim_elements, ensure_ascii=False)}\n\n"
        "Examine the attached screenshot for visual defects. Return the "
        "patch JSON."
    )


def _parse_screenshot(screenshot: str) -> Optional[Tuple[str, str]]:
    """Accept a data URL or a raw base64 string. Return (mime, base64_payload)
    or None if invalid / too large."""
    if not isinstance(screenshot, str) or not screenshot.strip():
        return None
    s = screenshot.strip()
    mime = "image/png"
    payload = s
    if s.startswith("data:"):
        m = re.match(r"data:([^;]+);base64,(.+)", s, re.DOTALL)
        if not m:
            return None
        mime = m.group(1)
        payload = m.group(2)
    # Rough byte-size check (base64 → ~3/4 of length)
    if len(payload) * 3 // 4 > _MAX_SCREENSHOT_BYTES:
        logger.warning(f"🖼️ [CRITIQUE] Screenshot too large ({len(payload)} b64 chars); skipping")
        return None
    return mime, payload


def _index_by_id(elements: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {el.get("id"): el for el in elements if isinstance(el, dict) and el.get("id")}


def _apply_patches(elements: List[Dict[str, Any]], patches: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """Apply the vision LLM's patches to the elements list in-place. Returns
    (new_list, patches_actually_applied)."""
    if not isinstance(patches, list):
        return elements, 0
    by_id = _index_by_id(elements)
    applied = 0
    to_delete: set = set()
    to_add: List[Dict[str, Any]] = []

    for p in patches:
        if not isinstance(p, dict):
            continue
        action = (p.get("action") or "").lower()

        if action == "set":
            target = by_id.get(p.get("id"))
            fields = p.get("fields") or {}
            if not target or not isinstance(fields, dict):
                continue
            # Only patch primitive scalar fields and dict children (chart/svg).
            # Don't let the vision model rewrite the entire element via `set`.
            ALLOWED = {
                "x", "y", "width", "height", "zIndex",
                "fill", "stroke", "strokeWidth", "opacity",
                "fontSize", "fontWeight", "fontStyle", "textAlign", "lineHeight",
                "content", "iconName", "shapeType", "rx", "ry",
                "color", "backgroundColor",
                # AI-emitted aliases — generator output is inconsistent. Some
                # slides use `text`/`color`, others use `content`/`fontColor`.
                # Accept both so contrast patches actually take effect.
                "text", "fontColor", "fontFamily", "letterSpacing", "borderRadius",
            }
            # Aliases the LLM frequently picks because it sees them in the
            # input JSON. Mirror to the canonical field so the renderer picks
            # the patched value up regardless of which name was used originally.
            ALIASES = {
                "fontColor": "color",
                "text": "content",
            }
            patched_any = False
            for k, v in fields.items():
                if k not in ALLOWED:
                    continue
                target[k] = v
                mirror = ALIASES.get(k)
                if mirror:
                    target[mirror] = v
                patched_any = True
            if patched_any:
                applied += 1

        elif action == "delete":
            eid = p.get("id")
            if eid and eid in by_id:
                to_delete.add(eid)
                applied += 1

        elif action == "add":
            new_el = p.get("element") or {}
            if isinstance(new_el, dict) and new_el.get("type") in (
                "text", "shape", "icon", "image_placeholder", "chart", "svg_diagram",
            ):
                # Required positioning fields
                if all(k in new_el for k in ("x", "y", "width", "height")):
                    if not new_el.get("id"):
                        # Use time.time() (asyncio.get_event_loop().time() was
                        # deprecated in 3.10+ and raises if no loop is running).
                        # len(to_add) ensures uniqueness across patches in this batch.
                        new_el["id"] = f"critique_add_{len(to_add)}_{int(time.time() * 1000)}"
                    if "zIndex" not in new_el:
                        new_el["zIndex"] = 25
                    to_add.append(new_el)
                    applied += 1

    new_list = [el for el in elements if not (isinstance(el, dict) and el.get("id") in to_delete)]
    new_list.extend(to_add)
    return new_list, applied


def _critique_enabled() -> bool:
    """Kill-switch for the vision/OCR critique pass.

    Set ``CRITIC_VISION_ENABLED=false`` in the service .env to disable the
    Critic AI entirely. The /presentation/critique-slide and
    /printable/critique-page endpoints then return the input elements
    unchanged with no vision LLM call — useful for verifying the
    presentation/printable composer pipeline holds up without the
    post-render polish step. Defaults to enabled.
    """
    val = os.getenv("CRITIC_VISION_ENABLED", "true").strip().lower()
    return val not in ("false", "0", "no", "off", "")


async def critique_and_patch(
    *,
    elements: List[Dict[str, Any]],
    screenshot: str,
    slide_info: Optional[Dict[str, Any]] = None,
    canvas: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run one vision-critique pass. Always returns a dict — falls back to
    the input elements unchanged on any failure so the caller is safe to
    use this on the hot path."""
    # Kill-switch: when CRITIC_VISION_ENABLED=false, return the elements
    # untouched without calling the vision model at all.
    if not _critique_enabled():
        logger.info("🖼️ [CRITIQUE] disabled via CRITIC_VISION_ENABLED — skipping vision pass")
        return {
            "elements": elements,
            "patches_applied": 0,
            "issues": [],
            "note": "visual critique disabled (CRITIC_VISION_ENABLED=false)",
        }

    parsed = _parse_screenshot(screenshot)
    if not parsed:
        return {
            "elements": elements,
            "patches_applied": 0,
            "issues": [],
            "note": "screenshot invalid or oversized — no critique performed",
        }
    mime, b64 = parsed

    # Vision call goes through the citra_llm client (VISION_BASE_URL /
    # VISION_API_KEY / VISION_MODEL env vars). Compatible with any
    # OpenAI-style multimodal endpoint:
    #   - z-ai/glm-4.6v (current default — image+text+video, NO json_object support)
    #   - qwen/qwen3-vl-32b-instruct (supports json_object)
    #   - anthropic/claude-3-5-sonnet via OpenRouter
    # We don't pass `response_format` here because glm-4.6v rejects it;
    # the prompt above demands JSON and the parser below tolerates
    # surrounding text / markdown fences.
    try:
        from citra_llm import get_vision_client, get_vision_model, get_vision_extra_body
    except ImportError:
        try:
            from citra_llm.client import get_vision_client, get_vision_model, get_vision_extra_body
        except ImportError:
            logger.warning("🖼️ [CRITIQUE] no vision client available; skipping")
            return {"elements": elements, "patches_applied": 0, "issues": [], "note": "vision client unavailable"}

    try:
        client = get_vision_client()
        model = get_vision_model()
        vision_extra_body = get_vision_extra_body()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"🖼️ [CRITIQUE] vision client init failed: {exc}; skipping")
        return {"elements": elements, "patches_applied": 0, "issues": [], "note": "vision client init failed"}

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(elements, slide_info, canvas)
    data_url = f"data:{mime};base64,{b64}"

    # Hard guard: glm-4.6v / most vision endpoints cap context at 128K tokens.
    # The user_prompt is the only variable-size input (system prompt + image
    # are bounded). Rough tokens ≈ chars / 4. If the slimmed JSON is still
    # huge (e.g. a slide with dozens of elements), truncate the elements
    # section rather than letting the vision call 400 with a 2M-token error.
    _MAX_PROMPT_CHARS = 360_000  # ~90K tokens, leaves headroom for image + system + output
    if len(user_prompt) > _MAX_PROMPT_CHARS:
        logger.warning(
            f"🖼️ [CRITIQUE] prompt too large after slimming ({len(user_prompt)} chars); "
            f"truncating elements JSON to fit the vision context window"
        )
        # Keep the canvas / title preamble; collapse elements to a brief count summary.
        cw = (canvas or {}).get("width", 960)
        ch = (canvas or {}).get("height", 540)
        title = (slide_info or {}).get("title", "")
        type_counts: Dict[str, int] = {}
        for el in elements:
            if isinstance(el, dict):
                t = el.get("type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1
        user_prompt = (
            f"Canvas: {cw}x{ch}px. Title: {title!r}\n"
            f"Elements ({len(elements)}) — element JSON too large to include, summary by type:\n"
            f"{json.dumps(type_counts, ensure_ascii=False)}\n\n"
            "Examine the attached screenshot for visual defects. Return the "
            "patch JSON. Identify offending elements by their visible content "
            "(text fragment, icon shape, chart) since IDs are not available."
        )

    try:
        _create_kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "max_tokens": 4000,
            "temperature": 0.2,
            # NB: no `response_format` — glm-4.6v doesn't list it as
            # supported on OpenRouter and will reject. The system prompt
            # demands JSON-only output and the parser below tolerates
            # surrounding markdown fences if a model adds them.
        }
        if vision_extra_body:
            _create_kwargs["extra_body"] = vision_extra_body
        response = await asyncio.to_thread(
            client.chat.completions.create,
            **_create_kwargs,
        )
        raw = (response.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"🖼️ [CRITIQUE] vision call failed: {exc}; returning original")
        return {"elements": elements, "patches_applied": 0, "issues": [], "note": f"vision call failed: {exc}"}

    if not raw:
        return {"elements": elements, "patches_applied": 0, "issues": [], "note": "empty vision response"}

    # Tolerant JSON extraction — strip ```json fences, leading prose, and
    # trailing chatter that some vision models add despite the "JSON only"
    # instruction. We try strict parse first, then a fence-strip, then
    # outermost-brace extraction.
    def _try_parse(s: str):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return None

    critique = _try_parse(raw)
    if critique is None:
        # Strip markdown fences
        stripped = raw
        if "```" in stripped:
            # Take content between the first and second triple-backtick blocks
            parts = stripped.split("```")
            for part in parts:
                p = part.strip()
                if p.startswith("json"):
                    p = p[4:].strip()
                if p.startswith("{"):
                    critique = _try_parse(p)
                    if critique is not None:
                        break
    if critique is None:
        # Outermost { ... } extraction
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            critique = _try_parse(raw[start : end + 1])
    if critique is None:
        logger.warning(f"🖼️ [CRITIQUE] vision returned non-JSON; first 200 chars: {raw[:200]!r}")
        return {"elements": elements, "patches_applied": 0, "issues": [], "note": "vision returned non-JSON"}

    issues = critique.get("issues") if isinstance(critique.get("issues"), list) else []
    patches = critique.get("patches") if isinstance(critique.get("patches"), list) else []

    new_elements, applied = _apply_patches(list(elements), patches)

    # Safety net: re-clamp positions after the vision LLM moved things.
    # `validate_element_positions` was already called during initial slide
    # generation — without re-running it here, the vision model could
    # `set` x:1200 or y:-50 and the patch would push elements off-canvas.
    # We import lazily to avoid a hard dependency on edit_orchestrator at
    # module-load time (this module also supports printable pages with
    # different canvas dims).
    cw = (canvas or {}).get("width", 960)
    ch = (canvas or {}).get("height", 540)
    try:
        from services.edit_orchestrator import CanvasConfig, validate_element_positions
        _critique_canvas = CanvasConfig(
            width=int(cw),
            height=int(ch),
            format_label=f"{cw}x{ch}",
            content_type="presentation" if cw == 960 else "printable",
        )
        validate_element_positions(new_elements, _critique_canvas)
    except Exception as _vp_exc:  # noqa: BLE001 — never block on the post-clamp
        logger.warning(f"🖼️ [CRITIQUE] post-patch position clamp failed (non-fatal): {_vp_exc}")

    logger.info(
        f"🖼️ [CRITIQUE] {len(issues)} issues, {len(patches)} patches proposed, "
        f"{applied} applied (after position re-clamp)"
    )
    if issues:
        for iss in issues[:6]:
            if isinstance(iss, dict):
                logger.info(
                    f"🖼️ [CRITIQUE] {iss.get('kind','?')} on {iss.get('id','-')}: {iss.get('desc','')}"
                )
    return {
        "elements": new_elements,
        "patches_applied": applied,
        "issues": issues,
    }


__all__ = [
    "critique_and_patch",
]
