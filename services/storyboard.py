# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
storyboard.py
=============
Deck-level / document-level design plan generated AFTER the outline but
BEFORE per-slide / per-page generation.

Why this exists
---------------
Per-slide generation calls are independent. Without a shared plan:
  - Slide 1 picks indigo+cyan; slide 3 picks orange+green → no cohesion.
  - Three consecutive slides pick bullet layouts because each one
    independently thought "this is a body slide" → no visual rhythm.
  - The narrative arc (set up → escalate → reveal → close) isn't honored.

The storyboard pass is ONE LLM call that sees the WHOLE outline and emits:
  - A deck palette + typography scale (E: design tokens)
  - A per-slide plan: intent (argument/comparison/stat_hero/data_viz/
    process/quote/closing/title), visual_mode (text/chart/svg/photo/hybrid),
    tone, and a suggested template family.

Per-slide generation then receives this plan as locked context, so:
  - Every slide's `backgroundColor` / accents come from the same palette.
  - Visual modes alternate (no 3 bullet slides in a row).
  - The LLM has a clear intent per slide → tighter, more decisive output.

Public API
----------
- :func:`generate_storyboard(outline, goal, doc_type, surface, user_id, …)`
  → returns a :class:`Storyboard` dict.

Output shape (always returned, never None — a fallback is provided when
the LLM call fails so callers never have to None-check)::

    {
      "palette": {
        "background": "#RRGGBB",        # dominant slide bg
        "surface":    "#RRGGBB",        # card / panel bg
        "accent":     "#RRGGBB",        # primary accent (titles, lines)
        "accent_alt": "#RRGGBB",        # secondary accent (charts, callouts)
        "text_strong":"#RRGGBB",        # body text on `surface`
        "text_muted": "#RRGGBB",        # captions / labels
      },
      "typography": {
        "title": 44, "subtitle": 22, "body": 15, "caption": 11
      },
      "motif": "minimal|editorial|geometric|organic",
      "slides": [
        {
          "index": 0,
          "intent": "title|argument|comparison|stat_hero|data_viz|process|quote|closing",
          "visual_mode": "text|chart|svg|photo|hybrid",
          "tone": "bold|measured|cautionary|optimistic|neutral",
          "template_family": "title|stat|bullets|chart|svg_diagram|comparison|closing",
        }, ...
      ]
    }
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from llm_oss import llm_call

logger = logging.getLogger(__name__)


# Fallback palette used when the LLM call fails — chosen to be a safe,
# professional default that looks fine across both slides and A4 pages.
_FALLBACK_PALETTE = {
    "background": "#0B1020",
    "surface":    "#F8FAFC",
    "accent":     "#0EA5E9",
    "accent_alt": "#10B981",
    "text_strong":"#0F172A",
    "text_muted": "#475569",
}

_FALLBACK_TYPOGRAPHY = {
    "title": 44, "subtitle": 22, "body": 15, "caption": 11,
}

# Background-style fallback used when the LLM call fails OR when the
# storyboard is called for a profile that requires bg images but the
# model returned no background_style block. Chosen to be a safe,
# topic-agnostic, atmospheric default that won't compete with content.
_FALLBACK_BACKGROUND_STYLE = {
    "motif": "atmospheric",
    "palette_overlay": "deep navy with soft cyan and amber accents",
    "description": (
        "Soft atmospheric photographic background with smooth gradient "
        "transitions, blurred organic shapes, and subtle bokeh light "
        "particles in deep navy with hints of muted cyan and warm amber. "
        "Purely textural — no recognizable subjects, no scenes, no text "
        "or symbols of any kind."
    ),
}


def _fallback_slide_plan(index: int, slide: Dict[str, Any], total: int) -> Dict[str, Any]:
    """Cheap heuristic so the storyboard always has a per-slide entry even
    when the LLM call fails."""
    title = (slide.get("title") or "").lower()
    is_title = (index == 0) or ("welcome" in title) or ("introduction" in title)
    is_closing = (index == total - 1) or ("takeaway" in title) or ("conclusion" in title) or ("summary" in title)
    intent = "title" if is_title else ("closing" if is_closing else "argument")
    return {
        "index": index,
        "intent": intent,
        "visual_mode": "text",
        "tone": "neutral",
        "template_family": intent,
    }


def _build_fallback_storyboard(outline: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "palette": dict(_FALLBACK_PALETTE),
        "typography": dict(_FALLBACK_TYPOGRAPHY),
        "motif": "minimal",
        "background_style": dict(_FALLBACK_BACKGROUND_STYLE),
        "slides": [_fallback_slide_plan(i, s, len(outline)) for i, s in enumerate(outline)],
    }


def _build_system_prompt() -> str:
    """One concise system prompt — no teaching, just the protocol."""
    return (
        "You are a deck designer producing a storyboard plan for a "
        "presentation/document. Given the outline, choose ONE coherent "
        "design language and a per-slide plan that gives the deck rhythm "
        "(don't put three identical intents in a row). Also derive ONE "
        "background_style description that every slide/page will use — so "
        "the deck reads as one artefact. Output JSON only.\n\n"
        'Shape:\n'
        '{\n'
        '  "palette": {\n'
        '    "background":  "#RRGGBB",  // dominant slide bg\n'
        '    "surface":     "#RRGGBB",  // card / panel bg\n'
        '    "accent":      "#RRGGBB",  // primary accent\n'
        '    "accent_alt":  "#RRGGBB",  // secondary accent\n'
        '    "text_strong": "#RRGGBB",  // body on surface\n'
        '    "text_muted":  "#RRGGBB"   // captions\n'
        '  },\n'
        '  "typography": {"title":44,"subtitle":22,"body":15,"caption":11},\n'
        '  "motif": "minimal|editorial|geometric|organic",\n'
        '  "background_style": {\n'
        '    "motif": "atmospheric|textural|architectural|abstract|natural|geometric",\n'
        '    "palette_overlay": "<colour family the bg image renders in, e.g. \\"deep navy with cyan and amber accents\\">",\n'
        '    "description": "<one-sentence photographic prompt that EVERY slide will use, varied per slide but with this exact visual language — NO TEXT/LABELS/WORDS in the image>"\n'
        '  },\n'
        '  "slides": [\n'
        '    {"index":0,"intent":"title|argument|comparison|stat_hero|data_viz|process|quote|closing","visual_mode":"text|chart|svg|photo|hybrid","tone":"bold|measured|cautionary|optimistic|neutral","template_family":"title|stat|bullets|chart|svg_diagram|comparison|closing"}\n'
        '  ]\n'
        '}\n\n'
        'The background_style description MUST be topic-agnostic (atmospheric / '
        'textural / abstract), have NO words or letters or labels in the image, '
        'and use the same colour family as the palette so it sits behind '
        'content without competing. Think editorial magazine spread — every '
        'page has the same texture, only the focal subject changes.'
    )


def _build_user_prompt(outline: List[Dict[str, Any]], goal: str, doc_type: str, surface: str) -> str:
    items = []
    for i, s in enumerate(outline):
        items.append({
            "i": i,
            "title": (s.get("title") or "").strip()[:120],
            "hint": (s.get("content_hint") or s.get("outline") or "").strip()[:240],
        })
    return (
        f"Surface: {surface} ({'16:9 slide' if surface == 'presentation' else 'A4 page'})\n"
        f"Type: {doc_type}\n"
        f"Goal: {goal[:400]}\n\n"
        f"Outline ({len(outline)} {('slides' if surface == 'presentation' else 'pages')}):\n"
        f"{json.dumps(items, ensure_ascii=False)}\n\n"
        f"Return one storyboard JSON. Vary intent + visual_mode across the "
        f"deck for visual rhythm. The palette must work for ALL slides — "
        f"don't pick a colour that clashes with any of the topics."
    )


def _merge_slide_plans(parsed: List[Dict[str, Any]], outline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Patch up missing entries with the heuristic fallback so callers
    always get exactly len(outline) slide plans in index order."""
    by_index: Dict[int, Dict[str, Any]] = {}
    for sp in parsed if isinstance(parsed, list) else []:
        if not isinstance(sp, dict):
            continue
        try:
            idx = int(sp.get("index"))
        except (TypeError, ValueError):
            continue
        by_index[idx] = sp
    return [by_index.get(i, _fallback_slide_plan(i, outline[i], len(outline))) for i in range(len(outline))]


async def generate_storyboard(
    *,
    outline: List[Dict[str, Any]],
    goal: str,
    doc_type: str = "informative",
    surface: str = "presentation",  # "presentation" | "printable"
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate the deck-level storyboard. Always returns a valid dict —
    falls back to safe defaults on any LLM failure so callers can
    unconditionally pass it into per-slide generation."""
    if not outline:
        return _build_fallback_storyboard(outline)

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(outline, goal, doc_type, surface)

    try:
        raw = await asyncio.to_thread(
            llm_call,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            user_id=user_id,
            max_tokens=4000,
            temperature=0.4,
            json_mode=True,
            tier="large",
            reasoning_effort="low",
        )
        if not raw or not raw.strip():
            logger.warning("📐 [STORYBOARD] LLM returned empty; using fallback")
            return _build_fallback_storyboard(outline)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Best-effort extraction if the LLM wrapped the JSON
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end > start:
                data = json.loads(raw[start : end + 1])
            else:
                raise

        if not isinstance(data, dict):
            logger.warning("📐 [STORYBOARD] non-dict response; using fallback")
            return _build_fallback_storyboard(outline)

        palette = data.get("palette") if isinstance(data.get("palette"), dict) else {}
        # Merge with fallback so every required key is present
        palette = {**_FALLBACK_PALETTE, **{k: v for k, v in palette.items() if isinstance(v, str) and v.startswith("#")}}

        typography = data.get("typography") if isinstance(data.get("typography"), dict) else {}
        typography = {**_FALLBACK_TYPOGRAPHY, **{k: int(v) for k, v in typography.items() if isinstance(v, (int, float))}}

        motif = data.get("motif") if isinstance(data.get("motif"), str) else "minimal"

        # Background style — deck-wide visual language for the bg image
        # on every slide. Falls back to a safe atmospheric default so
        # corporate-profile slides always have something coherent to use.
        bg = data.get("background_style") if isinstance(data.get("background_style"), dict) else {}
        background_style = {
            "motif": bg.get("motif") if isinstance(bg.get("motif"), str) else _FALLBACK_BACKGROUND_STYLE["motif"],
            "palette_overlay": bg.get("palette_overlay") if isinstance(bg.get("palette_overlay"), str) else _FALLBACK_BACKGROUND_STYLE["palette_overlay"],
            "description": bg.get("description") if isinstance(bg.get("description"), str) and bg.get("description").strip() else _FALLBACK_BACKGROUND_STYLE["description"],
        }

        slide_plans = _merge_slide_plans(data.get("slides"), outline)

        logger.info(
            f"📐 [STORYBOARD] palette={palette['background']}/{palette['accent']} "
            f"motif={motif} bg_motif={background_style['motif']} "
            f"slides_planned={len(slide_plans)}"
        )
        return {
            "palette": palette,
            "typography": typography,
            "motif": motif,
            "background_style": background_style,
            "slides": slide_plans,
        }

    except Exception as exc:  # noqa: BLE001 — never block deck gen on storyboard
        logger.warning(f"📐 [STORYBOARD] generation failed ({exc}); using fallback")
        return _build_fallback_storyboard(outline)


def render_for_prompt(storyboard: Optional[Dict[str, Any]], slide_index: int) -> str:
    """Format the storyboard slice for one slide into a compact prompt
    block. Returns "" when no storyboard is supplied."""
    if not isinstance(storyboard, dict):
        return ""
    palette = storyboard.get("palette") or {}
    typography = storyboard.get("typography") or {}
    motif = storyboard.get("motif") or ""
    background_style = storyboard.get("background_style") or {}
    slides = storyboard.get("slides") or []
    plan = next((s for s in slides if isinstance(s, dict) and s.get("index") == slide_index), {})
    if not plan and 0 <= slide_index < len(slides):
        plan = slides[slide_index]
    if not isinstance(plan, dict):
        plan = {}
    bits = []
    if palette:
        bits.append(
            "Deck palette: "
            + ", ".join(f"{k}={v}" for k, v in palette.items() if isinstance(v, str))
        )
    if typography:
        bits.append("Type scale: " + ", ".join(f"{k}={v}" for k, v in typography.items()))
    if motif:
        bits.append(f"Motif: {motif}")
    if background_style:
        bg_bits = []
        if background_style.get("motif"):
            bg_bits.append(f"motif={background_style['motif']}")
        if background_style.get("palette_overlay"):
            bg_bits.append(f"palette={background_style['palette_overlay']}")
        if bg_bits:
            bits.append("Deck bg style (every slide uses this language): " + ", ".join(bg_bits))
        if background_style.get("description"):
            bits.append(f"Deck bg description (apply to this slide too, vary the scene): \"{background_style['description']}\"")
    if plan:
        bits.append(
            f"This slide — intent: {plan.get('intent','?')}, "
            f"visual_mode: {plan.get('visual_mode','?')}, "
            f"tone: {plan.get('tone','?')}, "
            f"template_family: {plan.get('template_family','?')}"
        )
    return "\n".join(bits)


__all__ = [
    "generate_storyboard",
    "render_for_prompt",
]
