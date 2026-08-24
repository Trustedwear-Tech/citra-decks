# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Presentation API - AI-powered presentation generation endpoints

This module provides endpoints for generating presentation outlines, slides,
styles, and images using LLM multimodal capabilities.

Endpoints:
- POST /presentation/generate-outline - Generate slide outline from goal
- POST /presentation/generate-style - Generate AI style/theme
- POST /presentation/generate-slide - Generate single slide content
- POST /presentation/generate-image - Generate image using vision API
- POST /presentation/enhance-slide - AI enhancement for existing slide
- POST /presentation/save - Save presentation to MongoDB
- GET /presentation/load - Load presentation from MongoDB
- GET /presentation/list - List user's presentations
"""

from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from pydantic import BaseModel, Field
from citra_auth import get_secure_user_id
import logging
import os
import json
import ast
import asyncio
import copy
from llm_oss import llm_call as _llm_call_base, llm_call_streaming as _llm_call_streaming_base
import time
import uuid
from datetime import datetime
import re

# Presentation stays on GLM-5.1 even though the platform large tier now defaults
# to deepseek-v4-pro (see Citra-Service/.env LLM_LARGE_MODEL). Pin via
# PRESENTATION_LLM_MODEL; when a caller passes model=None on the large tier we
# substitute the pinned model so every large-tier presentation call routes to
# GLM-5.1 without touching individual call sites. base_url/api_key still come
# from the LLM_LARGE_* tier config.
_SURFACE_LLM_MODEL = os.getenv("PRESENTATION_LLM_MODEL", "z-ai/glm-5.1").strip()


def llm_call(*args, model=None, tier="large", **kwargs):
    if model is None and tier == "large":
        model = _SURFACE_LLM_MODEL or None
    return _llm_call_base(*args, model=model, tier=tier, **kwargs)


def llm_call_streaming(*args, model=None, tier="large", **kwargs):
    if model is None and tier == "large":
        model = _SURFACE_LLM_MODEL or None
    return _llm_call_streaming_base(*args, model=model, tier=tier, **kwargs)

# Unified edit orchestrator
from services.edit_orchestrator import (
    PRESENTATION_CANVAS,
    enhance_page_legacy as _orchestrator_enhance_slide_legacy,
    orchestrate_edit, orchestrate_edit_streaming,
    orchestrate_all_edits as _orchestrator_orchestrate_all_edits,
    orchestrate_all_edits_streaming as _orchestrator_orchestrate_all_edits_streaming,
    enhance_image_element as _orchestrator_enhance_image,
    enhance_single_element as _orchestrator_enhance_single,
    enhance_multiple_elements as _orchestrator_enhance_multi,
    generate_chart_data as _orchestrator_generate_chart,
    validate_element_positions,
)
from services.agent_deck_editor import agent_edit_deck_streaming, agent_edit_deck, agent_edit_deck_loop_streaming

# Structured data: schema-only previews from structured_file_metadata.
# Per-row data is no longer pre-fetched here — slide LLMs see the schema +
# 3 sample values per column. For computed chart values, callers should hit
# the composer/generate-chart endpoint, which routes through execute_code.
# For inline scalar facts (single numbers, top-N, aggregates) embedded in
# slide text, the slide LLM can call `compute_fact` (vault-only sandbox).
try:
    from services.structured_file_listing import (
        list_structured_files,
        format_schema_preview_for_prompt,
    )
    STRUCTURED_DATA_AVAILABLE = True
except ImportError:
    STRUCTURED_DATA_AVAILABLE = False

from services.compute_fact_tool import (
    build_compute_fact_tool_schema,
    make_compute_fact_dispatcher,
    COMPUTE_FACT_ROUTING_RULE,
)

# Data filler: resolves _data_request placeholders the slide LLM emits when it
# needs file-backed values. Kept as a fallback safety net for any leftover
# placeholders; the primary grounding path is now the prefetch-then-generate
# planner below.
try:
    from services.structured_data_filler import fill_data_requests
    DATA_FILLER_AVAILABLE = True
except ImportError:
    DATA_FILLER_AVAILABLE = False

# Prefetch-then-generate planner: at slide-gen time, plan the aggregations this
# slide needs against the user's structured files, run them in the sandbox, and
# inject the real numbers into the prompt so the slide LLM never has to invent
# chart datasets / stats / lists.
try:
    from services.structured_data_planner import plan_and_compute, format_for_page
    DATA_PLANNER_AVAILABLE = True
except ImportError:
    DATA_PLANNER_AVAILABLE = False


async def _fetch_structured_schema_context(
    user_id: str,
    folder_ids: Optional[List[str]] = None,
    *,
    log_prefix: str = "PRESENTATION",
    slide_info: Optional[Dict[str, Any]] = None,
    user_query: Optional[str] = None,
) -> str:
    """Return a schema-preview block ready to inject into the slide prompt,
    optionally enriched with a COMPUTED DATA block produced by the data planner.

    When ``slide_info`` and ``user_query`` are provided AND the planner is
    available, this triggers a single ``plan_and_compute`` call scoped to the
    current slide so the slide LLM sees real numbers instead of guessing.

    Empty string if the user has no structured files in scope. Never raises.
    """
    if not STRUCTURED_DATA_AVAILABLE:
        return ""

    # Preferred path: goal-aware data overview (cached at outline time).
    # The outline endpoint computes one overview per (user, folders, files,
    # goal); every per-slide call here is a cache HIT and reuses the same
    # real-data block — no extra sandbox round-trip per slide.
    if user_query and folder_ids:
        try:
            from services.structured_data_overview import (
                get_data_overview, format_overview_for_prompt,
            )
            overview = await get_data_overview(
                user_id=user_id, folder_ids=folder_ids, goal=user_query,
                log_prefix=log_prefix,
            )
            if overview:
                block = "\n\n" + format_overview_for_prompt(overview, role="slide")
                logger.info(
                    f"🎬 [{log_prefix}] Overview block added "
                    f"({len(overview.get('source_files') or [])} files used, "
                    f"cache_hit={overview.get('cache_hit', False)})"
                )
                return block
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"🎬 [{log_prefix}] Overview fetch failed (will fall back): {exc}"
            )

    try:
        listing = await list_structured_files(user_id, folder_ids=folder_ids)
        entries = listing.get("entries", [])
        if not entries:
            return ""
        schema_text = format_schema_preview_for_prompt(
            entries, truncated_files=listing.get("truncated_files"),
        )
        logger.info(
            f"🎬 [{log_prefix}] Schema preview added for {len(entries)} structured file(s) (fallback)"
        )

        block = (
            "\n\nSTRUCTURED DATA AVAILABLE (schema + samples only — fallback):\n"
            f"{schema_text}\n"
            "IMPORTANT: only the column samples above are reliable. Use the "
            "COMPUTED DATA block (if present below) for any real numbers; do "
            "NOT invent numbers."
        )

        if (
            DATA_PLANNER_AVAILABLE
            and slide_info
            and user_query
            and isinstance(slide_info, dict)
        ):
            try:
                title = (
                    slide_info.get("title")
                    or slide_info.get("slide_title")
                    or slide_info.get("page_title")
                    or ""
                )
                desc = (
                    slide_info.get("content_hint")
                    or slide_info.get("description")
                    or slide_info.get("summary")
                    or slide_info.get("body")
                    or ""
                )
                single_page_outline = [{"title": title, "description": desc}]
                planner_out = await plan_and_compute(
                    user_id=user_id,
                    folder_ids=folder_ids,
                    user_query=user_query,
                    outline=single_page_outline,
                    schema_preview=schema_text,
                    log_prefix=f"{log_prefix}-DP",
                )
                computed_block = format_for_page(
                    plan=planner_out["plan"],
                    results=planner_out["results"],
                    page_index=0,
                )
                if computed_block:
                    block += "\n\n" + computed_block
                    logger.info(
                        f"🎬 [{log_prefix}] Injected COMPUTED DATA block "
                        f"({len(planner_out['plan'])} aggs, "
                        f"{sum(1 for r in planner_out['results'].values() if r.get('ok'))} ok, "
                        f"{len(planner_out.get('warnings') or [])} warnings)"
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"🎬 [{log_prefix}] data planner failed (non-blocking): {e}")

        return block
    except Exception as e:
        logger.warning(f"🎬 [{log_prefix}] Structured schema preview failed: {e}")
        return ""


def extract_json_from_response(text: str) -> str:
    """Robustly extract JSON string from AI response text."""
    text = text.strip()
    
    # 1. Try to find JSON in markdown code blocks
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                json_candidate = part[4:].strip()
                try:
                    json.loads(json_candidate)
                    return json_candidate
                except json.JSONDecodeError:
                    pass # Continue searching
            
            # Use 'braced' heuristics for unmarked code blocks
            if part.startswith("{") and part.endswith("}"):
                 try:
                    json.loads(part)
                    return part
                 except json.JSONDecodeError:
                    pass

    # 2. Heuristic Scan: Find the first substring starting with '{' that parses as valid JSON
    # This handles cases where text precedes the JSON or multiple braces exist
    for i in range(len(text)):
        if text[i] == '{':
            # Attempt to find the matching brace for THIS opening brace
            brace_count = 0
            for j in range(i, len(text)):
                if text[j] == '{':
                    brace_count += 1
                elif text[j] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        # Found a balanced block
                        candidate = text[i:j+1]
                        try:
                            json.loads(candidate)
                            return candidate
                        except json.JSONDecodeError:
                            # If balanced but invalid, maybe it's just Python syntax (None instead of null)
                            # Let 'parse_json_robustly' handle it if it's the only option,
                            # but we search for a better valid block first.
                            pass 
                        break # Stop expanding this block

    # 3. Fallback: Standard balanced brace extraction from first '{' 
    start_idx = text.find('{')
    if start_idx != -1:
        brace_count = 0
        for i in range(start_idx, len(text)):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    return text[start_idx:i+1]
    
    # 4. Truncated JSON repair: close unclosed brackets/braces
    start_idx = text.find('{')
    if start_idx != -1:
        candidate = text[start_idx:]
        repaired = _repair_truncated_json(candidate)
        if repaired:
            try:
                json.loads(repaired)
                return repaired
            except json.JSONDecodeError:
                pass

    # 5. Deep Fallback: first '{' to last '}'
    if start_idx != -1:
        end_idx = text.rfind('}')
        if end_idx != -1 and end_idx > start_idx:
            return text[start_idx:end_idx+1]
            
    return text


def _repair_truncated_json(text: str) -> Optional[str]:
    """
    Attempt to repair truncated JSON by closing unclosed strings, brackets, and braces.
    Returns the repaired string or None if repair is not feasible.
    """
    in_string = False
    escape = False
    open_stack = []  # stack of '{' and '['
    last_complete_pos = -1

    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            open_stack.append(ch)
        elif ch == '}':
            if open_stack and open_stack[-1] == '{':
                open_stack.pop()
                if not open_stack:
                    last_complete_pos = i
        elif ch == ']':
            if open_stack and open_stack[-1] == '[':
                open_stack.pop()
                if not open_stack:
                    last_complete_pos = i

    if not open_stack:
        return text  # Already balanced

    # Truncate to the end of the last complete value in a list/object
    # Find the last comma or colon at the truncation boundary to remove partial values
    repair = text
    if in_string:
        repair += '"'

    # Close all open brackets/braces in reverse order
    for bracket in reversed(open_stack):
        if bracket == '{':
            # Remove trailing partial key-value (after last comma or opening brace)
            last_comma = repair.rfind(',')
            last_open = repair.rfind('{')
            cut_pos = max(last_comma, last_open)
            if cut_pos > 0:
                # Check if content after cut_pos looks like a partial value
                after = repair[cut_pos + 1:].strip()
                if after and not after.endswith('}') and not after.endswith(']') and not after.endswith('"'):
                    repair = repair[:cut_pos + 1] if repair[cut_pos] == '{' else repair[:cut_pos]
            repair += '}'
        elif bracket == '[':
            last_comma = repair.rfind(',')
            last_open = repair.rfind('[')
            cut_pos = max(last_comma, last_open)
            if cut_pos > 0:
                after = repair[cut_pos + 1:].strip()
                if after and not after.endswith('}') and not after.endswith(']') and not after.endswith('"'):
                    repair = repair[:cut_pos + 1] if repair[cut_pos] == '[' else repair[:cut_pos]
            repair += ']'

    return repair


def _extract_all_slide_objects(raw_response: str) -> list:
    """
    Extract all complete slide-like JSON objects from a (possibly truncated) response.
    Scans for balanced {...} blocks that contain 'title' or 'content_hint' keys.
    """
    slides = []
    i = 0
    # Skip the outermost object opening — look inside the slides array
    slides_marker = '"slides"'
    marker_pos = raw_response.find(slides_marker)
    if marker_pos != -1:
        # Start scanning after the '[' that follows "slides":
        bracket_pos = raw_response.find('[', marker_pos)
        if bracket_pos != -1:
            i = bracket_pos + 1

    while i < len(raw_response):
        if raw_response[i] == '{':
            brace_count = 0
            for j in range(i, len(raw_response)):
                if raw_response[j] == '{':
                    brace_count += 1
                elif raw_response[j] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        candidate = raw_response[i:j+1]
                        try:
                            obj = json.loads(candidate)
                            if isinstance(obj, dict) and ('title' in obj or 'content_hint' in obj):
                                slides.append(obj)
                        except json.JSONDecodeError:
                            pass
                        i = j + 1
                        break
            else:
                # Unbalanced — no more complete objects
                break
        else:
            i += 1

    if slides:
        logger.info(f"🌊 [PRESENTATION] Extracted {len(slides)} slide objects from raw response")
    return slides


def parse_json_robustly(json_str: str) -> Dict[str, Any]:
    """
    Attempt to parse JSON string, handling common LLM formatting errors
    like single quotes, Python booleans, etc.
    """
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning("⚠️ [JSON] Standard parse failed, attempting strict repair (Python eval)...")
        try:
            # Prepare string for ast.literal_eval (handle JS/JSON -> Python types)
            # Replaces null->None, true->True, false->False (if lowercase)
            # Only safe if the string structure is basically a dict
            safe_str = json_str.replace('null', 'None').replace('true', 'True').replace('false', 'False')
            return ast.literal_eval(safe_str)
        except Exception as e:
            # LOG THE FAILING CONTENT
            preview = json_str[:1000] if json_str else "EMPTY_STRING"
            logger.error(f"❌ [JSON] Robust parse failed: {e}")
            logger.error(f"❌ [JSON] CONTENT PREVIEW: {preview}")
            raise


def _normalize_icon_fields(elements):
    """
    Normalize icon elements: if AI sends 'icon' instead of 'iconName', fix it.
    Also handles children recursively.
    """
    for elem in elements:
        etype = elem.get("type", "")
        if isinstance(etype, str) and etype.lower() == "icon":
            # If AI used 'icon' field instead of 'iconName', normalize it
            if "icon" in elem and "iconName" not in elem:
                elem["iconName"] = elem.pop("icon")
        # Also normalize iconName in card elements that may use 'icon' instead
        if isinstance(etype, str) and etype.lower() == "card":
            if "icon" in elem and "iconName" not in elem:
                elem["iconName"] = elem.pop("icon")
        # Recurse into children
        if isinstance(elem.get("children"), list):
            _normalize_icon_fields(elem["children"])


def _fix_numbered_step_numbers(elements):
    """
    Auto-assign sequential numbers to numbered_step elements.
    Handles AI inconsistency where it sends 'index' instead of 'number',
    or omits both fields entirely.
    Processes each nesting level independently (children get their own sequence).
    """
    step_counter = 0
    for elem in elements:
        etype = elem.get("type", "").lower() if isinstance(elem.get("type"), str) else ""
        if etype == "numbered_step":
            step_counter += 1
            # Normalize: accept 'index' as alias for 'number'
            if "index" in elem and "number" not in elem:
                elem["number"] = elem.pop("index")
            # If still no number, auto-assign based on sibling order
            if "number" not in elem:
                elem["number"] = step_counter
        # Recurse into children (separate numbering scope per group)
        if isinstance(elem.get("children"), list):
            _fix_numbered_step_numbers(elem["children"])


# ==================== AI-Powered Chart Fix ====================

_VALID_CHART_TYPES = {"bar", "line", "pie", "doughnut", "radar", "polarArea", "scatter", "bubble"}

_CHART_DEMO_FALLBACK = {
    "type": "bar",
    "data": {
        "labels": ["Item 1", "Item 2", "Item 3"],
        "datasets": [{"label": "Data", "data": [10, 20, 15],
                       "backgroundColor": ["#3B82F6", "#10B981", "#F59E0B"]}]
    }
}


def _is_chart_valid(chart_config: dict) -> bool:
    """Check if a chartConfig is structurally valid for Chart.js rendering."""
    if not isinstance(chart_config, dict) or not chart_config:
        return False
    if chart_config.get("type") not in _VALID_CHART_TYPES:
        return False
    data = chart_config.get("data")
    if not isinstance(data, dict):
        return False
    labels = data.get("labels")
    datasets = data.get("datasets")
    if not isinstance(labels, list) or not labels:
        return False
    if not isinstance(datasets, list) or not datasets:
        return False
    if not isinstance(datasets[0], dict) or not datasets[0].get("data"):
        return False
    return True


async def _fix_malformed_charts_with_ai(data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """Detect chart elements flagged as malformed by _validate_chart_config and ask AI to
    generate valid, contextually appropriate chartConfig. Falls back to demo data on failure."""
    elements = data.get("elements", [])
    charts_to_fix = [(i, el) for i, el in enumerate(elements)
                     if el.get("type") == "chart"
                     and isinstance(el.get("chartConfig"), dict)
                     and el["chartConfig"].get("_ai_fix_needed")]

    if not charts_to_fix:
        return data

    chart_ids = [el.get("id") for _, el in charts_to_fix]
    logger.warning(f"📊 [PRESENTATION] {len(charts_to_fix)} malformed chart(s) detected ({chart_ids}), requesting AI fix...")

    # Clean internal flags before sending to AI
    for _, el in charts_to_fix:
        el["chartConfig"].pop("_ai_fix_needed", None)

    system_prompt = (
        "You are a Chart.js configuration expert. You will receive a slide JSON with chart elements "
        "that have placeholder/demo chartConfig because the original AI-generated config was malformed.\n\n"
        "Generate valid, contextually appropriate Chart.js chartConfig for each chart element ID listed.\n\n"
        "Rules:\n"
        "- type: one of bar, line, pie, doughnut, radar, polarArea, scatter, bubble\n"
        "- data.labels: array of descriptive strings (3-6 items)\n"
        "- data.datasets: array with at least one object containing label (string), data (numbers array), backgroundColor (array of hex color strings)\n"
        "- Infer what the chart should show from the slide title and surrounding text elements\n"
        "- Make the data realistic and relevant to the topic\n"
        "- Do NOT include any extra keys like _ai_fix_needed\n\n"
        "Return ONLY a JSON object mapping element ID to its complete chartConfig."
    )

    # Build a lightweight context (skip large fields like imageDescription)
    context_elements = []
    for el in elements:
        slim = {k: v for k, v in el.items() if k not in ("imageDescription",)}
        context_elements.append(slim)

    user_prompt = (
        f"Slide title: {data.get('title', 'Untitled')}\n\n"
        f"Slide elements:\n{json.dumps(context_elements, indent=2)}\n\n"
        f"Chart element IDs needing valid chartConfig: {json.dumps(chart_ids)}\n\n"
        f"Generate contextually relevant Chart.js chartConfig for each ID."
    )

    try:
        ai_response = await asyncio.to_thread(
            llm_call,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            user_id=user_id,
            max_tokens=4000,
            temperature=0.2,
            json_mode=True,
            tier="large",
        )

        json_str = extract_json_from_response(ai_response)
        fixes = json.loads(json_str)

        fixed_count = 0
        for _, el in charts_to_fix:
            el_id = el.get("id")
            fix = fixes.get(el_id) if isinstance(fixes, dict) else None
            if isinstance(fix, dict) and _is_chart_valid(fix):
                el["chartConfig"] = fix
                fixed_count += 1
                logger.info(f"📊 [PRESENTATION] Chart '{el_id}' fixed by AI")
            else:
                el["chartConfig"] = dict(_CHART_DEMO_FALLBACK)
                logger.warning(f"📊 [PRESENTATION] AI fix for '{el_id}' still invalid, using demo fallback")

        logger.info(f"📊 [PRESENTATION] AI chart fix: {fixed_count}/{len(charts_to_fix)} successful")

    except Exception as e:
        logger.error(f"📊 [PRESENTATION] AI chart fix failed: {e}, using demo fallback for all")
        for _, el in charts_to_fix:
            el["chartConfig"] = dict(_CHART_DEMO_FALLBACK)

    return data


def sanitize_slide_data(slide_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize slide elements to ensure visibility and prevent overflow.
    1. Fixes numbered_step sequential numbering.
    2. Recalculates heights for text/cards based on content length.
    3. Enforces color contrast for text against backgrounds.
    """
    elements = slide_data.get("elements", [])
    
    # Fix numbered_step numbering before any other processing
    _fix_numbered_step_numbers(elements)
    
    bg_color = slide_data.get("backgroundColor", "#ffffff")
    
    # Helper: Get contrast color (black/white)
    def get_contrast_color(hex_color):
        if not hex_color or not isinstance(hex_color, str) or not hex_color.startswith('#'):
            return "#000000"
        try:
            h = hex_color.lstrip('#')
            rgb = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
            luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
            return "#FFFFFF" if luminance < 0.5 else "#000000"
        except (ValueError, IndexError, TypeError):
            # best-effort: malformed hex color → default to black contrast
            return "#000000"

    slide_text_color = get_contrast_color(bg_color)

    # Helper: Check if text color has low contrast against background
    # Catches both "nearly identical" and "both dark / both light" combos,
    # and medium-grey text on dark backgrounds (the primary source of invisible body text).
    def has_low_contrast(text_hex, bg_hex):
        try:
            th = text_hex.lstrip('#')
            bh = bg_hex.lstrip('#')
            if len(th) < 6 or len(bh) < 6:
                return False
            tr = tuple(int(th[i:i+2], 16) for i in (0, 2, 4))
            br = tuple(int(bh[i:i+2], 16) for i in (0, 2, 4))
            # RGB distance check
            dist = ((tr[0]-br[0])**2 + (tr[1]-br[1])**2 + (tr[2]-br[2])**2) ** 0.5
            if dist < 60:
                return True
            # Luminance check
            t_lum = (0.299 * tr[0] + 0.587 * tr[1] + 0.114 * tr[2]) / 255
            b_lum = (0.299 * br[0] + 0.587 * br[1] + 0.114 * br[2]) / 255
            # Catch medium-grey text on dark backgrounds (#6B7280, #9CA3AF on #111827 etc.)
            # bg is dark (< 0.4), text is not bright enough (< 0.6), and luminance gap is < 0.38
            grey_on_dark = b_lum < 0.4 and t_lum < 0.6 and abs(t_lum - b_lum) < 0.38
            # Classical both-dark / both-light same-range check
            both_dark = t_lum < 0.4 and b_lum < 0.4
            both_light = t_lum > 0.6 and b_lum > 0.6
            if grey_on_dark or (both_dark and abs(t_lum - b_lum) < 0.15) or (both_light and abs(t_lum - b_lum) < 0.15):
                return True
            return False
        except (ValueError, IndexError, TypeError):
            # best-effort: malformed hex color → treat as not low-contrast
            return False

    for elem in elements:
        etype = elem.get("type", "").lower()
        
        # 1. Recalculate Heights (Text & Cards)
        if etype == "text":
            content = elem.get("content", "")
            font_size = elem.get("fontSize", 20)
            width = elem.get("width", 800)
            # Approx chars per line (avg char width ~0.6 * fontSize)
            chars_per_line = max(1, width / (font_size * 0.5)) 
            lines = max(1, len(content) / chars_per_line)
            # Add buffet for line breaks
            lines += content.count('\n') 
            min_height = int(lines * font_size * 1.5)  # 1.5 line height
            if elem.get("height", 0) < min_height:
                elem["height"] = min_height
                
        elif etype == "card":
            # Estimate card height: Title + Description + Padding
            title = elem.get("title", "")
            desc = elem.get("description", "")
            width = elem.get("width", 300)
            
            # Title height (approx 24px font)
            t_lines = max(1, len(title) / (width / 14)) # 14px char width
            t_height = t_lines * 30 
            
            # Desc height (approx 16px font)
            d_lines = max(1, len(desc) / (width / 9)) # 9px char width
            d_height = d_lines * 22
            
            min_height = int(t_height + d_height + 40) # 40px padding
            if elem.get("height", 0) < min_height:
                elem["height"] = min_height
                
        # 2. Enforce Contrast Colors
        if etype == "card":
            card_bg = elem.get("backgroundColor", "#ffffff")
            card_text_col = get_contrast_color(card_bg)
            if not elem.get("titleColor") or has_low_contrast(elem.get("titleColor", ""), card_bg):
                elem["titleColor"] = card_text_col
            if not elem.get("descriptionColor") or has_low_contrast(elem.get("descriptionColor", ""), card_bg):
                elem["descriptionColor"] = card_text_col
                
        elif etype == "numbered_step":
            if not elem.get("textColor") or has_low_contrast(elem.get("textColor", ""), bg_color):
                elem["textColor"] = slide_text_color
            if not elem.get("titleColor") or has_low_contrast(elem.get("titleColor", ""), bg_color):
                elem["titleColor"] = slide_text_color
            if not elem.get("descriptionColor") or has_low_contrast(elem.get("descriptionColor", ""), bg_color):
                elem["descriptionColor"] = slide_text_color
            # Ensure number is visible - use contrast against circle color if needed, 
            # but usually number is white on colored circle. Let's assume white.

        elif etype == "text":
            # Check 'color' field (legacy / freeform slides)
            if not elem.get("color") or has_low_contrast(elem.get("color", ""), bg_color):
                elem["color"] = slide_text_color
            # Check 'fill' field (template-built slides) — only override if contrast is bad
            fill_val = elem.get("fill", "")
            if fill_val and has_low_contrast(fill_val, bg_color):
                elem["fill"] = slide_text_color

        # 3. Validate chart data structure
        if etype == "chart":
            chart_cfg = elem.get("chartConfig")
            needs_fix = False
            if not isinstance(chart_cfg, dict) or not chart_cfg:
                needs_fix = True
            else:
                # Normalize chart type (AI sometimes returns icon names like "chart-bar")
                _valid_types = {"bar", "line", "pie", "doughnut", "radar", "polarArea", "scatter", "bubble"}
                ctype = chart_cfg.get("type", "bar")
                if ctype not in _valid_types:
                    stripped = ctype.replace("chart-", "").replace("chart_", "")
                    chart_cfg["type"] = stripped if stripped in _valid_types else "bar"
                # Fix misplaced labels/datasets (should be inside data, not root)
                if "data" not in chart_cfg and ("labels" in chart_cfg or "datasets" in chart_cfg):
                    chart_cfg["data"] = {"labels": chart_cfg.pop("labels", []), "datasets": chart_cfg.pop("datasets", [])}
                    elem["chartConfig"] = chart_cfg
                data = chart_cfg.get("data")
                if not isinstance(data, dict) or not data:
                    needs_fix = True
                else:
                    labels = data.get("labels", [])
                    datasets = data.get("datasets", [])
                    if not labels or not datasets or not isinstance(datasets[0], dict) or not datasets[0].get("data"):
                        needs_fix = True
            if needs_fix:
                elem["chartConfig"] = {
                    "type": "bar",
                    "data": {
                        "labels": ["Item 1", "Item 2", "Item 3"],
                        "datasets": [{"label": "Data", "data": [10, 20, 15], "backgroundColor": ["#3B82F6", "#10B981", "#F59E0B"]}]
                    }
                }

    return slide_data


def _estimate_text_height(elem: Dict[str, Any]) -> float:
    """
    Estimate the rendered height of a text element based on content wrapping.
    Uses the same formula as the frontend's validateTextElement for consistency.
    Adapted for 960×540 presentation canvas.
    """
    # Generator output is inconsistent: corporate-template path emits `content`,
    # legacy/general path emits `text`. Read whichever is populated so this
    # estimator (and the fit pass that depends on it) works for both.
    content = elem.get("content") or elem.get("text") or ""
    if not content:
        return elem.get("height", 60)
    
    font_size = elem.get("fontSize", 20)
    line_height = elem.get("lineHeight", 1.4)
    width = elem.get("width", 400)
    char_width_ratio = 0.48  # Unified with frontend's charWidthRatio
    
    chars_per_line = max(1, int(width / (font_size * char_width_ratio)))
    
    # Count lines including explicit newlines
    content_lines = content.split('\n')
    total_lines = 0
    for line in content_lines:
        total_lines += max(1, -(-len(line) // chars_per_line))  # ceil division
    
    estimated_height = total_lines * font_size * line_height
    # Only use explicit height as floor if actually specified; avoid arbitrary 60px floor
    explicit_h = elem.get("height")
    if explicit_h is not None:
        return max(estimated_height, explicit_h)
    return estimated_height


def fit_content_to_slots(slide_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post-generation pass: ensure every text element's content fits within its
    allocated pixel box by shrinking fontSize if needed.
    
    This catches cases where the AI ignores character-limit hints and generates
    content that overflows the fixed-size template slot.
    """
    elements = slide_data.get("elements", [])
    if not elements:
        return slide_data
    
    for elem in elements:
        if elem.get("type") != "text":
            continue

        # General path emits `text`, corporate path emits `content`. Accept
        # either so the fit shrink covers both — otherwise titles emitted by
        # the legacy free-form generator never get fit-checked and wrap into
        # the element below them.
        content = elem.get("content") or elem.get("text") or ""
        if not content:
            continue

        font_size = elem.get("fontSize", 20)
        width = elem.get("width", 400)
        height = elem.get("height")
        line_height = elem.get("lineHeight", 1.4)

        if height is None:
            continue  # No height constraint — skip

        # Determine minimum font size based on text type. Many legacy-path
        # slides don't set textType explicitly — infer "title" from a large
        # font size (≥30) so big headings still get a sane lower bound and
        # don't shrink to 10px body-text size.
        text_type = elem.get("textType")
        if not text_type:
            text_type = "title" if font_size >= 30 else "body"
        min_font_sizes = {
            "title": 18,
            "subtitle": 14,
            "body": 10,
        }
        min_fs = min_font_sizes.get(text_type, 10)
        
        # Iteratively shrink font until content fits
        original_fs = font_size
        while font_size > min_fs:
            elem["fontSize"] = font_size
            estimated_h = _estimate_text_height(elem)
            if estimated_h <= height:
                break
            font_size -= 1
        
        if font_size != original_fs:
            elem["fontSize"] = font_size
            logger.info(f"🔧 [FIT] Element '{elem.get('id', '?')}' fontSize {original_fs} → {font_size} "
                       f"to fit {width}x{height}px (textType={text_type})")
    
    return slide_data


def _elements_overlap_horizontally(el1: Dict, el2: Dict) -> bool:
    """Check if two elements share horizontal space."""
    l1 = el1.get("x", 0)
    r1 = l1 + el1.get("width", 100)
    l2 = el2.get("x", 0)
    r2 = l2 + el2.get("width", 100)
    return l1 < r2 and l2 < r1


def _are_in_different_columns(el1: Dict, el2: Dict) -> bool:
    """
    Detect when two elements are in clearly different visual columns of the slide.
    In multi-column layouts (e.g. content cards on the left + image on the right),
    elements in separate columns should NOT push each other down vertically.
    Uses center-X to decide: left zone (<40% of canvas) vs right zone (>60%).
    """
    CANVAS_W = 960
    cx1 = el1.get("x", 0) + el1.get("width", 100) / 2
    cx2 = el2.get("x", 0) + el2.get("width", 100) / 2

    LEFT_BOUND = CANVAS_W * 0.40    # 384px
    RIGHT_BOUND = CANVAS_W * 0.60   # 576px

    el1_left = cx1 < LEFT_BOUND
    el1_right = cx1 > RIGHT_BOUND
    el2_left = cx2 < LEFT_BOUND
    el2_right = cx2 > RIGHT_BOUND

    return (el1_left and el2_right) or (el1_right and el2_left)


def _is_side_placed_text_media(el1: Dict, el2: Dict) -> bool:
    """
    Detect when a full-width text element and a media element (chart/image)
    are in different visual zones (e.g. title spanning full width, chart on the right).
    In such layouts, horizontal bounding boxes overlap but the elements are visually
    side-by-side; pushing the text below the media creates ugly gaps.
    Returns True if the pair should be SKIPPED during overlap resolution.
    """
    CANVAS_W = 960
    FULLWIDTH_THRESHOLD = CANVAS_W * 0.7       # 672px — element spans most of the slide
    MEDIA_TYPES = {"chart", "image_placeholder"}

    t1, t2 = el1.get("type", ""), el2.get("type", "")
    w1, w2 = el1.get("width", 100), el2.get("width", 100)

    # Identify text vs media
    if t1 == "text" and t2 in MEDIA_TYPES:
        text_w, media_el = w1, el2
    elif t2 == "text" and t1 in MEDIA_TYPES:
        text_w, media_el = w2, el1
    else:
        return False  # Not a text-vs-media pair

    # Text must be full-width
    if text_w < FULLWIDTH_THRESHOLD:
        return False

    # Media must be clearly in one half of the slide (not centered)
    media_x = media_el.get("x", 0)
    media_w = media_el.get("width", 100)
    media_center = media_x + media_w / 2

    # Left-zone: center < 35% of canvas | Right-zone: center > 65% of canvas
    in_left_zone = media_center < CANVAS_W * 0.35    # < 336
    in_right_zone = media_center > CANVAS_W * 0.65   # > 624

    if not (in_left_zone or in_right_zone):
        return False  # Media is centered → genuine overlap, don't skip

    return True


def fix_overlapping_elements(slide_data: Dict[str, Any], min_gap: int = 12) -> Dict[str, Any]:
    """
    Post-process slide data to detect and fix overlapping elements.
    
    Strategy (matches printable's robust approach):
    1. Compute accurate text heights via character-wrapping estimation
    2. Fix children within cards/shapes that overflow their parent bounds (Phase 1)
    3. Sort all positionable elements by Y
    4. For each pair of vertically & horizontally overlapping elements, push the lower one down
    
    Args:
        slide_data: The slide JSON from AI generation
        min_gap: Minimum vertical gap between elements (pixels)
        
    Returns:
        Modified slide_data with corrected positions
    """
    elements = slide_data.get("elements", [])
    if not elements:
        return slide_data
    
    SAFE_BOTTOM = 470  # Don't push elements below this (540 - 70px bottom margin for safety)
    corrections_made = 0
    
    # === PHASE 1: Fix children overflow within cards/shapes ===
    for elem in elements:
        children = elem.get("children", [])
        if not children:
            continue
        
        parent_height = elem.get("height", 300)
        parent_width = elem.get("width", 300)
        text_children = [c for c in children if c.get("type") == "text"]
        
        # Sort children by relative Y
        text_children.sort(key=lambda c: c.get("y", 0))
        
        for i, child in enumerate(text_children):
            child_y = child.get("y", 0)
            child_height = _estimate_text_height(child)
            child_bottom = child_y + child_height
            
            # If child overflows parent bottom, shrink font
            padding_bottom = 12
            if child_bottom > parent_height - padding_bottom:
                available_height = max(20, parent_height - child_y - padding_bottom)
                # Reduce fontSize to fit
                content = child.get("content", "")
                if content:
                    current_fs = child.get("fontSize", 14)
                    min_fs = 11  # Keep text readable (never go below 11px)
                    while current_fs > min_fs:
                        child["fontSize"] = current_fs
                        new_h = _estimate_text_height(child)
                        if new_h <= available_height:
                            break
                        current_fs -= 1
                    child["fontSize"] = current_fs
                    corrections_made += 1
                    logger.info(f"🔧 [OVERLAP] Child '{child.get('id', '?')}' font shrunk to {current_fs}px to fit parent")
            
            # Fix child-to-child overlap within same parent
            if i > 0:
                prev_child = text_children[i - 1]
                prev_bottom = prev_child.get("y", 0) + _estimate_text_height(prev_child)
                if child_y < prev_bottom + 6:  # 6px min gap inside cards
                    child["y"] = prev_bottom + 6
                    corrections_made += 1
    
    # === PHASE 2: Fix top-level element overlaps ===
    # NOTE: "shape" intentionally excluded — shapes are backgrounds, dividers, accent
    # lines, and decorative elements. Including them causes catastrophic cascading
    # overlap fixes (e.g. a full-canvas background rect at 0,0,960,540 pushes ALL
    # content elements to y=500, making slides unusable).
    positionable_types = {"text", "card", "numbered_step", "image_placeholder", "chart"}
    positionable = [e for e in elements if e.get("type", "") in positionable_types]
    
    if len(positionable) < 2:
        if corrections_made > 0:
            logger.info(f"🔧 [OVERLAP] Total corrections: {corrections_made} (children only)")
        return slide_data
    
    # Sort by Y position
    positionable.sort(key=lambda e: e.get("y", 0))
    
    # Compute effective height for each element
    for elem in positionable:
        if elem.get("type") == "text":
            elem["_effective_height"] = _estimate_text_height(elem)
        elif elem.get("type") == "numbered_step":
            # The frontend (expandNumberedStep) renders a circle + title + optional desc
            # beside/below the circle. The API only receives the raw 'size' and 'height' fields,
            # but the actual rendered height is at minimum max(size, 80) + ~20px padding.
            # Using only elem.get("height", 60) severely underestimates and causes overlap.
            step_size = elem.get("size", 50)
            declared_h = elem.get("height", 0)
            # Buffer covers title + description text rendered alongside the circle
            estimated_h = max(declared_h, step_size, 80) + 20
            elem["_effective_height"] = estimated_h
        else:
            elem["_effective_height"] = elem.get("height", 60)
    
    # Fix overlaps — check each element against ALL previous elements (not just consecutive)
    # The old consecutive-pair check missed overlaps when non-overlapping elements
    # (at different X positions) separated overlapping ones in Y-sorted order.
    for i in range(1, len(positionable)):
        curr = positionable[i]
        curr_y = curr.get("y", 0)
        
        for j in range(i):
            prev = positionable[j]
            
            if not _elements_overlap_horizontally(prev, curr):
                continue
            
            # Skip when a full-width text and a side-placed media are in different
            # visual zones (e.g. title text spanning full width, chart on right half).
            # Without this, the text gets incorrectly pushed below the media.
            if _is_side_placed_text_media(prev, curr):
                continue

            # Skip elements in clearly different visual columns (e.g. left-side
            # cards vs right-side image). Without this, a small horizontal-overlap
            # zone between columns causes left-side content to be pushed below
            # the right-side image, creating an ugly gap.
            if _are_in_different_columns(prev, curr):
                continue
            
            prev_bottom = prev.get("y", 0) + prev.get("_effective_height", 60)
            
            if curr_y < prev_bottom + min_gap:
                new_y = round(min(prev_bottom + min_gap, SAFE_BOTTOM))
                if new_y > curr_y:
                    logger.info(f"🔧 [OVERLAP] Fixed: '{curr.get('id', '?')}' y={curr_y} → y={new_y} "
                               f"(overlaps '{prev.get('id', '?')}' bottom={prev_bottom:.0f})")
                    curr["y"] = new_y
                    curr_y = new_y  # Update for subsequent checks
                    corrections_made += 1
    
    # Clean up temp keys
    for elem in positionable:
        elem.pop("_effective_height", None)
    
    # === PHASE 3: Clamp elements whose bottom edge extends below canvas ===
    CANVAS_HEIGHT = 540
    BOTTOM_MARGIN = 20
    for elem in positionable:
        ey = elem.get("y", 0)
        eh = elem.get("height")
        if eh is not None and isinstance(ey, (int, float)) and isinstance(eh, (int, float)):
            bottom_edge = ey + eh
            if bottom_edge > CANVAS_HEIGHT - BOTTOM_MARGIN:
                # Try moving up first
                new_y = CANVAS_HEIGHT - BOTTOM_MARGIN - eh
                if new_y >= BOTTOM_MARGIN:
                    logger.info(f"🔧 [OVERLAP] Clamped '{elem.get('id', '?')}' bottom {bottom_edge} → moved y from {ey} to {new_y}")
                    elem["y"] = round(new_y)
                    corrections_made += 1
                else:
                    # Element is too tall — shrink to fit
                    max_h = CANVAS_HEIGHT - 2 * BOTTOM_MARGIN
                    logger.info(f"🔧 [OVERLAP] Clamped '{elem.get('id', '?')}' height {eh} → {max_h} (too tall for canvas)")
                    elem["y"] = BOTTOM_MARGIN
                    elem["height"] = round(max_h)
                    corrections_made += 1

    if corrections_made > 0:
        logger.info(f"🔧 [OVERLAP] Total corrections: {corrections_made} elements repositioned")
    
    return slide_data


def _compact_title_position(slide_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure the main title starts near the top of the slide.
    If the title element is too far down (e.g. y:120 when it should be ~40),
    shift ALL elements up uniformly so the title lands at TARGET_Y.
    This corrects cases where the LLM refine pass or the AI generation places
    the title lower than intended, and the overlap fixer (which only pushes
    elements DOWN) cannot pull it back up.
    """
    elements = slide_data.get("elements", [])
    if not elements:
        return slide_data

    MAX_TITLE_Y = 60   # Title should not be below y=60
    TARGET_Y = 40       # Ideal title Y position

    # Find the topmost title-type text element
    title_elem = None
    for e in elements:
        if e.get("type") != "text":
            continue
        is_title = (
            e.get("textType") == "title"
            or e.get("fontSize", 0) >= 36
            or "title" in e.get("id", "").lower()
        )
        if is_title:
            if title_elem is None or e.get("y", 999) < title_elem.get("y", 999):
                title_elem = e

    if not title_elem or title_elem.get("y", 0) <= MAX_TITLE_Y:
        return slide_data

    shift = title_elem.get("y", 0) - TARGET_Y
    if shift <= 0:
        return slide_data

    original_y = title_elem.get("y", 0)
    for e in elements:
        e["y"] = max(0, e.get("y", 0) - shift)
        # Children use relative coords — no need to adjust them

    logger.info(f"📐 [COMPACT] Title was at y={original_y}, shifted all elements up by {shift}px")
    return slide_data


# Import existing utilities

from persona import generate_persona_system_prompt
from services.image_processor import image_processor

router = APIRouter()


def _grounded_sys(base: str) -> str:
    """Prefix a system prompt with the canonical strict-grounding header.
    Used by factual content generators (slide outlines, slot fills, slide design).
    Layout-only / classifier prompts do NOT need this prefix."""
    try:
        from prompts.grounding import STRICT_GROUNDING_PROMPT, CITATION_TAGS_RULE
        return (
            STRICT_GROUNDING_PROMPT.strip()
            + "\n\n"
            + CITATION_TAGS_RULE.strip()
            + "\n\n---\n\n"
            + base
        )
    except Exception:
        return base
logger = logging.getLogger(__name__)

# Global semaphore to throttle concurrent LLM calls for slide generation
# Prevents overwhelming the API when frontend generates multiple slides in parallel
_slide_generation_semaphore = asyncio.Semaphore(3)

# MongoDB client for persistence
_mongo_db = None

def get_mongo_db():
    """Get MongoDB database connection."""
    global _mongo_db
    if _mongo_db is None:
        try:
            from citra_mongo import get_sync_database
            _mongo_db = get_sync_database()
            logger.info("🎬 [PRESENTATION] MongoDB connection established")
        except Exception as e:
            logger.error(f"🎬 [PRESENTATION] MongoDB connection failed: {e}")
            _mongo_db = None
    return _mongo_db


# ==================== Request/Response Models ====================

class GenerateOutlineRequest(BaseModel):
    goal: str = Field(..., description="Presentation goal/topic")
    presentation_type: str = Field(default="informative", description="Type: informative, persuasive, instructional, pitch, report")
    target_audience: Optional[str] = Field(default=None, description="Target audience description")
    slide_count: int = Field(default=10, ge=3, le=30, description="Number of slides to generate")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs for context")
    use_personal_data: bool = Field(default=False, description="Whether personal vault/SaaS data is enabled")
    include_supplementary: bool = Field(default=False, description="Whether to include SaaS supplementary sources")
    use_internet_search: bool = Field(default=False, description="Fetch latest data from internet and embed in vault")
    prefetched_corpus: Optional[List[dict]] = Field(
        default=None,
        description=(
            "Caller-supplied research corpus [{text, title?, source?}]. When "
            "supplied (e.g. quick/main chat already did a fast search), each "
            "entry is embedded into the vault before outline generation, so "
            "the normal outline + per-slide retrieval grounds the deck on it "
            "— no deep-research sandbox spawn needed."
        ),
    )
    existing_outline: Optional[List[dict]] = Field(default=None, description="Existing slide outline [{title, outline}] to refine rather than regenerate from scratch")
    deck_profile: str = Field(
        default="corporate",
        description=(
            "Single routing axis. 'corporate' → matcher picks a template from "
            "the executive catalog, then slot-fill generation runs. 'general' "
            "→ template path skipped entirely, LLM designs each slide from "
            "scratch via the legacy free-form generator."
        ),
    )


class SlideOutline(BaseModel):
    title: str
    content_hint: str
    layout: str = "title_content"
    image_prompt: Optional[str] = None


class GenerateOutlineResponse(BaseModel):
    success: bool
    slides: List[Dict[str, Any]]
    message: Optional[str] = None


class GenerateStyleRequest(BaseModel):
    prompt: str = Field(..., description="Style description prompt")


class StyleDefinition(BaseModel):
    name: str
    fontFamily: str
    textPrimary: str
    textSecondary: str
    accentColor: str
    slideBackground: str
    preview: Dict[str, str]


class GenerateSlideRequest(BaseModel):
    slide_info: Dict[str, Any] = Field(..., description="Slide outline information")
    slide_index: int = Field(..., description="Index of this slide in presentation")
    total_slides: int = Field(..., description="Total number of slides")
    presentation_goal: str = Field(..., description="Overall presentation goal")
    presentation_type: str = Field(default="informative", description="Presentation type")
    style: Optional[Dict[str, Any]] = Field(default=None, description="Style definition")
    template_id: Optional[str] = Field(default=None, description="Template ID for template-based generation")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs")
    previous_slides: Optional[List[Dict[str, Any]]] = Field(default=None, description="Previous slides for context")
    images_remaining: int = Field(default=3, description="Number of images still available in budget (max 3)")
    icon_set: str = Field(default="lucide", description="Icon set to use: lucide, ionicons")
    special_instructions: Optional[str] = Field(default=None, description="User guidance for AI: style preferences, data to include, formatting, etc.")
    use_personal_data: bool = Field(default=False, description="Whether personal vault/SaaS data is enabled")
    include_supplementary: bool = Field(default=False, description="Whether to include SaaS supplementary sources")
    generation_quality: Optional[str] = Field(default="premium", description="Quality of generation for images: premium, medium, basic")
    structured_data_context: Optional[str] = Field(default=None, description="Pre-fetched structured data context from outline prefetch")
    prefetched_vault_block: Optional[str] = Field(
        default=None,
        description=(
            "Pre-fetched per-slide vault passages block (from "
            "/presentation/prefetch-vault-chunks). When supplied, this slide "
            "generation call skips its own /embeddings + Milvus + Mongo "
            "round-trip — the deck-level prefetch already paid that cost in "
            "a single batched embed."
        ),
    )
    deck_plan: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Deck-level storyboard produced by /presentation/generate-outline-stream "
            "(SSE event type=storyboard). Contains the deck's palette, typography "
            "scale, motif, and a per-slide plan (intent / visual_mode / tone / "
            "template_family). When supplied, the per-slide prompt is grounded "
            "in the deck's design language so slides cohere visually."
        ),
    )
    deck_profile: str = Field(
        default="corporate",
        description=(
            "Single routing axis. 'corporate' → template path. 'general' → "
            "legacy free-form path (LLM designs the slide from scratch)."
        ),
    )


class GenerateImageRequest(BaseModel):
    prompt: str = Field(..., description="Image generation prompt")
    style: Optional[str] = Field(default="professional", description="Image style")


class EnhanceSlideRequest(BaseModel):
    slide_id: str = Field(..., description="Slide ID")
    slide_content: Dict[str, Any] = Field(..., description="Current slide content")
    instruction: str = Field(..., description="Enhancement instruction")
    style: Optional[Dict[str, Any]] = Field(default=None, description="Style definition")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs for context")
    template_id: Optional[str] = Field(default=None, description="Template ID for template-based slides")
    presentation_goal: Optional[str] = Field(default=None, description="Overall presentation goal for context")
    presentation_type: str = Field(default="informative", description="Presentation type: informative, persuasive, instructional, pitch, report")
    icon_set: str = Field(default="lucide", description="Icon set to use: lucide, ionicons")
    skip_vault: bool = Field(default=False, description="Whether to skip vault retrieval (for simple edits)")
    generation_quality: Optional[str] = Field(default="premium", description="Quality of generation for images: premium, medium, basic")
    is_update_all: bool = Field(default=False, description="True for 'Update All' (vault refresh), False for 'Edit All' (user instruction only)")
    deck_profile: str = Field(
        default="corporate",
        description=(
            "Single routing axis. 'corporate' → template-based edit. "
            "'general' → legacy free-form edit (LLM redesigns the slide)."
        ),
    )
    deck_plan: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Deck-level storyboard (palette / typography / per-slide intent). Threaded into the edit prompt so edits stay coherent with the rest of the deck.",
    )


class OrchestrateRequest(BaseModel):
    instruction: str = Field(..., description="User's natural language instruction")
    slide_content: Dict[str, Any] = Field(..., description="Current slide content")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs")
    # New fields for direct execution
    slide_id: Optional[str] = Field(default=None, description="Slide ID for enhancement")
    style: Optional[Dict[str, Any]] = Field(default=None, description="Style definition")
    template_id: Optional[str] = Field(default=None, description="Template ID for template-based slides")
    # Selection mode fields
    edit_mode: str = Field(default='slide', description="'slide' for full slide, 'element' for single, 'multi' for multiple")
    selected_elements: Optional[List[Dict[str, Any]]] = Field(default=None, description="Array of selected elements to edit")
    # Overall presentation context
    presentation_goal: Optional[str] = Field(default=None, description="Overall presentation goal for context")
    presentation_type: str = Field(default="informative", description="Presentation type: informative, persuasive, instructional, pitch, report")
    icon_set: str = Field(default="lucide", description="Icon set to use: lucide, ionicons")
    # Agentic scope field
    user_edit_scope: str = Field(default='page', description="Frontend radio: 'element', 'page', 'all'")
    generation_quality: Optional[str] = Field(default="premium", description="Quality of generation for images: premium, medium, basic")
    fast_path: Optional[str] = Field(default=None, description="Skip classification: 'layout_fix' for direct page enhancement")
    # Document context for single-slide edits
    slides_summary: Optional[List[Dict[str, Any]]] = Field(default=None, description="Lightweight slide summaries for document-level context")
    deck_profile: str = Field(
        default="corporate",
        description="'corporate' → template path. 'general' → legacy free-form path.",
    )
    deck_plan: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Deck-level storyboard threaded into the edit prompt so edits stay coherent with the rest of the deck.",
    )


class OrchestrateResponse(BaseModel):
    success: bool = Field(default=True, description="Success status")
    intent: str = Field(..., description="Classified intent: simple_edit, data_addition, chart_request")
    requires_vault: bool = Field(default=False, description="Whether vault data is needed")
    
    # Direct execution results
    enhanced_slide: Optional[Dict[str, Any]] = Field(default=None, description="Result of enhance_slide if applicable")
    enhanced_element: Optional[Dict[str, Any]] = Field(default=None, description="Result of single element edit")
    enhanced_elements: Optional[List[Dict[str, Any]]] = Field(default=None, description="Result of multi-element edit")
    chart_config: Optional[Dict[str, Any]] = Field(default=None, description="Result of generate_chart_data if applicable")
    
    # Legacy/Meta fields
    chart_type: Optional[str] = Field(default=None, description="Chart type if chart_request")
    chart_query: Optional[str] = Field(default=None, description="Query for chart data generation")


class OrchestrateAllRequest(BaseModel):
    """Request for smart all-slides orchestration (single API call replaces N individual calls)"""
    instruction: str = Field(..., description="User's natural language instruction")
    slides_summary: List[Dict[str, Any]] = Field(..., description="Lightweight summaries: [{slide_index, slide_id, text_summary, element_types, title}]")
    full_slides: List[Dict[str, Any]] = Field(..., description="Complete slide data for all slides")
    current_slide_index: int = Field(default=0, description="Currently viewed slide index")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs")
    style: Optional[Dict[str, Any]] = Field(default=None, description="Style definition")
    presentation_goal: Optional[str] = Field(default=None, description="Overall presentation goal")
    presentation_type: str = Field(default="informative", description="Presentation type")
    icon_set: str = Field(default="lucide", description="Icon set to use")
    is_update_all: bool = Field(default=False, description="True for Update All (vault refresh with image regeneration), False for Edit All (user instruction only)")
    outline_changed: bool = Field(default=False, description="True when outlines were regenerated — triggers template re-matching")
    deck_profile: str = Field(
        default="corporate",
        description="'corporate' → template re-matching per slide. 'general' → legacy free-form per slide.",
    )
    deck_plan: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Deck-level storyboard threaded into every per-slide edit prompt so all edits stay storyboard-coherent.",
    )


class AgentEditRequest(BaseModel):
    """Agentic whole-deck edit — the entire deck is sent in one shot and the LLM
    decides what to change, returning a list of operations. Replaces the old
    scope-selected single/multi/all edit flow."""
    instruction: str = Field(..., description="User's natural-language chat message")
    slides: List[Dict[str, Any]] = Field(..., description="The ENTIRE deck — every slide with full elements (images as markers)")
    current_slide_index: int = Field(default=0, description="Index of the slide the user is viewing")
    style: Optional[Dict[str, Any]] = Field(default=None, description="Deck style/theme")
    header_footer: Optional[Dict[str, Any]] = Field(default=None, description="Header/footer config")
    slide_numbers: Optional[Dict[str, Any]] = Field(default=None, description="Slide-number config")
    presentation_goal: Optional[str] = Field(default=None, description="Overall presentation goal")
    presentation_type: str = Field(default="informative", description="Presentation type")
    chat_history: Optional[List[Dict[str, Any]]] = Field(default=None, description="Recent chat turns [{role,text}]")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs for grounding")
    selected_element_ids: Optional[List[str]] = Field(default=None, description="Element ids the user has selected on the canvas ('this' refers to them)")
    image_attachments: Optional[List[Dict[str, Any]]] = Field(default=None, description="Screenshots pasted into the chat: [{name, mimeType, base64}]. OCR'd server-side and prepended to the instruction.")


class ChartDataRequest(BaseModel):
    chart_type: str = Field(..., description="Chart type: bar, line, pie, doughnut, radar, polarArea, scatter, bubble")
    query: str = Field(..., description="Description of data to visualize")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs")
    page_context: Optional[Dict[str, Any]] = Field(default=None, description="Current slide/page content for AI context")
    source_context: Optional[str] = Field(default=None, description="Source type: presentation or report")


class ChartDataResponse(BaseModel):
    success: bool
    chart_config: Dict[str, Any] = Field(default=None, description="Chart.js compatible config")
    message: Optional[str] = None


class SavePresentationRequest(BaseModel):
    id: Optional[str] = Field(default=None, description="Presentation ID (for updates)")
    title: str = Field(..., description="Presentation title")
    goal: Optional[Dict[str, Any]] = Field(default=None, description="Presentation goal")
    style: Optional[Dict[str, Any]] = Field(default=None, description="Style definition")
    slides: List[Dict[str, Any]] = Field(..., description="Slide data")
    team_id: Optional[str] = Field(default=None, description="Team/Workspace ID (null for personal workspace)")
    presentation_type: str = Field(default="informative", description="Presentation type")
    thumbnail: Optional[str] = Field(default=None, description="Thumbnail image (base64 or URL)")
    folder_id: Optional[str] = Field(default=None, description="Presentation's dedicated folder (one per artifact)")
    # Accepted because the composer has always sent the plural. Pydantic
    # dropped it as unknown, folder_id fell back to None, and every saved deck
    # stored null -- detaching it from its own data store, so the folder view
    # opened empty and a reopened deck had no documents to read. Taking either
    # here means an un-updated client keeps working.
    folder_ids: Optional[List[str]] = Field(default=None, description="Legacy plural form of folder_id; first entry wins")
# ... (previous models)

class BatchGenerateSlidesRequest(BaseModel):
    items: List[GenerateSlideRequest] = Field(..., description="List of slides to generate")

# Module-level singleton to prevent creating new UnifiedQueryEngine instances in different event loops
_unified_query_engine = None

def get_query_engine():
    """Get or create singleton UnifiedQueryEngine instance"""
    global _unified_query_engine
    if _unified_query_engine is None:
        from llamaindex_query_engine import UnifiedQueryEngine
        _unified_query_engine = UnifiedQueryEngine()
    return _unified_query_engine

async def retrieve_vault_context(
    user_id: str,
    query: str,
    folder_ids: list = None,
    top_k: int = 2,
    milvus_fetch_k: int = None,
    include_supplementary: bool = False,
    skip_saas: bool = False
):
    """
    Retrieve relevant context from user's vault for content generation.
    
    Delegates to shared implementation in composer_query.py which supports
    optional supplementary sources (SQL databases and SaaS apps).
    
    Args:
        user_id: User identifier
        query: Search query for semantic matching
        folder_ids: Optional list of folder IDs to filter by
        top_k: Number of top results to return
        milvus_fetch_k: Number of candidates to fetch from Milvus before reranking
        include_supplementary: Whether to also fetch from SQL/SaaS sources (AI-routed)
        skip_saas: Whether to skip SaaS/structured data retrieval (when pre-fetched at outline level)
    
    Returns:
        str: Concatenated context from vault (and optionally supplementary sources)
    """
    try:
        from composer_query import retrieve_vault_context as shared_retrieve_vault_context
        
        return await shared_retrieve_vault_context(
            user_id=user_id,
            query=query,
            folder_ids=folder_ids,
            top_k=top_k,
            milvus_fetch_k=milvus_fetch_k,
            use_saas=include_supplementary,
            skip_saas=skip_saas
        )
    except ImportError:
        # Fallback to local implementation if shared not available
        logger.warning("🎬 [PRESENTATION] Shared vault context not available, using local")
        engine = get_query_engine()
        
        contexts = await engine.retrieve_personal_context(
            query=query,
            user_id=user_id,
            selected_folder_ids=folder_ids,
            folder_search_enabled=bool(folder_ids),
            top_k=top_k
        )
        
        if not contexts:
            return ""
            
        return format_flattened_context(contexts)
    except Exception as e:
        logger.warning(f"🎬 [PRESENTATION] Vault retrieval failed: {e}")
        return ""


def format_flattened_context(contexts: List[Any]) -> str:
    """
    Flatten and group context chunks by source document to reduce token overhead.
    """
    if not contexts:
        return ""
        
    grouped_content = {}
    chunk_count = 0
    
    for ctx in contexts:
        chunk_count += 1
        text = ""
        source = "Unknown Document"
        
        if isinstance(ctx, dict):
            text = ctx.get('text', ctx.get('content', '')).strip()
            source = ctx.get('topic', ctx.get('filename', ctx.get('file_name', 'Document')))
        else:
            text = str(ctx).strip()
            source = "Document"
            
        if not text:
            continue
            
        if source not in grouped_content:
            grouped_content[source] = []
        
        grouped_content[source].append(text)
    
    formatted_parts = []
    for source, texts in grouped_content.items():
        doc_content = "\n(...)\n".join(texts)
        formatted_parts.append(f"[Document: {source}]\n{doc_content}")
    
    logger.info(f"🎬 [PRESENTATION] Context formatted. Flattened {chunk_count} chunks from {len(grouped_content)} documents")
    
    return "\n\n---\n\n".join(formatted_parts)


# ==================== AI Generation Helpers ====================



# ==================== API Endpoints ====================

@router.post("/presentation/generate-outline", response_model=GenerateOutlineResponse, deprecated=True)
async def generate_outline(request: Request, body: GenerateOutlineRequest):
    """
    LEGACY / DEPRECATED — Marked for deletion.
    UI exclusively uses /presentation/generate-outline-stream.
    This non-streaming variant lacks internet search support.
    Remove once confirmed no external callers depend on it.
    """
    logger.info(f"🎬 [PRESENTATION] Generating outline for: {body.goal[:50]}...")
    
    user_id = get_secure_user_id(request)

    # Vault chunks now fetched agentically by the LLM via personal_data_tool
    # inside run_Enterprise_or_Personal_tool below — no pre-fetch.
    _outline_use_personal = bool(body.folder_ids)
    vault_context = ""
    
    # Prefetch schema-only structured-data context (post-DuckDB)
    structured_data_context = None
    if body.folder_ids:
        try:
            from composer_query import prefetch_structured_data_context
            structured_data_context = await prefetch_structured_data_context(
                user_id=user_id,
                goal=body.goal,
                folder_ids=body.folder_ids
            )
            if structured_data_context:
                logger.info(f"🌊 [PRESENTATION] Prefetched structured data ({len(structured_data_context)} chars)")
        except Exception as e:
            logger.warning(f"🌊 [PRESENTATION] Structured data prefetch failed (non-blocking): {e}")

    # Prefetch unstructured-file metadata (filenames + summaries + tags) for
    # the outline LLM. The model uses this to decide whether to call
    # personal_data_tool to pull chunks for vault-grounded outlines.
    unstructured_metadata_context = None
    if body.folder_ids:
        try:
            from services.unstructured_file_listing import prefetch_unstructured_metadata_for_outline
            unstructured_metadata_context = await prefetch_unstructured_metadata_for_outline(
                user_id=user_id, folder_ids=body.folder_ids, query=body.goal,
            )
            if unstructured_metadata_context:
                logger.info(f"📄 [PRESENTATION] Prefetched unstructured metadata ({len(unstructured_metadata_context)} chars)")
        except Exception as e:
            logger.warning(f"📄 [PRESENTATION] Unstructured metadata prefetch failed (non-blocking): {e}")
    
    # Build system prompt - PROFILE-AWARE. The user-picked deck_profile
    # determines whether the outline LLM operates in strict executive mode,
    # mixed (exec + charts + selective images), or full-freedom legacy mode.
    _profile = getattr(body, 'deck_profile', None) or 'corporate_boardroom'

    if _profile == 'corporate_with_visuals':
        system_prompt = """You are designing a CORPORATE deck with strategic visuals. The base look is executive (typography-led, kicker → action-title → subhead spine), augmented by data charts, diagrams, and the occasional hero photograph where it materially helps the argument.

OUTPUT: {"slides":[{"title":"<action title — a CLAIM, not a topic>","content_hint":"2-3 sentences","layout":"<layout name>","kicker":"SHORT UPPERCASE LABEL","image_prompt":"<photo description — only for image-bearing layouts>","speaker_notes":"optional"}]}

PRIMARY LAYOUTS (executive family — use as the backbone):
  exec_title, exec_pillars, exec_argument, exec_pillar_detail, exec_stat_grid,
  exec_features, exec_industries, exec_sovereignty, exec_chat_example, exec_closing

PERMITTED EXTRAS (use when the slide content earns them):
  chart_focus / chart_left / chart_right / chart_and_image / data_dashboard /
  stats_highlight / big_number  — when the slide is fundamentally about numbers
  process_steps / org_hierarchy / infographic_diagram / timeline  — when content is a structure
  title_image / image_left / image_right  — at most 1-2 slides per deck where one hero photo earns its place

RULES:
- Action titles, not topic titles. The `title` field MUST be the slide's claim. Reader should reconstruct the argument from titles alone.
- KICKER on every body slide — short uppercase label (≤ 7 words). Cover and closing too.
- IMAGE BUDGET — at most 1-2 photographic slides per deck. Most slides are text + colour + charts. Filler photography cheapens corporate decks; only include image_prompt when the photo materially amplifies the message.
- DARK / LIGHT RHYTHM — slide 1 and slide N are dark (exec_title / exec_closing). Architecture / sovereignty pages can be dark. Body stays light.
- VARIETY — never two consecutive slides of the same layout. Alternate exec_argument with stat_grid / pillar_detail / chart variants.
- IMAGE-PROMPT TEXT-LEAK PREVENTION (when emitting one): no proper nouns, no quoted strings, no "labeled / titled / saying" phrasing. Describe scene, lighting, composition, palette only.
- DATA ACCURACY: do NOT fabricate numbers. Use only values from provided context."""
    elif _profile == 'general_with_images':
        system_prompt = """Expert presentation designer. Create slide outlines with narrative arc and rich imagery.

OUTPUT: {"slides":[{"title":"...","content_hint":"2-3 sentences","layout":"title|title_content|two_column|image_focus|bullet_points|quote|comparison|chart|data|timeline|process|exec_*","image_prompt":"A concise description of a PHOTO (not infographic, not org chart, not diagram — a real photograph)","speaker_notes":"optional"}]}

LAYOUT GUIDE: title=hero/cover, title_content=text with bullets, two_column=side-by-side, image_focus=visual-heavy, bullet_points=list, quote=citation, comparison=vs/compare, chart=chart-focused, data=stats, timeline=chronological, process=step-by-step. The exec_* family is also available if a tighter, typography-led look fits the slide.

RULES: First=title slide, Last=CTA/summary. 2+ image_focus slides for visual interest. EVERY non-exec slide MUST include "image_prompt" — describe a PHOTOGRAPH only (real-world scene, objects, people, nature, architecture). NEVER request infographics, org charts, diagrams, flowcharts, or images containing text/labels/numbers.
IMAGE-PROMPT RULES (CRITICAL — get the SUBJECT right, prevent text artefacts):
  - NAME CONCRETE PHYSICAL SUBJECTS DIRECTLY. If the slide is about a caterpillar, write "caterpillar"; about an MRI machine, write "MRI machine"; about a vineyard, write "vineyard". Diffusion models render concrete physical nouns (animals, plants, objects, vehicles, food, buildings, body parts, weather, landscapes, people) accurately. Euphemisms produce wrong subjects.
  - USE VISUAL ANALOGUES ONLY for ABSTRACT / NON-VISUAL concepts that have no physical form: technical jargon ("OAuth", "Kubernetes"), scientific processes ("Krebs cycle"), business metrics ("Q3 revenue", "ARR"), brand/product names. Replace those with generic analogues (e.g. "abstract organic structures with glowing connections" instead of "Krebs cycle diagram").
  - No "reading… / titled… / labeled… / saying… / with the text…" phrasing.
  - No quoted strings — quoted text renders literally.
  - Pattern: <concrete subject>, <action / pose>, <setting>, <lighting>, <composition>, <colour / mood>.
DATA ACCURACY: Do NOT hallucinate facts, numbers, dates, or claims. Use ONLY verifiable information from provided context. JSON only, no markdown."""
    else:
        # Default: corporate_boardroom — strict exec-only mode (the Cowork aesthetic)
        system_prompt = """Citra is an enterprise platform. EVERY deck you produce is a consultant-grade executive deck — boardroom polish, typography-led, no filler photography. There is no separate "casual" mode.

OUTPUT: {"slides":[{"title":"<action title — a CLAIM, not a topic>","content_hint":"2-3 sentences","layout":"<one of the 10 layout names below>","kicker":"SHORT UPPERCASE LABEL (e.g. PILLAR 1 · BUSINESS PROCESS AUTOMATION)","speaker_notes":"optional talk-track"}]}

THE 10 LAYOUTS — every slide picks exactly one:
  exec_title          → Slide 1 ONLY. Dark navy cover, two-tone headline, three pillar pills. No image.
  exec_pillars        → "What is X" / "Three pillars" / framework intro. Light bg, three coloured pillar cards. No image.
  exec_argument       → THE WORKHORSE body slide. Kicker + action title + subhead + 4-5 bullets. Use for any body slide making one claim.
  exec_pillar_detail  → Pillar deep-dive WITH a before/after stat or numbered how-it-works steps. Light bg, left steps card + right navy stat card. No image.
  exec_stat_grid      → 4 headline KPIs / "by the numbers" / business impact. Light bg, 4 stat cards with coloured accent bars. No image.
  exec_features       → 4 distinct capabilities / value props in a 2x2 grid. Light bg, coloured icon circles. No image.
  exec_industries     → 4 verticals each with 4 checkmark use-cases. Light bg, vertical coloured side-rules. No image.
  exec_sovereignty    → Architecture / security / governance / trust posture. Dark bg, 4 dark cards in a row + governance panel. No image.
  exec_chat_example   → Live product example as a chat Q&A + 3 supporting stat blocks. Light bg. No image.
  exec_closing        → Slide N ONLY. Dark navy, 2x2 numbered reason cards, cyan CTA banner. No image.

THE SPINE — every deck follows this rhythm:
  Slide 1            : exec_title          (dark)
  Slide 2            : exec_pillars        (light)        — frame the deck's pillars
  Slides 3..N-1      : a varied mix from { exec_argument, exec_pillar_detail, exec_stat_grid, exec_features, exec_industries, exec_sovereignty, exec_chat_example }
  Slide N            : exec_closing        (dark)

VARIETY RULES (apply across the deck):
- Vary the body layout — do NOT use exec_argument twice in a row. Alternate with stat_grid / features / pillar_detail / chat_example for rhythm.
- A typical L-tier deck (10-14 slides) hits roughly: title (1) + pillars (1) + 3-5 argument (workhorse) + 1-2 stat_grid + 1-2 pillar_detail + 1 features OR industries + 1 sovereignty + closing (1). Adjust to the goal.
- exec_sovereignty is appropriate ONLY when the deck speaks to trust / data-residency / security posture — don't shoehorn it.

ACTION TITLES, never topic titles. The `title` field MUST be the slide's CLAIM. Examples:
  ✗ Topic:   "Q4 results"                        | ✓ Action:  "Q4 missed growth but cash position improved"
  ✗ Topic:   "Citra overview"                    | ✓ Action:  "Operations that run themselves. Owned by your team."
  ✗ Topic:   "Analytics features"                | ✓ Action:  "A month of analyst work, overnight — with citations"
  ✗ Topic:   "Industries"                        | ✓ Action:  "Built for regulated, complex enterprises"
  ✗ Topic:   "Architecture"                      | ✓ Action:  "Your data stays. Your AI shows up."
A reader skimming titles alone should be able to reconstruct your argument.

KICKER — every body slide gets a short uppercase label in the `kicker` field. Examples: "PILLAR 1 · BUSINESS PROCESS AUTOMATION", "BUSINESS IMPACT", "ARCHITECTURE & SOVEREIGNTY", "INDUSTRIES & USE CASES", "WHY BUY CITRA". The cover slide (exec_title) and closing (exec_closing) also carry kickers ("EXECUTIVE OVERVIEW · <DATE>", "WHY BUY CITRA"). Keep kickers ≤ 7 words.

NO IMAGES. Citra's executive aesthetic is typography + colour blocks + icons + simple shapes. DO NOT emit an `image_prompt` field on any slide. Filler photography cheapens enterprise decks. (Charts and stat numbers are not images — those are first-class elements in the layouts themselves.)

DARK/LIGHT RHYTHM — Slide 1 and slide N are dark navy; exec_sovereignty is dark; everything else is light. This is the deck's pulse — don't fight it.
IMAGE-PROMPT RULES (CRITICAL — get the SUBJECT right, prevent text artefacts) — applies ONLY if you emit an image_prompt at all (exec decks normally do not):
  - NAME CONCRETE PHYSICAL SUBJECTS DIRECTLY. Diffusion models render concrete physical nouns (animals, plants, objects, vehicles, food, buildings, body parts, weather, landscapes, people) accurately. Euphemisms produce wrong subjects.
  - USE VISUAL ANALOGUES ONLY for ABSTRACT / NON-VISUAL concepts (technical jargon, scientific processes, business metrics, brand/product names) — replace with generic analogues (e.g. "abstract organic structures with glowing connections" instead of "Krebs cycle diagram").
  - DO NOT use phrases like "reading…", "titled…", "labeled…", "saying…", "with the text…", "with caption…", "with sign…" — these instruct the image model to render text.
  - DO NOT include any quoted strings ("…", '…') — quoted text gets rendered literally.
DATA ACCURACY: Do NOT hallucinate or fabricate facts, numbers, or claims. Use ONLY verifiable information from provided context. JSON only, no markdown."""

    # Pre-bind: lite-mode vault retrieval (no sub-query expansion, no
    # reranker, no agentic tool-loop) using the goal as the query. Replaces
    # the previous agentic loop that fanned out 4-5 personal_data_tool
    # calls per outline (~30-45 s) with a single Milvus top-k pull (~1-2 s).
    outline_vault_block = ""
    if _outline_use_personal:
        from services.personal_data_tool import retrieve_vault_context_for_prompt
        outline_vault_block = await retrieve_vault_context_for_prompt(
            query=body.goal,
            user_id=user_id,
            folder_ids=body.folder_ids,
            max_results=8,
            log_prefix="PRESENTATION-OUTLINE-LEGACY-LITE",
            # Outline queries are the user's raw deck goal — often short
            # ("energy outlook") or typo'd. Enable adaptive backfill so a
            # narrow score band or vague query doesn't starve the outline
            # LLM of grounding context.
            adaptive_threshold=True,
            adaptive_floor=5,
        )

    # Build user prompt - DYNAMIC CONTENT LAST
    context_section = ""
    if outline_vault_block:
        context_section += f"\n\n{outline_vault_block}"
    if unstructured_metadata_context:
        context_section += f"\n\n{unstructured_metadata_context}"
    if structured_data_context:
        context_section += f"""\n\nSTRUCTURED DATA FROM USER'S FILES (real precomputed values from uploaded spreadsheets/CSVs):
{structured_data_context}
(IMPORTANT: These are REAL aggregates from the user's files — top categories, totals, date ranges, breakdowns. Anchor every slide title and content_hint on these actual values. Reference real names, real numbers, real periods. Do NOT write generic narrative when concrete facts are available, and never invent numbers.)"""

    user_prompt = f"""Create a {body.slide_count}-slide presentation outline.

GOAL: {body.goal}
TYPE: {body.presentation_type}
AUDIENCE: {body.target_audience or 'General professional audience'}
{context_section}"""

    try:
        # Single LLM call — vault chunks pre-injected via outline_vault_block.
        # Compute_fact / personal_data_tool tool-calling intentionally
        # dropped here to recover pre-refactor outline latency.
        ai_response = await asyncio.to_thread(
            llm_call,
            system_prompt=_grounded_sys(system_prompt),
            user_prompt=user_prompt,
            model=None,
            user_id=user_id,
            max_tokens=8000,
            temperature=0.2,
            top_p=0.95,
            json_mode=True,
            tier="large",
        )
        
        
        # Parse JSON from response (handle potential markdown code blocks)
        # Parse JSON from response (handle potential markdown code blocks)
        json_str = extract_json_from_response(ai_response)
        
        outline_data = json.loads(json_str)
        slides = outline_data.get("slides", outline_data)
        
        # Add IDs to slides
        slides_with_ids = []
        for i, slide in enumerate(slides):
            slides_with_ids.append({
                "id": f"slide_{int(time.time() * 1000)}_{i}",
                "order": i + 1,
                **slide
            })
        
        logger.info(f"🎬 [PRESENTATION] Generated {len(slides_with_ids)} slide outlines")
        
        return GenerateOutlineResponse(
            success=True,
            slides=slides_with_ids,
            message=f"Generated {len(slides_with_ids)} slides"
        )
        
    except json.JSONDecodeError as e:
        logger.error(f"🎬 [PRESENTATION] JSON parse error: {e}")
        raise HTTPException(status_code=500, detail="Failed to parse AI response")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"🎬 [PRESENTATION] Outline generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/presentation/generate-outline-stream")
async def generate_outline_stream(request: Request, body: GenerateOutlineRequest):
    """
    Stream slide outline generation with Server-Sent Events (SSE).
    
    Immediately returns response and streams slides as they are generated,
    providing better UX by showing progress in real-time.
    
    SSE Event Format:
    - {"type": "progress", "message": "...", "step": 1}
    - {"type": "slide", "index": 0, "slide": {...}}
    - {"type": "done", "total": 5}
    - {"type": "error", "message": "..."}
    """
    logger.info(f"🌊 [PRESENTATION] Starting streaming outline for: {body.goal[:50]}...")
    
    user_id = get_secure_user_id(request)

    async def generate_stream():
        try:
            # Send initial progress
            yield f"data: {json.dumps({'type': 'progress', 'message': 'Analyzing your presentation goal...', 'step': 1})}\n\n"

            # Internet prefetch: run BEFORE vault retrieval so the freshly
            # embedded internet doc is picked up by the same vault retrieval
            # call used for outline + slide generation.
            # Vault gate matches the per-slide gate (`saas_enabled()` in
            # composer_query.py:78): folder selection IS the vault toggle —
            # the UI sends `folder_ids=[]` when the toggle is OFF and the
            # selected folders when ON. `body.use_personal_data` is treated
            # as an additional opt-in but is not required, so the outline
            # path doesn't sit at a stricter gate than per-slide retrieval.
            _vault_enabled = bool(body.folder_ids)
            if body.use_internet_search:
                try:
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Searching the internet for latest data...', 'step': 2})}\n\n"
                    from services.internet_prefetch import prefetch_internet_research
                    prefetch_results = await prefetch_internet_research(
                        goal=body.goal,
                        doc_type=body.presentation_type or "presentation",
                        target_audience=body.target_audience,
                        user_id=user_id,
                        folder_id=(body.folder_ids[0] if body.folder_ids else None),
                        num_queries=1,
                    )
                    for r in prefetch_results:
                        yield f"data: {json.dumps({'type': 'internet_research', 'document_id': r['document_id'], 'folder_id': r['folder_id'], 'word_count': r['word_count']})}\n\n"
                    if prefetch_results:
                        logger.info(f"🌐 [PRESENTATION] Internet prefetch embedded {len(prefetch_results)} doc(s) in vault")
                        if not _vault_enabled and body.folder_ids:
                            _vault_enabled = True
                except Exception as e:
                    logger.warning(f"🌐 [PRESENTATION] Internet prefetch failed (non-blocking): {e}")
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Internet search skipped, continuing...', 'step': 2})}\n\n"

            # Caller-supplied research corpus — quick / main chat already did
            # a fast search and handed the findings in. Embed it into the
            # vault (same path as the internet prefetch above) so the normal
            # outline + per-slide retrieval grounds the deck on it. No deep-
            # research sandbox spawn. If the caller passed no folder, the
            # corpus lands in the fallback folder and we pin retrieval to it
            # so embed + retrieve agree.
            if body.prefetched_corpus:
                try:
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Preparing your research...', 'step': 2})}\n\n"
                    from services.internet_prefetch import prefetch_corpus
                    corpus_results = await prefetch_corpus(
                        corpus=body.prefetched_corpus,
                        doc_type=body.presentation_type or "presentation",
                        user_id=user_id,
                        folder_id=(body.folder_ids[0] if body.folder_ids else None),
                    )
                    for r in corpus_results:
                        yield f"data: {json.dumps({'type': 'internet_research', 'document_id': r['document_id'], 'folder_id': r['folder_id'], 'word_count': r['word_count']})}\n\n"
                    if corpus_results:
                        logger.info(f"🎬 [PRESENTATION] Corpus prefetch embedded {len(corpus_results)} doc(s) in vault")
                        # The corpus IS the grounding data — enable vault
                        # retrieval, and pin folder scope to where it landed
                        # so the per-slide retrieval can actually find it.
                        if not body.folder_ids:
                            body.folder_ids = [corpus_results[0]["folder_id"]]
                        _vault_enabled = True
                except Exception as e:
                    logger.warning(f"🎬 [PRESENTATION] Corpus prefetch failed (non-blocking): {e}")
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Research prep skipped, continuing...', 'step': 2})}\n\n"

            # Vault chunks are fetched agentically by the LLM via
            # personal_data_tool in the `run_Enterprise_or_Personal_tool` call below
            # — no pre-fetch.
            vault_context = ""
            _use_personal_for_outline = bool(_vault_enabled) and bool(body.folder_ids)
            if _use_personal_for_outline:
                yield f"data: {json.dumps({'type': 'progress', 'message': 'Preparing data tools for outline...', 'step': 2})}\n\n"

            yield f"data: {json.dumps({'type': 'progress', 'message': 'Creating slide outline...', 'step': 3})}\n\n"

            # Prefetch structured data once for all slides
            structured_data_context = None
            if body.folder_ids:
                try:
                    from composer_query import prefetch_structured_data_context
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Analyzing structured data...', 'step': 3})}\n\n"
                    structured_data_context = await prefetch_structured_data_context(
                        user_id=user_id,
                        goal=body.goal,
                        folder_ids=body.folder_ids
                    )
                    if structured_data_context:
                        logger.info(f"🌊 [PRESENTATION] Prefetched structured data for all slides ({len(structured_data_context)} chars)")
                except Exception as e:
                    logger.warning(f"🌊 [PRESENTATION] Structured data prefetch failed (non-blocking): {e}")

            # Prefetch unstructured-file metadata once for all slides — gives
            # the outline LLM filename + summary + tags so it can decide
            # whether to call personal_data_tool to pull chunks.
            unstructured_metadata_context = None
            if body.folder_ids:
                try:
                    from services.unstructured_file_listing import prefetch_unstructured_metadata_for_outline
                    unstructured_metadata_context = await prefetch_unstructured_metadata_for_outline(
                        user_id=user_id, folder_ids=body.folder_ids, query=body.goal,
                    )
                    if unstructured_metadata_context:
                        logger.info(f"📄 [PRESENTATION] Prefetched unstructured metadata for all slides ({len(unstructured_metadata_context)} chars)")
                except Exception as e:
                    logger.warning(f"📄 [PRESENTATION] Unstructured metadata prefetch failed (non-blocking): {e}")

            # Build prompts (same as non-streaming version)
            system_prompt = """Expert presentation designer. Create slide outlines with narrative arc.

OUTPUT: {"suggested_topic":"A concise 1-2 sentence topic that best captures the presentation focus given the GOAL and CONTEXT","slides":[{"id":1,"title":"...","content_hint":"2-3 sentences","layout":"title|title_content|two_column|image_focus|bullet_points|quote|comparison|chart|data|timeline|process","image_prompt":"A concise description of a PHOTO (not infographic, not org chart, not diagram — a real photograph)","speaker_notes":"optional"}]}

LAYOUT GUIDE: title=hero/cover, title_content=text with bullets, two_column=side-by-side, image_focus=visual-heavy, bullet_points=list, quote=citation/testimonial, comparison=vs/compare, chart=chart-focused, data=stats/metrics, timeline=chronological, process=step-by-step flow.
RULES: First=title slide, Last=CTA/summary, 2+ image_focus slides. Each slide MUST have a numeric "id" field. EVERY slide MUST include "image_prompt" — it MUST describe a PHOTOGRAPH only (real-world scene, objects, people, nature, architecture, etc.). NEVER request infographics, org charts, diagrams, flowcharts, or any image containing text/labels/numbers.
IMAGE-PROMPT RULES (CRITICAL — get the SUBJECT right, prevent text artefacts):
  - NAME CONCRETE PHYSICAL SUBJECTS DIRECTLY. If the slide is about a caterpillar, write "caterpillar"; about a butterfly, write "butterfly"; about a beach, write "beach". Diffusion models render concrete physical nouns (animals, plants, objects, vehicles, food, buildings, body parts, weather, landscapes, people) accurately and DO NOT leak them as text. Euphemisms like "small elongated crawling creature with striped patterns" produce wrong subjects (e.g. a lizard instead of a caterpillar).
  - ONLY USE VISUAL ANALOGUES FOR ABSTRACT / NON-VISUAL CONCEPTS that have no physical form: technical jargon ("OAuth", "Kubernetes", "API"), scientific processes ("Krebs cycle", "mitosis", "glycolysis"), business metrics ("Q3 revenue", "ARR"), legal/financial concepts, brand/product names. For these, replace with a generic visual analogue (e.g. "abstract organic structures with glowing connections" instead of "Krebs cycle diagram").
  - DO NOT use phrases that instruct the image model to render text: "reading…", "titled…", "labeled…", "saying…", "with the text…", "with caption…", "with sign…", "with logo…".
  - DO NOT include any quoted strings ("…", '…') — quoted text gets rendered literally.
  - Pattern: <concrete subject>, <action / pose>, <setting>, <lighting>, <composition>, <colour / mood>. Example for an egg-stage slide: "A pinhead-sized butterfly egg resting on the underside of a green leaf, morning dew on the surrounding surface, soft natural lighting, extreme macro composition, fresh greens with warm highlights".
The "suggested_topic" MUST reflect the best focus for this presentation given the goal and any vault context provided — you have FULL FREEDOM to rewrite it completely if the data warrants a different angle. DATA ACCURACY: Do NOT hallucinate or fabricate facts, numbers, or claims. Use ONLY verifiable information from provided context. JSON only, no markdown."""

            # Pre-bind: lite-mode vault retrieval (no sub-query expansion, no
            # reranker, no agentic tool-loop) using the goal as the focused
            # query. Returns "" when vault is disabled / no match. This
            # replaces the previous agentic loop that fanned out 4-5
            # personal_data_tool calls per outline (~30-45 s) with a single
            # Milvus top-k pull (~1-2 s) followed by one synthesis call.
            outline_vault_block = ""
            if _use_personal_for_outline:
                from services.personal_data_tool import retrieve_vault_context_for_prompt
                outline_vault_block = await retrieve_vault_context_for_prompt(
                    query=body.goal,
                    user_id=user_id,
                    user_email=getattr(getattr(request, 'state', None), 'user_email', None),
                    folder_ids=body.folder_ids,
                    max_results=8,
                    log_prefix="PRESENTATION-OUTLINE-LITE",
                    adaptive_threshold=True,
                    adaptive_floor=5,
                )

            context_section = ""
            if outline_vault_block:
                context_section += f"\n\n{outline_vault_block}"

            if unstructured_metadata_context:
                context_section += f"\n\n{unstructured_metadata_context}"

            if structured_data_context:
                context_section += f"""\n\nSTRUCTURED DATA FROM USER'S FILES (real precomputed values from uploaded spreadsheets/CSVs):
{structured_data_context}
(IMPORTANT: These are REAL aggregates from the user's files — top categories, totals, date ranges, breakdowns. Anchor every slide title and content_hint on these actual values. Reference real names, real numbers, real periods. Do NOT write generic narrative when concrete facts are available, and never invent numbers.)"""

            existing_outline_section = ""
            if body.existing_outline:
                outline_items = json.dumps([{"id": item.get('id', i+1), "title": item.get('title', ''), "content_hint": item.get('outline', '')} for i, item in enumerate(body.existing_outline)])
                existing_outline_section = f"""\n\nEXISTING SLIDE OUTLINE (use the SAME "id" values so changes map back to original slides):
{outline_items}

IMPORTANT: Return EXACTLY {len(body.existing_outline)} slides, each keeping its original "id".
- If a slide is still relevant to the GOAL and CONTEXT: refine its title and content_hint.
- If a slide is NO LONGER valid or applicable given the goal/context: completely rewrite its title and content_hint to something that IS relevant. Do NOT keep outdated or irrelevant content.
- You have full freedom to overhaul every slide if the data warrants it. The only constraint is keeping the same count and the same id values."""

            user_prompt = f"""Create a {body.slide_count}-slide presentation outline.

GOAL: {body.goal}
TYPE: {body.presentation_type}
AUDIENCE: {body.target_audience or 'General professional audience'}
{context_section}{existing_outline_section}"""

            # Single streaming LLM call — vault chunks are pre-injected via
            # `outline_vault_block` (lite-mode retrieval). The previous
            # agentic-loop path was making 4-5 personal_data_tool calls per
            # outline (~30-45 s); this collapses to one ~1-2 s lite fetch
            # plus one streaming synthesis (~10-15 s). Compute_fact /
            # personal_data_tool tool-calling intentionally dropped here.
            full_response = ""
            chunk_count = 0
            for chunk in llm_call_streaming(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=None,
                user_id=user_id,
                max_tokens=8000,
                json_mode=True,
                tier="large",
            ):
                full_response += chunk
                chunk_count += 1
                if chunk_count % 10 == 0:
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Generating slide details...', 'step': 4})}\n\n"
            
            # Parse the complete response
            yield f"data: {json.dumps({'type': 'progress', 'message': 'Finalizing outline...', 'step': 5})}\n\n"
            
            logger.info(f"🌊 [PRESENTATION] Raw response length: {len(full_response)}, first 500 chars: {full_response[:500]}")
            json_str = extract_json_from_response(full_response)
            logger.info(f"🌊 [PRESENTATION] Extracted JSON length: {len(json_str) if json_str else 0}, first 300 chars: {json_str[:300] if json_str else 'None'}")
            outline_data = json.loads(json_str)
            # Handle double-encoded JSON (string instead of dict)
            if isinstance(outline_data, str):
                outline_data = json.loads(outline_data)
            
            logger.info(f"🌊 [PRESENTATION] Parsed outline type: {type(outline_data).__name__}, keys: {list(outline_data.keys()) if isinstance(outline_data, dict) else 'N/A'}")
            
            if isinstance(outline_data, dict):
                # Try common key names for slides array
                slides = (
                    outline_data.get("slides")
                    or outline_data.get("outline")
                    or (outline_data.get("presentation", {}).get("slides") if isinstance(outline_data.get("presentation"), dict) else None)
                )
                if slides is None:
                    # If the dict has a single key containing a list, use that
                    for key, val in outline_data.items():
                        if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                            logger.info(f"🌊 [PRESENTATION] Using key '{key}' as slides array")
                            slides = val
                            break
                if slides is None:
                    # Check if the dict itself looks like a single slide (has 'title' or 'content_hint')
                    if outline_data.get("title") or outline_data.get("content_hint"):
                        logger.warning(f"🌊 [PRESENTATION] Parsed dict looks like a single slide — attempting to extract all slides from raw response")
                        slides = _extract_all_slide_objects(full_response)
                        if not slides:
                            # Last resort: wrap the single slide in a list
                            logger.warning(f"🌊 [PRESENTATION] Could not extract multiple slides, using single slide")
                            slides = [outline_data]
                    else:
                        # Dict has no slides key and doesn't look like a slide itself.
                        # The LLM may have returned suggested_topic as a separate object
                        # followed by a slides array — try to extract slides from raw response.
                        logger.warning(f"🌊 [PRESENTATION] Dict has no slides key (keys: {list(outline_data.keys())}), attempting to extract slides from raw response")
                        slides = _extract_all_slide_objects(full_response)
                        if not slides:
                            # Also try parsing a JSON array from the raw response
                            array_match = re.search(r'\[[\s\S]*\]', full_response)
                            if array_match:
                                try:
                                    parsed_array = json.loads(array_match.group())
                                    if isinstance(parsed_array, list) and len(parsed_array) > 0 and isinstance(parsed_array[0], dict):
                                        slides = parsed_array
                                        logger.info(f"🌊 [PRESENTATION] Extracted {len(slides)} slides from JSON array in raw response")
                                except json.JSONDecodeError:
                                    pass
                        if not slides:
                            slides = []
                suggested_topic = outline_data.get("suggested_topic", "") or outline_data.get("topic", "")
                # If we had to extract slides from raw response, also try to get suggested_topic from it
                if not suggested_topic and slides and slides is not outline_data.get("slides"):
                    topic_match = re.search(r'"suggested_topic"\s*:\s*"([^"]*)"', full_response)
                    if topic_match:
                        suggested_topic = topic_match.group(1)
            elif isinstance(outline_data, list):
                slides = outline_data
                suggested_topic = ""
            else:
                raise ValueError(f"Unexpected outline format: {type(outline_data)}")
            
            # Stream suggested topic if present
            if suggested_topic:
                yield f"data: {json.dumps({'type': 'topic', 'topic': suggested_topic})}\n\n"
            
            # Stream each slide individually
            for i, slide in enumerate(slides):
                original_id = slide.get('id', i + 1)
                slide_with_id = {
                    "id": f"slide_{int(time.time() * 1000)}_{i}",
                    "order": i + 1,
                    "original_id": original_id,
                    **{k: v for k, v in slide.items() if k != 'id'}
                }
                yield f"data: {json.dumps({'type': 'slide', 'index': i, 'slide': slide_with_id})}\n\n"
                # Small delay for visual effect
                await asyncio.sleep(0.1)

            # Storyboard pass — ONE LLM call that sees the whole outline and
            # emits a deck-level design plan (palette + typography + per-slide
            # intent/mode/tone). Client should capture this and pass it as
            # `deck_plan` on every /presentation/generate-slide call so all
            # slides share the same design language. Non-fatal on failure.
            try:
                yield f"data: {json.dumps({'type': 'progress', 'message': 'Planning deck design...', 'step': 6})}\n\n"
                from services.storyboard import generate_storyboard
                storyboard = await generate_storyboard(
                    outline=slides,
                    goal=body.goal,
                    doc_type=body.presentation_type or "informative",
                    surface="presentation",
                    user_id=user_id,
                )
                yield f"data: {json.dumps({'type': 'storyboard', 'storyboard': storyboard})}\n\n"
            except Exception as _sb_exc:
                logger.warning(f"📐 [PRESENTATION] storyboard pass failed (non-blocking): {_sb_exc}")

            # Send completion
            yield f"data: {json.dumps({'type': 'done', 'total': len(slides), 'message': f'Generated {len(slides)} slides'})}\n\n"
            
            logger.info(f"🌊 [PRESENTATION] Streamed {len(slides)} slide outlines")
            
        except json.JSONDecodeError as e:
            logger.error(f"🌊 [PRESENTATION] JSON parse error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to parse AI response'})}\n\n"
        except Exception as e:
            logger.error(f"🌊 [PRESENTATION] Streaming error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ============================================================================
# BUILT-IN STYLE PRESETS — modelled on consultant-grade executive decks
# (board / investor / pitch). Returned verbatim by /presentation/generate-style
# when the user's prompt looks executive-shaped; saves a round-trip and
# guarantees consistent palette + type system across the deck.
# Future: extend to a tenant-bound `brand_registry` so each enterprise gets
# its own logo / palette / footer pattern.
# ============================================================================
BUILTIN_STYLE_PRESETS: Dict[str, Dict[str, Any]] = {
    "citra-executive": {
        "id": "citra-executive",
        "name": "Citra Executive",
        "fontFamily": "Inter",
        # Body slides — light surface, near-black text, single bold accent.
        "slideBackground": "#F8FAFC",
        "textPrimary": "#0F172A",
        "textSecondary": "#475569",
        "accentColor": "#2563EB",
        # Dark-surface palette used by exec_title_dark and exec_closing_dark
        # templates and by section-divider slides.
        "darkSurface": "#0B1020",
        "onDarkPrimary": "#FFFFFF",
        "onDarkSecondary": "#CBD5E1",
        "onDarkAccent": "#22D3EE",
        # Section accents — one per pillar / industry. Consumed by template
        # post-processor so each pillar slide gets a stable color stamp.
        "sectionAccents": [
            "#2563EB",  # blue       — pillar 1, banking
            "#06B6D4",  # cyan       — pillar 2, healthcare/data
            "#8B5CF6",  # purple     — pillar 3, public sector / docs
            "#10B981",  # green      — operations / proof / use cases
            "#F59E0B",  # amber      — risks / warnings
            "#EC4899",  # rose       — creative
        ],
        # Type system — six well-defined ramps the renderer can hand to
        # textType selectors instead of ad-hoc fontSize choices.
        "typeSystem": {
            "h1":       {"fontFamily": "Inter", "fontSize": 44, "fontWeight": "bold",   "lineHeight": 1.15, "letterSpacing": 0},
            "h2":       {"fontFamily": "Inter", "fontSize": 28, "fontWeight": "bold",   "lineHeight": 1.2,  "letterSpacing": 0},
            "h3":       {"fontFamily": "Inter", "fontSize": 18, "fontWeight": "bold",   "lineHeight": 1.3,  "letterSpacing": 0},
            "body":     {"fontFamily": "Inter", "fontSize": 14, "fontWeight": "normal", "lineHeight": 1.55, "letterSpacing": 0},
            "kicker":   {"fontFamily": "Inter", "fontSize": 12, "fontWeight": "bold",   "lineHeight": 1.2,  "letterSpacing": 3, "textTransform": "uppercase"},
            "footnote": {"fontFamily": "Inter", "fontSize": 9,  "fontWeight": "normal", "lineHeight": 1.4,  "letterSpacing": 1},
        },
        # Footer convention — every body slide carries a footer with the deck
        # title left and `page/total` right. Renderer auto-injects these on
        # exec_* and any template that opts in via `footerStyle: 'exec'`.
        "footer": {
            "leftPattern": "CITRA  |  {deck_title}",
            "rightPattern": "{page} / {total}",
            "fontSize": 9,
            "letterSpacing": 2,
            "color": "#94A3B8",
            "darkColor": "#475569",
            "y": 516,
        },
        # Preview block consumed by the style picker UI.
        "preview": {
            "titleColor": "#0F172A",
            "bodyColor":  "#475569",
        },
    },
}


def _executive_keywords_in(text: str) -> bool:
    """Heuristic: does the user's style prompt look like an executive deck?"""
    if not text:
        return False
    t = text.lower()
    for k in (
        "executive", "board deck", "investor deck", "pitch deck", "pitch",
        "leadership", "c-suite", "csuite", "strategic review", "overview deck",
        "boardroom", "consultant deck",
    ):
        if k in t:
            return True
    return False


@router.post("/presentation/generate-style")
async def generate_style(request: Request, body: GenerateStyleRequest):
    """
    Generate a custom presentation style/theme using AI.

    Short-circuit: if the user's prompt looks executive-shaped (board /
    investor / pitch / strategic review), return the built-in
    ``citra-executive`` preset directly. Skips a round-trip and guarantees
    consistent palette + type system + footer convention across the deck.
    """
    logger.info(f"🎨 [PRESENTATION] Generating style: {body.prompt[:50]}...")

    user_id = get_secure_user_id(request)

    # Executive shortcut — match the prompt against the executive-keyword
    # set and return the baked preset verbatim. The preset carries a
    # darkSurface / onDarkPrimary / sectionAccents palette + a type
    # system + a footer pattern that the LLM cannot reliably invent.
    if _executive_keywords_in(body.prompt):
        logger.info("🎨 [PRESENTATION] Matched executive preset → citra-executive")
        return JSONResponse(BUILTIN_STYLE_PRESETS["citra-executive"])

    system_prompt = """Presentation design expert. Generate color scheme.

OUTPUT: {"name":"Theme","fontFamily":"Inter","textPrimary":"#hex","textSecondary":"#hex","accentColor":"#hex","slideBackground":"#hex","preview":{"titleColor":"#hex","bodyColor":"#hex"}}

JSON only, no markdown."""

    user_prompt = f"""Create a presentation style theme based on this description:

"{body.prompt}"
"""


    try:
        # Call llm_oss (sync, run in thread)
        ai_response = await asyncio.to_thread(
            llm_call,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=None,
            user_id=user_id,
            max_tokens=5000,
            temperature=0.2,
            top_p=0.95,
            json_mode=True,
            tier="large",
        )
        
        # Parse JSON
        json_str = extract_json_from_response(ai_response)
        
        style_data = json.loads(json_str)
        
        logger.info(f"🎨 [PRESENTATION] Generated style: {style_data.get('name')}")
        
        return {"success": True, "style": style_data}
        
    except Exception as e:
        logger.error(f"🎨 [PRESENTATION] Style generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class PrefetchVaultChunksRequest(BaseModel):
    """Deck-level batch vault prefetch input.

    Submit ONE call with the full slide outline; the server batches all
    per-slide queries into a single OpenAI `/embeddings` request and
    parallelises the Milvus+Mongo lookups. The response is a list of
    formatted vault blocks aligned 1:1 with the input outline — clients
    pass each block back into `/presentation/generate-slide` via the
    `prefetched_vault_block` field so per-slide generation skips its
    own retrieval cost.
    """
    outline: List[Dict[str, Any]] = Field(..., description="Ordered list of slide info dicts with at least 'title' and optionally 'content_hint'")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs to scope retrieval")
    presentation_goal: Optional[str] = Field(default=None, description="Fallback query when a slide has no title/content_hint")
    max_results: int = Field(default=3, description="Max chunks per slide block")


@router.post("/presentation/prefetch-vault-chunks")
async def prefetch_vault_chunks_for_presentation(request: Request, body: PrefetchVaultChunksRequest):
    """Batch-prefetch vault passages for every slide in one shot.

    Eliminates the N concurrent OpenAI `/embeddings` calls (and their
    rate-limit retries) that we'd otherwise pay when the client fires
    `/presentation/generate-slide` for every slide in parallel. The
    blocks returned here are intended to be passed back to each slide
    generation call via `prefetched_vault_block`.
    """
    user_id = get_secure_user_id(request)

    if not body.outline:
        return {"success": True, "blocks": []}
    if not body.folder_ids:
        # No folders selected → nothing to retrieve. Return aligned empties
        # so the client can still iterate and pass "" per slide.
        return {"success": True, "blocks": ["" for _ in body.outline]}

    # Build one query string per slide using the same shape per-slide
    # generation uses (title + content_hint), with presentation_goal as
    # a fallback. Empty queries are tolerated by the batch helper.
    queries: List[str] = []
    for slide in body.outline:
        title = (slide.get("title") or "").strip() if isinstance(slide, dict) else ""
        content_hint = (slide.get("content_hint") or "").strip() if isinstance(slide, dict) else ""
        composed = f"{title}. {content_hint}".strip(" .")
        queries.append(composed or (body.presentation_goal or ""))

    from services.personal_data_tool import retrieve_vault_contexts_batch
    blocks = await retrieve_vault_contexts_batch(
        queries=queries,
        user_id=user_id,
        folder_ids=body.folder_ids,
        max_results=max(1, min(int(body.max_results or 3), 10)),
        log_prefix="PRESENTATION-PREFETCH",
    )
    return {"success": True, "blocks": blocks}


class CritiqueSlideRequest(BaseModel):
    """Vision-critique input: the rendered slide + its element JSON.

    Client captures the rendered fabric canvas via ``canvas.toDataURL('image/png')``
    after generation completes, then POSTs the data URL plus the current
    element list. Server runs one vision-LLM pass and returns a patched
    element list. Use opt-in per slide (skip for simple text slides to save
    budget; run for hero / closing / chart / svg slides).
    """
    elements: List[Dict[str, Any]] = Field(..., description="Current element list to critique")
    screenshot: str = Field(..., description="PNG screenshot as a data URL (image/png;base64,...)")
    slide_info: Optional[Dict[str, Any]] = Field(default=None, description="Optional slide context (title, content_hint)")
    canvas: Optional[Dict[str, Any]] = Field(default=None, description="Canvas dims {width, height} — defaults to 960x540")


@router.post("/presentation/critique-slide")
async def critique_slide(request: Request, body: CritiqueSlideRequest):
    """One-shot vision critique on a rendered slide.

    Returns the patched element list. The client should replace its
    in-memory elements with the returned list. Always returns the original
    elements on failure — safe to call on the hot path.
    """
    user_id = get_secure_user_id(request)
    from services.visual_critique import critique_and_patch
    result = await critique_and_patch(
        elements=body.elements,
        screenshot=body.screenshot,
        slide_info=body.slide_info,
        canvas=body.canvas or {"width": 960, "height": 540},
        user_id=user_id,
    )
    return {"success": True, **result}


@router.post("/presentation/generate-slide")
async def generate_slide(request: Request, body: GenerateSlideRequest):
    """Generate a single slide.

    Single routing axis: ``body.deck_profile``.
      - ``general``   → legacy free-form generator (LLM designs from scratch).
        ``template_id`` is ignored even if the UI sent one.
      - ``corporate`` → template path: LLM matcher picks a template from the
        executive catalog (or keyword fallback), then slot-fill generation.
    """
    logger.info(f"🎬 [PRESENTATION] Generating slide {body.slide_index + 1}: {body.slide_info.get('title', 'Unknown')}")

    user_id = get_secure_user_id(request)
    _profile = (getattr(body, 'deck_profile', None) or 'corporate').lower()

    # ─── GENERAL: legacy free-form path ────────────────────────────────────
    if _profile in ('general', 'general_with_images'):
        body.template_id = None
        logger.info("🎬 [PRESENTATION] deck_profile=general → legacy free-form generator")
        return await generate_slide_legacy(body, user_id)

    # ─── CORPORATE: template path ──────────────────────────────────────────
    # Match a template (LLM first, keyword fallback) if the UI didn't pin one.
    if not body.template_id or body.template_id == 'ai_auto':
        from slide_templates import auto_match_template, llm_match_template
        slide_title = body.slide_info.get('title', '')
        slide_instruction = body.slide_info.get('content_hint', body.slide_info.get('instruction', ''))
        slide_layout = body.slide_info.get('layout', '')
        slide_image_prompt = body.slide_info.get('image_prompt', '')

        llm_matched = await asyncio.to_thread(
            llm_match_template,
            slide_title, slide_instruction, body.slide_index, body.total_slides,
            slide_layout, slide_image_prompt, bool(body.structured_data_context), user_id,
            _profile,
        )
        if llm_matched:
            body.template_id = llm_matched
            logger.info(f"🎬 [PRESENTATION] LLM-matched template: {body.template_id} for slide '{slide_title}' (layout={slide_layout}, has_image_prompt={bool(slide_image_prompt)})")
        else:
            body.template_id = auto_match_template(
                slide_title, slide_instruction, body.slide_index, body.total_slides,
                layout=slide_layout, image_prompt=slide_image_prompt,
                has_structured_data=bool(body.structured_data_context),
                deck_profile=_profile,
            )
            logger.info(f"🎬 [PRESENTATION] Keyword-matched template (LLM fallback): {body.template_id} for slide '{slide_title}' (layout={slide_layout}, has_image_prompt={bool(slide_image_prompt)}, profile={_profile})")

    return await generate_slide_with_template(body, user_id)


async def generate_slide_with_template(body: GenerateSlideRequest, user_id: str):
    """
    Template-based slide generation.
    
    AI only fills slot content (text, icon names, image descriptions).
    Positions come from the predefined template.
    """
    from slide_templates import (
        SLIDE_TEMPLATES,
        get_slot_prompt_format,
        get_example_json_for_template,
        build_elements_from_template,
        apply_style_to_template,
        inject_exec_footer,
    )
    
    template_id = body.template_id
    template = SLIDE_TEMPLATES.get(template_id)
    
    if not template:
        logger.warning(f"🎬 [PRESENTATION] Template '{template_id}' not found, falling back to three_cards")
        template_id = "three_cards"
        template = SLIDE_TEMPLATES.get(template_id)
    
    logger.info(f"🎬 [PRESENTATION] Using template: {template_id}")
    
    # Get vault context for content — only if SaaS conditions are all met
    _has_prefetched = bool(body.structured_data_context)
    from composer_query import saas_enabled as _saas_enabled
    _should_fetch_saas = _saas_enabled(
        use_personal_data=body.use_personal_data,
        folder_ids=body.folder_ids,
        include_supplementary=body.include_supplementary
    )
    logger.info(
        f"🎬 [PRESENTATION] SaaS fetch: {'enabled' if _should_fetch_saas else 'disabled'} "
        f"(personal={body.use_personal_data}, folders={bool(body.folder_ids)}, "
        f"supplementary={body.include_supplementary}, prefetched={_has_prefetched})"
    )
    # Vault chunks are PRE-FETCHED via lite-mode retrieval (no sub-query
    # expansion, no reranker, no agentic tool-loop) and injected into the
    # prompt below. This recovers the pre-refactor 1-RTT latency shape for
    # per-slide generation while keeping the agentic path for outline /
    # chat where multi-hop planning actually pays off.
    vault_context = ""
    _use_personal_for_slide = bool(_should_fetch_saas) and bool(body.folder_ids)
    structured_data_context = ""
    if _has_prefetched:
        structured_data_context = body.structured_data_context
        logger.info(f"🎬 [PRESENTATION] Using prefetched structured data ({len(structured_data_context)} chars)")
    elif _should_fetch_saas:
        structured_data_context = await _fetch_structured_schema_context(
            user_id, folder_ids=body.folder_ids, log_prefix="PRESENTATION",
            slide_info=body.slide_info,
            user_query=body.presentation_goal,
        )

    # Pre-bind: focused Milvus top-k for THIS slide, query keyed to
    # title + content_hint. Returns "" when folders are empty / no match.
    #
    # Fast path: when the client supplied a `prefetched_vault_block`
    # (deck-level batch prefetch via /presentation/prefetch-vault-chunks),
    # skip the per-slide /embeddings + Milvus + Mongo round-trip entirely.
    # The batch endpoint already produced this block from a single OpenAI
    # embed call for all slides, avoiding the rate-limit retry storm we'd
    # otherwise see when N slides fire concurrent embed requests.
    slide_vault_block = ""
    if body.prefetched_vault_block:
        slide_vault_block = body.prefetched_vault_block
        logger.info(
            f"⚡ [PRESENTATION-SLIDE-LITE] using prefetched vault block "
            f"({len(slide_vault_block)} chars) — skipping per-slide retrieval"
        )
    elif _use_personal_for_slide:
        from services.personal_data_tool import retrieve_vault_context_for_prompt
        _slide_query = (
            f"{body.slide_info.get('title', '')}. "
            f"{body.slide_info.get('content_hint', '')}"
        ).strip(" .")
        slide_vault_block = await retrieve_vault_context_for_prompt(
            query=_slide_query or body.presentation_goal,
            user_id=user_id,
            folder_ids=body.folder_ids,
            max_results=3,
            log_prefix="PRESENTATION-SLIDE-LITE",
        )

    # Build simplified system prompt for template-based generation
    slot_format = get_slot_prompt_format(template_id)
    example_json = get_example_json_for_template(template_id)
    
    # Determine icon instruction based on set
    icon_instruction = "kebab-case Lucide names (chart-bar, shield-check, users, lightbulb, rocket)"
    if body.icon_set == "ionicons":
        icon_instruction = "kebab-case Ionicons names (home-outline, settings-sharp, partly-sunny, add-circle)"

    _is_exec_template = (body.template_id or "").startswith("exec_")

    # Style: ai-auto → free; explicit palette → respect it (allow override for emphasis).
    is_auto_style = not body.style or body.style.get('id') == 'ai-auto'
    if is_auto_style:
        style_rule = "Style: full palette freedom."
    else:
        style_rule = f"Style palette: bg={body.style.get('slideBackground')}, text={body.style.get('textPrimary')}. Override per element when needed."

    # Profile resolution. Two paths only:
    #   - "corporate"  → design guards engaged (storyboard-locked bg, server
    #                    enforcement, overlap protection, slot retries).
    #   - "general"    → LLM is in charge. We only sanitize for renderer
    #                    safety (SVG fix-ups, bullets→text, ID assignment,
    #                    off-canvas clamp) — zero design enforcement.
    from slide_templates import profile_always_emits_background
    _profile = getattr(body, 'deck_profile', None) or 'corporate'
    _profile_requires_bg = profile_always_emits_background(_profile)
    _is_general_profile = (_profile in ("general", "general_with_images"))
    _deck_bg_style = (body.deck_plan or {}).get("background_style") if isinstance(getattr(body, "deck_plan", None), dict) else None
    _deck_bg_desc = (_deck_bg_style or {}).get("description") if isinstance(_deck_bg_style, dict) else None
    _deck_bg_motif = (_deck_bg_style or {}).get("motif") if isinstance(_deck_bg_style, dict) else None
    _deck_bg_palette = (_deck_bg_style or {}).get("palette_overlay") if isinstance(_deck_bg_style, dict) else None

    if _profile_requires_bg:
        # Corporate profile: MUST emit background_image, and it MUST adhere to
        # the deck's shared background_style so all slides look like one book.
        _bg_hint_bits = []
        if _deck_bg_motif:
            _bg_hint_bits.append(f"motif={_deck_bg_motif}")
        if _deck_bg_palette:
            _bg_hint_bits.append(f"palette={_deck_bg_palette}")
        _bg_hint = (" (" + ", ".join(_bg_hint_bits) + ")") if _bg_hint_bits else ""
        _bg_desc_block = f'\n  Deck-wide bg description (apply to THIS slide too): "{_deck_bg_desc}".' if _deck_bg_desc else ""
        bg_image_rule = (
            'background_image (REQUIRED — corporate profile): emit sibling field '
            '"background_image": {"imageDescription":"...","imageType":"background"}. '
            f'The imageDescription MUST conform to the DECK\'S SHARED background style{_bg_hint} '
            f'so every slide reads as part of one artefact — same atmosphere, same lighting, '
            f'same texture family, same palette overlay. Vary the specific scene per slide, '
            f'but keep the visual language IDENTICAL.{_bg_desc_block}'
        )
    else:
        # General profile: completely up to the LLM. No prescription.
        bg_image_rule = "background_image: your call — emit a sibling `background_image` field if it serves the slide."

    # The unified authoring guidance lives in services/authoring_guidance.py
    # so presentation and printable share the same capability palette and
    # template-is-guidance philosophy.
    from services.authoring_guidance import COMMON_AUTHORING_GUIDANCE_PRESENTATION
    from services.storyboard import render_for_prompt as _render_storyboard_for_prompt

    # Deck-level storyboard (palette + per-slide intent/mode/tone). When
    # supplied by the client (from the outline-stream `storyboard` SSE event),
    # this is the deck's shared design language — every slide grounds its
    # colours and visual mode in it so the deck reads as one coherent artefact.
    _storyboard_block = _render_storyboard_for_prompt(getattr(body, "deck_plan", None), body.slide_index)

    system_prompt = f"""You are designing slide {body.slide_index + 1} of {body.total_slides} ({body.presentation_type}).

{COMMON_AUTHORING_GUIDANCE_PRESENTATION}

{(
    (
        "Deck storyboard (LOCKED — every slide shares this design):"
        if not _is_general_profile
        else (
            "Deck storyboard (GUIDANCE ONLY, NOT MANDATORY — general profile gives you full creative freedom). "
            "Treat the palette, typography, motif, background style and per-slide intent below as a reference "
            "for deck cohesion. Use your own design intuition to make this slide great: deviate from the palette / "
            "intent / template_family whenever the slide's content suggests a better treatment. Don't optimize for "
            "matching the storyboard — optimize for the best possible slide for this content."
        )
    ) + chr(10) + _storyboard_block + chr(10)
) if _storyboard_block else ""}
Matched template (starting point):
{slot_format}

Example output shape:
{example_json}

Icons: {icon_instruction}
{bg_image_rule}
{style_rule}

JSON only."""

    # Build user prompt
    prev_context = ""
    if body.previous_slides:
        prev_summaries = [f"Slide {i+1}: {s.get('title', 'Unknown')}" 
                         for i, s in enumerate(body.previous_slides[-2:])]
        prev_context = f"\nPREVIOUS SLIDES: " + ", ".join(prev_summaries)

    user_prompt = f"""Fill content for slide {body.slide_index + 1} of {body.total_slides}.

PRESENTATION: {body.presentation_goal}
TYPE (CRITICAL - STRICTLY FOLLOW): {body.presentation_type}

SLIDE INFO:
- Title: {body.slide_info.get('title', 'Untitled')}
- Content: {body.slide_info.get('content_hint', '')}
{prev_context}

{structured_data_context}
{slide_vault_block}
{f"SPECIAL INSTRUCTIONS FROM USER (MUST FOLLOW):{chr(10)}{body.special_instructions}" if body.special_instructions else ""}

Generate the JSON with slot content: And double check that layout is proper and no overalapping of shapes text etc for a clean pixel perfect presentation rendering in UI"""

    try:
        # Single LLM call per slide — vault chunks are already injected via
        # `slide_vault_block` above (lite-mode pre-fetch), so the agentic
        # tool-loop is no longer needed for slot synthesis. RETRY logic
        # handles empty responses and shape-mismatched JSON (model returns
        # a flat {"content": "..."} envelope instead of the slot-keyed
        # schema). Compute_fact / personal_data_tool tool-calling is
        # intentionally dropped here — structured aggregates already arrive
        # via `structured_data_context`, and per-slide vault passages
        # already arrive via `slide_vault_block`.
        required_slots = template.get("required_slots", [])
        ai_response = ""
        slot_data = None
        slots: dict = {}
        last_parse_error: Optional[str] = None
        retry_hint = ""
        for attempt in range(3):
            try:
                effective_user_prompt = user_prompt + retry_hint
                ai_response = await asyncio.to_thread(
                    llm_call,
                    system_prompt=_grounded_sys(system_prompt),
                    user_prompt=effective_user_prompt,
                    model=None,
                    user_id=user_id,
                    # 32k output budget. With reasoning enabled, the model
                    # can spend several thousand tokens on internal reasoning
                    # before emitting the JSON. Slides with an SVG diagram in
                    # extra_elements + rich slot text were truncating at the
                    # prior 8k→16k caps — the parser then saw empty content
                    # and retried, only to truncate again. Doubled to 32k for
                    # headroom for reasoning + SVG markup + slot content.
                    max_tokens=32000,
                    temperature=0.2,
                    top_p=0.95,
                    tier="large",
                    reasoning_effort="low",
                )

                if not ai_response or len(ai_response.strip()) <= 10:
                    logger.warning(f"⚠️ [PRESENTATION] Empty/short response (attempt {attempt+1}/3). Retrying…")
                    await asyncio.sleep(1)
                    continue

                # Parse JSON
                try:
                    json_str = extract_json_from_response(ai_response)
                    slot_data = json.loads(json_str)
                except Exception as parse_err:
                    last_parse_error = str(parse_err)
                    logger.warning(f"⚠️ [PRESENTATION] JSON parse failed (attempt {attempt+1}/3): {parse_err}. Retrying…")
                    retry_hint = (
                        f"\n\nPREVIOUS ATTEMPT RETURNED INVALID JSON ({parse_err}). "
                        f"Output a single valid JSON object with the exact slot keys: {required_slots}."
                    )
                    await asyncio.sleep(1)
                    continue

                # Defensive: strip any [vault:...]/[doc:...]/[source:...]
                # citation markers that leaked through into slot text.
                # These are grounding-only references and look like garbage
                # when they render in slide bullets / titles. Done BEFORE
                # extracting slots so downstream code (background_image,
                # missing-slot retry, build_elements_from_template) sees the
                # cleaned tree.
                from services.personal_data_tool import strip_citation_tags
                if isinstance(slot_data, dict):
                    slot_data = strip_citation_tags(slot_data)

                slots = slot_data.get("slots", slot_data) if isinstance(slot_data, dict) else {}
                if not isinstance(slots, dict):
                    slots = {}

                # Shape-mismatch detector: if the model returned NONE of the
                # required slot keys (e.g. just {"content": "..."}), retry
                # with an explicit schema reminder.
                def _slot_has_substantive_content(s_val) -> bool:
                    """A slot counts as filled only when it actually carries
                    rendering content — not just a wrapper dict with `fill`
                    or other styling. Otherwise the retry below treats
                    `{"bullets": {"fill": "#xxx"}}` as "present" and the
                    bullets card renders blank.
                    """
                    if s_val is None:
                        return False
                    if isinstance(s_val, dict):
                        for key in ("content", "iconName", "imageDescription", "chartConfig", "svgContent", "text"):
                            v = s_val.get(key)
                            if isinstance(v, str) and v.strip():
                                return True
                            if isinstance(v, list) and any(str(x).strip() for x in v):
                                return True
                            if isinstance(v, dict) and v:
                                return True
                        return False
                    if isinstance(s_val, str):
                        return bool(s_val.strip())
                    if isinstance(s_val, list):
                        return any(str(x).strip() for x in s_val)
                    return bool(s_val)

                missing_slots = [s for s in required_slots if not _slot_has_substantive_content(slots.get(s))]
                shape_ok = bool(required_slots) and any(s in slots for s in required_slots)
                if required_slots and not shape_ok and attempt < 2:
                    logger.warning(
                        f"⚠️ [PRESENTATION] Shape mismatch: parsed keys {list(slots.keys())} "
                        f"contain none of required {required_slots} (attempt {attempt+1}/3). Retrying…"
                    )
                    retry_hint = (
                        f"\n\nPREVIOUS ATTEMPT RETURNED THE WRONG JSON SHAPE. "
                        f"You returned keys {list(slots.keys())}, but this template requires top-level keys "
                        f"{required_slots}. Output strictly: "
                        + "{ "
                        + ", ".join(f'"{s}": {{ "content": "..." }}' for s in required_slots)
                        + " }. NO other top-level keys, NO 'content' wrapper around the whole object."
                    )
                    await asyncio.sleep(1)
                    continue

                # Partial-mismatch detector: shape is right (some required
                # slots present) but at least one required slot is blank or
                # missing. Common case: `exec_argument` `bullets` slot is
                # consistently dropped by the LLM, leaving an empty card.
                # CORPORATE profile only — GENERAL profile treats the
                # template as pure guidance, so a blank slot is a valid
                # design choice, not a defect.
                if required_slots and missing_slots and attempt < 2 and not _is_general_profile:
                    logger.warning(
                        f"⚠️ [PRESENTATION] Required slots missing: {missing_slots} "
                        f"(template={template_id}, attempt {attempt+1}/3). Retrying…"
                    )
                    _slot_examples = {
                        "bullets": '"• Demand grows 40% in emerging markets by 2030\\n• Renewables overtake coal in the power mix\\n• Investment in transmission must double\\n• Hydrogen scales as a long-duration storage backbone"',
                        "title": '"Your Action-Oriented Slide Title Here"',
                        "subhead": '"One-sentence subhead that explains the slide claim."',
                        "kicker": '"SECTION LABEL"',
                        "takeaway": '"Single-line takeaway in accent color."',
                    }
                    _slot_examples_str = ", ".join(
                        f'"{s}": {{ "content": {_slot_examples.get(s, """"...""")} }}'
                        for s in missing_slots
                    )
                    retry_hint = (
                        f"\n\nPREVIOUS ATTEMPT OMITTED REQUIRED SLOTS: {missing_slots}. "
                        f"You MUST include these slots — they are mandatory for this template. "
                        f"Add them to your JSON output with substantive content. Example shapes: "
                        + "{ " + _slot_examples_str + " }. "
                        f"For 'bullets' slots specifically, output a single string with 4-5 lines "
                        f"separated by \\n, each starting with • (bullet character) and containing "
                        f"a complete sentence ≤14 words. Do NOT return bullets as a JSON array."
                    )
                    await asyncio.sleep(1)
                    continue

                # Good enough — break out
                break
            except Exception as e:
                logger.error(f"⚠️ [PRESENTATION] Template generation attempt {attempt+1} failed: {e}")
                if attempt == 2:
                    raise e
                await asyncio.sleep(1)

        if not ai_response or slot_data is None:
            raise ValueError(f"AI returned empty/invalid response after 3 attempts (last_parse_error={last_parse_error})")

        # Log raw AI response for debugging
        logger.debug(f"🎬 [PRESENTATION] Raw AI response for template {template_id}: {ai_response[:500]}...")

        # Log parsed slots for debugging
        logger.info(f"🎬 [PRESENTATION] Parsed slots: {list(slots.keys())}")

        # Validate that required slots are filled
        missing_slots = [s for s in required_slots if not _slot_has_substantive_content(slots.get(s))]
        if missing_slots:
            logger.warning(f"🎬 [PRESENTATION] Missing required slots after retries: {missing_slots}")

        # Last-resort fallback for `bullets` slots — if the LLM still won't
        # produce content after 3 attempts, synthesize bullets from the
        # other slots so the slide isn't blank. This handles the recurring
        # `exec_argument` failure mode where the bullets card rendered as
        # a solid white rectangle with nothing in it.
        # GENERAL profile: no bullets fallback synthesis. Template is pure
        # guidance there — if the LLM left a slot blank, it meant to.
        for _slot_name, _slot_def in (template.get("slots", {}).items() if not _is_general_profile else []):
            if _slot_def.get("type") != "bullets":
                continue
            if _slot_has_substantive_content(slots.get(_slot_name)):
                continue
            # Synthesize from kicker / subhead / takeaway / content_hint —
            # whatever the LLM did give us — split into sentence-ish chunks.
            _source_bits: List[str] = []
            for _src_key in ("kicker", "subhead", "takeaway"):
                _v = slots.get(_src_key)
                if isinstance(_v, dict):
                    _t = _v.get("content") or ""
                elif isinstance(_v, str):
                    _t = _v
                else:
                    _t = ""
                if isinstance(_t, str) and _t.strip():
                    _source_bits.append(_t.strip())
            _content_hint = (body.slide_info.get("content_hint") or "").strip()
            if _content_hint:
                _source_bits.append(_content_hint)
            _joined = " ".join(_source_bits)
            _sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", _joined) if len(s.strip()) >= 8]
            if not _sentences:
                _sentences = [
                    f"Key takeaway from {body.slide_info.get('title', 'this slide')}.",
                    "Refer to the title and subhead for the headline argument.",
                    "Supporting evidence is detailed in the source material.",
                    "See the takeaway for the bottom-line conclusion.",
                ]
            _fallback_lines = [f"• {s}" for s in _sentences[:5]]
            slots[_slot_name] = {"content": "\n".join(_fallback_lines)}
            logger.warning(
                f"🩹 [PRESENTATION] Synthesized fallback bullets for slot '{_slot_name}' "
                f"({len(_fallback_lines)} lines from {len(_source_bits)} source slots)"
            )

        # Build final elements from template + slot content + style
        elements = build_elements_from_template(template, slots, body.style or {})

        # Escape hatch: the authoring guidance explicitly tells the LLM it can
        # tweak / extend / replace the template by emitting an `extra_elements`
        # array alongside `slots`. Each entry is a fully-positioned element
        # (text / shape / image_placeholder / chart / svg_diagram / icon)
        # that gets appended to the slide. We do minimal validation here —
        # the position-clamping pass below will keep them inside the canvas.
        _extra_elements = slot_data.get("extra_elements") if isinstance(slot_data, dict) else None
        if isinstance(_extra_elements, list) and _extra_elements:
            # CORPORATE profile only: build the filled-content-bbox list used
            # by the overlap dropper below. GENERAL profile is hands-off —
            # the LLM is free to overlay anything; we trust its design call.
            def _bbox(o):
                try:
                    return (
                        float(o.get("x", 0) or 0),
                        float(o.get("y", 0) or 0),
                        float(o.get("x", 0) or 0) + float(o.get("width", 0) or 0),
                        float(o.get("y", 0) or 0) + float(o.get("height", 0) or 0),
                    )
                except (TypeError, ValueError):
                    return None

            def _overlap_area(a, b):
                if not a or not b:
                    return 0.0
                ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
                iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
                return ix * iy

            def _area(box):
                return max(0.0, (box[2] - box[0]) * (box[3] - box[1])) if box else 0.0

            # Empty for general profile → no extra_element will ever be
            # dropped for overlap. Corporate keeps the protection.
            _filled_content_bboxes = []
            if not _is_general_profile:
                for _el in elements:
                    if not isinstance(_el, dict):
                        continue
                    # Only block against text/chart/svg/image content — not against
                    # decorative shapes / backgrounds which are meant to be sat on.
                    if _el.get("type") not in ("text", "chart", "svg_diagram", "image_placeholder"):
                        continue
                    # Image placeholders that are slide backgrounds (full-canvas,
                    # zIndex 0) shouldn't block either.
                    if _el.get("type") == "image_placeholder" and _el.get("imageType") == "background":
                        continue
                    _b = _bbox(_el)
                    if _b and _area(_b) > 100:  # ignore tiny degenerate boxes
                        _filled_content_bboxes.append((_el.get("id", "?"), _b, _el.get("type")))

            _accepted = 0
            _dropped_overlap = 0
            _slide_idx_ms = int(time.time() * 1000)
            for _i, _extra in enumerate(_extra_elements):
                if not isinstance(_extra, dict):
                    continue
                _etype = _extra.get("type")
                if _etype not in ("text", "shape", "image_placeholder", "chart", "svg_diagram", "icon", "bullets", "numbered_steps", "card"):
                    logger.warning(f"🎨 [PRESENTATION] extra_elements[{_i}] dropped: unknown type={_etype!r}")
                    continue
                # Overlap check: drop the extra if it geometrically lands on a
                # filled content slot (>50% of extra OR >30% of slot). This
                # catches the failure mode where the LLM doubles content —
                # filling `slots.content` AND adding icon+caption pairs at the
                # same coordinates, producing visual garbage on render.
                # Decorative shapes (icons, accent bars, dividers) are exempt
                # because they're meant to overlay content for emphasis.
                _ebbox = _bbox(_extra)
                if _ebbox and _etype not in ("icon", "shape"):
                    _earea = _area(_ebbox)
                    _conflict = None
                    for _slot_id, _sbox, _stype in _filled_content_bboxes:
                        _ov = _overlap_area(_ebbox, _sbox)
                        _sarea = _area(_sbox)
                        if _earea > 0 and _sarea > 0:
                            _ov_of_extra = _ov / _earea
                            _ov_of_slot = _ov / _sarea
                            if _ov_of_extra > 0.5 or _ov_of_slot > 0.3:
                                _conflict = (_slot_id, _stype, _ov_of_extra, _ov_of_slot)
                                break
                    if _conflict:
                        _sid, _stype, _ov_e, _ov_s = _conflict
                        logger.warning(
                            f"🎨 [PRESENTATION] extra_elements[{_i}] (type={_etype}) dropped: "
                            f"overlaps filled slot '{_sid}' (type={_stype}, "
                            f"{int(_ov_e*100)}% of extra / {int(_ov_s*100)}% of slot)"
                        )
                        _dropped_overlap += 1
                        continue
                # Bullets type → text (frontend has no bullets renderer)
                if _etype == "bullets":
                    _raw = _extra.get("content", "")
                    if isinstance(_raw, list):
                        _raw = "\n".join(f"• {str(x).strip().lstrip('•').lstrip('-').lstrip('*').strip()}" for x in _raw if str(x).strip())
                    elif isinstance(_raw, str) and _raw and "•" not in _raw:
                        _raw = "\n".join(f"• {line.strip().lstrip('-').lstrip('*').strip()}" for line in _raw.split("\n") if line.strip())
                    _extra["type"] = "text"
                    _extra["textType"] = _extra.get("textType", "bullets")
                    _extra["content"] = _raw
                # SVG diagram in extra_elements: run same sanitizer the slot
                # path uses (fixes <circle y="N"> → <circle cy="N">, bare & →
                # &amp;, viewBox normalization) so LLM-emitted SVG renders.
                if _etype == "svg_diagram":
                    _svg = _extra.get("svgContent") or _extra.get("svg") or ""
                    if isinstance(_svg, str) and _svg.strip():
                        try:
                            from svg_diagram_prompts import sanitize_svg as _sanitize_svg
                            _exp_w = int(_extra.get("width") or 0) or None
                            _exp_h = int(_extra.get("height") or 0) or None
                            _ok, _cleaned, _err = _sanitize_svg(_svg, expected_width=_exp_w, expected_height=_exp_h)
                            if _ok and _cleaned:
                                _extra["svgContent"] = _cleaned
                            elif _err:
                                logger.warning(f"🎨 [PRESENTATION] extra_elements[{_i}] svg sanitize failed: {_err}")
                        except Exception as _sanitize_exc:
                            logger.warning(f"🎨 [PRESENTATION] extra_elements[{_i}] svg sanitize errored: {_sanitize_exc}")
                # Ensure every extra element has an id so the canvas can track it
                if not _extra.get("id"):
                    _extra["id"] = f"extra_{_slide_idx_ms}_{_i}"
                # zIndex default — sit above template shapes, below footer
                if "zIndex" not in _extra:
                    _extra["zIndex"] = 25
                elements.append(_extra)
                _accepted += 1
                # Once accepted, this extra becomes a potential collision
                # target for subsequent extras (text element overlapping
                # another text element is also bad).
                if _ebbox and _etype in ("text", "chart", "svg_diagram", "image_placeholder"):
                    _filled_content_bboxes.append((_extra.get("id", "?"), _ebbox, _etype))
            if _accepted or _dropped_overlap:
                logger.info(
                    f"🎨 [PRESENTATION] Accepted {_accepted}/{len(_extra_elements)} extra_elements "
                    f"({_dropped_overlap} dropped for overlap)"
                )

        # Background image handling. CORPORATE profile: enforce + synthesize
        # if missing. GENERAL profile: no guard — take whatever the LLM
        # emitted (including no bg if it chose that). The "drop bg for
        # diagram/has_image=False template" rule is intentionally GONE
        # for general — the LLM is in charge of that decision now.
        bg_image_data = slot_data.get("background_image")
        if _profile_requires_bg and not bg_image_data and _deck_bg_desc:
            # Corporate guarantee: if the LLM forgot to emit background_image,
            # synthesize from the deck-wide style so every slide still gets
            # the shared look.
            bg_image_data = {"imageDescription": _deck_bg_desc, "imageType": "background"}
            logger.info(
                f"\U0001F3A8 [PRESENTATION] Synthesized fallback background_image from deck storyboard "
                f"(template={template_id}, profile={_profile})"
            )
        if isinstance(bg_image_data, str):
            bg_image_data = {"imageDescription": bg_image_data}
        if bg_image_data and isinstance(bg_image_data, dict) and bg_image_data.get("imageDescription"):
            bg_element = {
                "id": f"bg_img_{int(time.time() * 1000)}",
                "type": "image_placeholder",
                "imageType": "background",
                "imageDescription": bg_image_data["imageDescription"],
                "x": 0,
                "y": 0,
                "width": 960,
                "height": 540,
                "zIndex": 0,
                "opacity": 0.3,
                "generationQuality": "premium",
            }
            elements.insert(0, bg_element)
            logger.info(f"🎨 [PRESENTATION] Background image added: {bg_image_data['imageDescription'][:80]}")
        # No server-side fallback — if the LLM didn't emit background_image
        # (or this is a diagram template), the slide simply renders without
        # one. Server-side fabrication was over-engineering: the LLM owns
        # the decision and the description.
        
        # Get styled background
        styled = apply_style_to_template(template, body.style or {})
        
        # Final pass: Ensure generationQuality is set for image placeholders
        for el in elements:
            if el.get("type") == "image_placeholder":
                el["generationQuality"] = getattr(body, "generation_quality", "premium")

        # Priority: 1. AI Override, 2. Style Default, 3. White
        # EXCEPT for CORPORATE-profile slides on executive templates with a
        # declared backgroundColor (every `exec_*` template, including the
        # `_dark` family): the template itself is the authoritative design
        # surface for corporate — the AI must not turn an `exec_title_dark`
        # deck into white. In GENERAL profile the LLM is free to override
        # any bg colour, even on exec templates.
        ai_bg = slot_data.get("backgroundColor")
        style_bg = body.style.get("slideBackground", "#ffffff") if body.style else "#ffffff"
        _template_locks_bg = (
            bool(template.get("backgroundColor"))
            and template_id.startswith(("exec_", "exec_pg_"))
            and not _is_general_profile
        )
        if _template_locks_bg:
            background_color = styled.get("backgroundColor") or template.get("backgroundColor")
            if ai_bg and ai_bg.lower() != background_color.lower():
                logger.info(
                    f"🎨 [PRESENTATION] Ignoring AI backgroundColor={ai_bg} for "
                    f"template {template_id} — template-locked to {background_color}"
                )
        else:
            background_color = ai_bg or styled.get("backgroundColor", style_bg)
        
        slide_data = {
            "template": template_id,
            "title": body.slide_info.get("title", ""),
            "elements": elements,
            "backgroundColor": background_color,
        }
        
        logger.info(f"🎬 [PRESENTATION] Template slide generated with {len(elements)} elements")
        logger.info(f"📄 [DEBUG] Template Slide JSON: {json.dumps(slide_data)}")

        # Resolve _data_request placeholders against the user's structured files.
        # Runs the sandbox per placeholder and substitutes real values in-place.
        if DATA_FILLER_AVAILABLE:
            try:
                fill_report = await fill_data_requests(
                    slide_data,
                    user_id=user_id,
                    folder_ids=getattr(body, "folder_ids", None),
                    log_prefix="PRESENTATION",
                )
                if fill_report.get("data_warnings"):
                    slide_data["_data_warnings"] = fill_report["data_warnings"]
            except Exception as exc:  # noqa: BLE001 — never block slide on filler errors
                logger.warning(f"📊 [PRESENTATION] data filler raised: {exc}")

        # AI-powered chart fix: detect malformed chartConfigs and ask AI to regenerate
        slide_data = await _fix_malformed_charts_with_ai(slide_data, user_id)
        
        # Fix numbered_step sequential numbering
        _fix_numbered_step_numbers(slide_data.get("elements", []))
        # Normalize icon fields (AI sometimes sends 'icon' instead of 'iconName')
        _normalize_icon_fields(slide_data.get("elements", []))
        
        # Layout refinement: LLM pass to fix misplaced objects/text (DISABLED — saving credits/latency)
        # logger.info("🔧 [LAYOUT-FIX] Running layout refinement pass on template slide...")
        # slide_data = await refine_slide_layout(slide_data, user_id)
        
        # Post-process: Fix overlapping elements (deterministic safety net)
        # slide_data = fix_overlapping_elements(slide_data)  # DISABLED: testing LLM-based layout fixer
        # Compact title position: pull layout up if title drifted too far down
        # slide_data = _compact_title_position(slide_data)  # DISABLED: testing LLM-based layout fixer
        
        # Post-process: Shrink font sizes to fit content within fixed-size template slots
        slide_data = fit_content_to_slots(slide_data)

        # Validate element positions: clamp out-of-bounds, fix invalid dimensions
        validate_element_positions(slide_data.get("elements", []), PRESENTATION_CANVAS)

        # Inject the consistent executive footer (CITRA | DECK on the left,
        # page / total on the right). Idempotent and a no-op when the
        # template isn't in the exec_* family.
        inject_exec_footer(
            slide_data["elements"],
            template,
            deck_title=(body.presentation_goal or "")[:48],
            page=int(body.slide_index or 0) + 1,
            total=int(body.total_slides or 1),
            canvas_width=PRESENTATION_CANVAS.width,
            canvas_height=PRESENTATION_CANVAS.height,
        )

        # Build response — include credit warning if layout fix hit insufficient credits.
        # `critique_recommended` is always True — the vision-critique pass
        # runs on every rendered slide regardless of profile. Even templated
        # corporate slides can have subtle defects the deterministic post-
        # processor misses (overflow against template padding, icon-text
        # overlap inside cards, low-contrast text on the storyboard-locked
        # background image). Cost is one vision call per slide; benefit is
        # uniform visual quality across both paths.
        response = {
            "success": True,
            "slide": slide_data,
            "critique_recommended": True,
        }
        if slide_data.pop("_credits_exhausted", False):
            response["credits_warning"] = {
                "error": "insufficient_credits",
                "message": slide_data.pop("_credits_message", "Insufficient credits"),
                "balance": slide_data.pop("_credits_balance", 0),
            }
            logger.warning(f"💰 [PRESENTATION] Including credits_warning in slide response")
        else:
            slide_data.pop("_credits_message", None)
            slide_data.pop("_credits_balance", None)
        return response
        
    except json.JSONDecodeError as e:
        logger.error(f"🎬 [PRESENTATION] JSON parse error in template generation: {e}")
        # Retry with bullets template as safe fallback
        logger.info("🎬 [PRESENTATION] Retrying with bullets template as fallback")
        body.template_id = "bullets"
        return await generate_slide_with_template(body, user_id)
    except HTTPException:
        raise  # Propagate 402 insufficient_credits and other HTTP errors as-is
    except Exception as e:
        logger.error(f"🎬 [PRESENTATION] Template slide generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def refine_slide_layout(slide_data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    Second LLM pass: Fix layout issues in a generated slide.
    Corrects misplaced objects, overlapping text, off-canvas elements,
    and poor spacing. Does NOT change content — only geometry.
    Returns the corrected slide_data dict (falls back to original on failure).
    """
    system_prompt = """You are a Presentation Layout QA Expert. Your ONLY job is to fix the spatial layout of a JSON slide.

CANVAS: 960×540 pixels (16:9 landscape). ABSOLUTE BOUNDS: x ≥ 40, y ≥ 40, x+width ≤ 920, y+height ≤ 500. NOTHING may exceed these limits.

STRICT RULES — FOLLOW EVERY ONE:
1. PRESERVE ALL ELEMENTS — never add, remove, merge, or reorder elements.
2. PRESERVE ALL CONTENT — never change "content", "title", "description", "iconName", "imageDescription", "imageType", "chartConfig", "number", or "shapeType".
3. PRESERVE ALL STYLING — never change "color", "fill", "backgroundColor", "borderRadius", "opacity", "borderColor", "fontFamily", "fontWeight", "fontStyle", or "lineHeight".
4. YOU MAY ONLY MODIFY these geometry/layout fields: "x", "y", "width", "height", "fontSize", "zIndex", "textAlign".
5. Also fix children geometry (relative x, y, width, height, fontSize inside parent).

LAYOUT FIXES TO APPLY:
• No element may extend beyond the ABSOLUTE BOUNDS (x+width ≤ 920, y+height ≤ 500). Clamp or resize. This is the highest priority rule.
• OVERLAP DETECTION: For each element compute left=x, top=y, right=x+width, bottom=y+height. Two elements overlap if left1 < right2 AND right1 > left2 AND top1 < bottom2 AND bottom1 > top2. Check EVERY pair. Images, cards, text, shapes — ALL have bounding boxes. Do NOT layer cards or text on top of images. Maintain ≥8px gap between all element bounding boxes.
• COLUMN LAYOUTS: Some slides use multi-column layouts. Elements whose X-centers are in different halves of the canvas (left half < 480, right half ≥ 480) are in SEPARATE COLUMNS — do NOT push one below the other. Only fix overlaps between elements in the SAME column or full-width elements.
• Cards MUST use flat properties (title, description, iconName) directly on the card element. Do NOT split card content into separate sibling text/icon elements.
• Text: estimate rendered height as (ceil(len(content) / floor(width / (fontSize*0.55)))) × fontSize × lineHeight. Ensure the element's height accommodates this.
• If elements are stacked vertically, sort by visual hierarchy: title first, then subtitle, body, images/charts last.
• Background shapes (type:"shape" spanning most of the canvas) should have zIndex ≤ 1; content should have higher zIndex.
• Icons inside cards should be positioned before the title text (lower y).
• CRITICAL: Do NOT move elements significantly from their original positions. Only make MINIMAL adjustments needed to fix genuine overlaps.

OUTPUT: Return the COMPLETE corrected JSON object with the same structure. JSON only — no markdown, no commentary."""

    user_prompt = f"""Fix the layout of this 960×540 presentation slide. Only adjust positions, sizes, fontSize, zIndex, and textAlign. Keep all content and styling intact.

{json.dumps(slide_data)}"""

    try:
        response = await asyncio.to_thread(
            llm_call,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=None,
            user_id=user_id,
            max_tokens=10000,
            temperature=0.2,
            top_p=0.95,
            json_mode=True,
            tier="large",
        )
        if not response or len(response.strip()) < 20:
            logger.warning("⚠️ [LAYOUT-FIX] Empty response from layout fixer, using original")
            return slide_data

        json_str = extract_json_from_response(response)
        fixed = parse_json_robustly(json_str)

        # Sanity: ensure element count didn't change
        orig_count = len(slide_data.get("elements", []))
        fixed_count = len(fixed.get("elements", []))
        if fixed_count != orig_count:
            logger.warning(f"⚠️ [LAYOUT-FIX] Element count mismatch (orig={orig_count}, fixed={fixed_count}), using original")
            return slide_data

        logger.info(f"✅ [LAYOUT-FIX] Slide layout refined successfully ({fixed_count} elements)")
        return fixed

    except HTTPException as he:
        if he.status_code == 402:
            logger.warning(f"⚠️ [LAYOUT-FIX] Insufficient credits during layout refinement, using original layout")
            detail = he.detail if isinstance(he.detail, dict) else {}
            slide_data["_credits_exhausted"] = True
            slide_data["_credits_message"] = detail.get("message", "Insufficient credits") if detail else str(he.detail)
            slide_data["_credits_balance"] = detail.get("balance", 0) if detail else 0
        else:
            logger.error(f"⚠️ [LAYOUT-FIX] HTTP {he.status_code} during layout refinement: {he.detail}, using original")
        return slide_data
    except Exception as e:
        logger.error(f"⚠️ [LAYOUT-FIX] Layout refinement failed: {e}, using original")
        return slide_data



async def generate_slide_legacy(body: GenerateSlideRequest, user_id: str):
    """
    Generate content for a single slide.
    
    Creates text elements, suggests images, and applies layout
    based on the slide outline and presentation style.
    """
    logger.info(f"🎬 [PRESENTATION] Generating slide {body.slide_index + 1}: {body.slide_info.get('title', 'Unknown')}")
    
    # Get vault context for content — only if SaaS conditions are all met
    _has_prefetched = bool(body.structured_data_context)
    from composer_query import saas_enabled as _saas_enabled
    _should_fetch_saas = _saas_enabled(
        use_personal_data=body.use_personal_data,
        folder_ids=body.folder_ids,
        include_supplementary=body.include_supplementary
    )
    logger.info(
        f"🎬 [PRESENTATION] Legacy SaaS fetch: {'enabled' if _should_fetch_saas else 'disabled'} "
        f"(personal={body.use_personal_data}, folders={bool(body.folder_ids)}, "
        f"supplementary={body.include_supplementary}, prefetched={_has_prefetched})"
    )
    # Vault chunks PRE-FETCHED via lite-mode retrieval (no sub-query
    # expansion, no reranker, no agentic tool-loop). Recovers pre-refactor
    # 1-RTT latency for ai-free / legacy slide generation.
    vault_context = ""
    _legacy_use_personal = bool(_should_fetch_saas) and bool(body.folder_ids)

    # Get structured data for charts — use prefetched if available, otherwise fetch per-slide
    structured_data_context = ""
    if _has_prefetched:
        structured_data_context = body.structured_data_context
        logger.info(f"🎬 [PRESENTATION] Legacy slide: Using prefetched structured data ({len(structured_data_context)} chars)")
    elif _should_fetch_saas:
        structured_data_context = await _fetch_structured_schema_context(
            user_id, folder_ids=body.folder_ids, log_prefix="PRESENTATION",
            slide_info=body.slide_info,
            user_query=body.presentation_goal,
        )

    # Pre-bind: focused Milvus top-k for THIS slide. Returns "" when
    # vault is disabled / no match. Honors `prefetched_vault_block` from
    # the deck-level /presentation/prefetch-vault-chunks call so the
    # legacy path benefits from the same batch-embed optimization.
    legacy_slide_vault_block = ""
    if body.prefetched_vault_block:
        legacy_slide_vault_block = body.prefetched_vault_block
        logger.info(
            f"⚡ [PRESENTATION-SLIDE-LEGACY-LITE] using prefetched vault block "
            f"({len(legacy_slide_vault_block)} chars) — skipping per-slide retrieval"
        )
    elif _legacy_use_personal:
        from services.personal_data_tool import retrieve_vault_context_for_prompt
        _legacy_slide_query = (
            f"{body.slide_info.get('title', '')}. "
            f"{body.slide_info.get('content_hint', '')}"
        ).strip(" .")
        legacy_slide_vault_block = await retrieve_vault_context_for_prompt(
            query=_legacy_slide_query or body.presentation_goal,
            user_id=user_id,
            folder_ids=body.folder_ids,
            max_results=3,
            log_prefix="PRESENTATION-SLIDE-LEGACY-LITE",
        )
    
    # Style override — only when the user pinned a specific style (not "ai-auto").
    style_block = ""
    if body.style and body.style.get('id') and body.style.get('id') != 'ai-auto':
        style_block = (
            f"\nUSER-PINNED STYLE: bg={body.style.get('slideBackground', '#fff')}, "
            f"title={body.style.get('textPrimary', '#000')}, "
            f"body={body.style.get('textSecondary', '#333')}, "
            f"accent={body.style.get('accentColor', '#3B82F6')}, "
            f"font={body.style.get('fontFamily', 'Arial')}. Use these unless the storyboard above is supplied."
        )

    # Storyboard slice (deck-wide design language). Same render_for_prompt
    # used by the template path. For the legacy free-form path, the slice
    # is the PRIMARY source of palette / typography / motif / per-slide
    # intent — the LLM should treat it as the deck's design system.
    from services.storyboard import render_for_prompt as _render_storyboard_for_prompt
    from services.authoring_guidance import FREEFORM_AUTHORING_GUIDANCE_PRESENTATION
    _storyboard_block = _render_storyboard_for_prompt(getattr(body, "deck_plan", None), body.slide_index)
    storyboard_section = (
        f"\nDECK STORYBOARD (deck-wide design language — palette, typography, motif, per-slide intent — "
        f"apply consistently across this slide):\n{_storyboard_block}\n"
        if _storyboard_block else ""
    )

    icon_lib = "Ionicons (kebab-case, e.g. home-outline)" if body.icon_set == "ionicons" else "Lucide (kebab-case)"

    system_prompt = f"""You are designing slide {body.slide_index + 1} of {body.total_slides} ({body.presentation_type}).

{FREEFORM_AUTHORING_GUIDANCE_PRESENTATION}

Icons: {icon_lib}.
{storyboard_section}{style_block}

IMAGE PROMPTS (image_placeholder.imageDescription) — describe a photographic scene only:
- Never include text, words, letters, numbers, labels, captions, watermarks, or signage in the description.
- Ground the scene in the slide's geographic / cultural context inferred from goal + title + vault. People, architecture, vegetation, clothing, food, festivals must match the locale (e.g. India → Indian people, locally accurate streets and buildings; never default to Western faces unless the locale is explicitly Western).
- Pattern: <scene>, <lighting>, <composition>, <style cue>, <colour cue>.

CHARTS — when the slide is about numbers/trends, PREFER a `chart` element over an image. Chart types: bar | line | pie | doughnut | radar | polarArea | scatter | bubble. Format:
{{"type":"chart","x":..,"y":..,"width":400,"height":300,"chartConfig":{{"type":"bar","data":{{"labels":[...],"datasets":[{{"label":"...","data":[...],"backgroundColor":["#3B82F6","#10B981"]}}]}}}}}}
Scatter/bubble use point objects. If a `=== COMPUTED DATA ===` block appears below, use its `value` verbatim — those are the ONLY trusted numbers; never fabricate aggregates from schema samples.

SVG DIAGRAMS — for org charts / process flows / cycles / venn / funnel / anatomy diagrams, emit a `svg_diagram` element with `svgContent` (raw SVG string), `fillColor`, `diagramKind`, `diagramTitle`. Use when a structural diagram tells the story better than text or a chart.

BACKGROUND IMAGE — optional top-level field `background_image: {{"imageDescription": "..."}}` (sibling of `elements`, NOT inside it). Scene only, no text.

DESIGN — one idea per slide, vary rhythm vs previous slides, bullets ≤ 14 words, titles ≤ 8 words. Text colour must contrast with whatever the text sits on (card bg, not slide bg, for text inside cards).

TEXT SIZING (CRITICAL — most slides break here):
- For every text element you MUST size `fontSize` and `height` so the `text`/`content` fits the bounding box WITHOUT wrapping the title or clipping body text. Wrapped titles cascade over the element below them and break the layout.
- Estimate visible text width (rough): bold chars ≈ `fontSize × 0.55 × char_count`. Regular ≈ `fontSize × 0.48 × char_count`. The text MUST fit `width` at that fontSize on ONE line (titles, kickers, stat values) OR `height` must accommodate the wrapped lines (body paragraphs).
- TITLES: pick a fontSize that fits the WHOLE title text on one line of the given `width`. If the title is long, EITHER reduce fontSize (e.g. 44→32→28) OR increase `width` (use the full canvas width 880px). Do NOT set `height: 55` and `fontSize: 44` if the title is more than ~24 characters — it WILL wrap and overflow into the elements below.
- BODY PARAGRAPHS: pick a `height` large enough for the wrapped lines (estimate lines = ceil(char_count / chars_per_line) where chars_per_line ≈ `width / (fontSize × 0.5)`; then `height ≈ lines × fontSize × 1.5`). If a paragraph wouldn't fit, prefer a smaller fontSize (12-13) and an explicit `lineHeight: 1.4` over forcing the height up.
- STAT NUMBERS / KICKERS: keep them short (≤ 8 chars for stats, ≤ 6 words for kickers). One line, no wrap.
- Canvas is 960×540. Maximum safe title width is 880 (40px margin each side). Never let any element extend past the canvas edges.

DATA ACCURACY — never hallucinate numbers, dates, names, claims. Use only verifiable facts from the COMPUTED DATA / vault / context. If unbacked, omit.

Output: one JSON object: {{"title":"...", "elements":[...], "background_image":{{...}}|null, "backgroundColor":"#RRGGBB"}}. JSON only, no markdown."""

    # Previous slides context for continuity
    prev_context = ""
    if body.previous_slides:
        prev_summaries = [f"Slide {i+1}: {s.get('title', 'Unknown')} - {s.get('content_summary', '')[:100]}" 
                         for i, s in enumerate(body.previous_slides[-3:])]  # Last 3 slides
        prev_context = f"\n\nPREVIOUS SLIDES FOR CONTEXT:\n" + "\n".join(prev_summaries)

    # Pass image_prompt from outline if available
    image_prompt = body.slide_info.get('image_prompt', '')
    image_instruction = f"\nIMAGE PROMPT (MUST include an image_placeholder element using this description):\n{image_prompt}" if image_prompt else ""

    user_prompt = f"""Design slide {body.slide_index + 1} of {body.total_slides}.

PRESENTATION: {body.presentation_goal}
TYPE (CRITICAL - STRICTLY FOLLOW): {body.presentation_type}

SLIDE INFO:
- Title: {body.slide_info.get('title', 'Untitled')}
- Content: {body.slide_info.get('content_hint', '')}
- Suggested Layout: {body.slide_info.get('layout', 'title_content')}
{image_instruction}
{prev_context}

{legacy_slide_vault_block}
{structured_data_context}

{f"SPECIAL INSTRUCTIONS FROM USER (MUST FOLLOW):{chr(10)}{body.special_instructions}" if body.special_instructions else ""}

Generate the JSON object for this slide. And double check that layout is proper and no overalapping of shapes text etc for a clean pixel perfect presentation rendering in UI """

    try:

        # Call llm_oss (sync, run in thread) with RETRY logic
        ai_response = ""
        slide_data = None
        max_attempts = 4
        # Corrective feedback appended to the user prompt on each retry so the
        # model SELF-CORRECTS instead of blindly re-rolling the same prompt.
        # Empty on the first attempt; populated with the specific failure
        # reason (empty / 0-element / unparseable) before each retry.
        retry_feedback = ""

        # Visibility: the composer fires every slide in parallel, but the
        # semaphore admits only 3 at a time. Log the wait so a queued slide
        # isn't mistaken for a hang — the gap between these two lines is the
        # time this slide spent waiting for a free generation slot.
        _slide_no = body.slide_index + 1
        logger.info(f"⏳ [PRESENTATION] Slide {_slide_no}/{body.total_slides} waiting for LLM generation slot")
        async with _slide_generation_semaphore:
            logger.info(f"▶️ [PRESENTATION] Slide {_slide_no}/{body.total_slides} acquired generation slot — calling LLM")
            for attempt in range(max_attempts):
                try:
                    # Single LLM call per slide — vault chunks are pre-injected
                    # via legacy_slide_vault_block (lite-mode retrieval).
                    # Compute_fact / personal_data_tool tool-calling dropped
                    # to recover pre-refactor latency.
                    ai_response = await asyncio.to_thread(
                        llm_call,
                        system_prompt=_grounded_sys(system_prompt),
                        user_prompt=user_prompt + retry_feedback,
                        model=None,
                        user_id=user_id,
                        # 100k output budget. glm-5.1 in reasoning mode
                        # regularly spends 15-25K tokens on internal reasoning
                        # before emitting the JSON content, and rich slides
                        # then need a large visible JSON body on top of that.
                        # At 50K we still saw batch failures where the
                        # reasoning trace plus a heavy slide left too little
                        # room for complete JSON (parsed to 0 elements /
                        # `finish_reason=length`; prod incident 2026-06-10
                        # slide 5/5 → 0 elements). 100K leaves generous
                        # headroom for reasoning AND the full slide, well
                        # inside the model's 128K context window (input is
                        # only a few thousand tokens here). The llm_oss
                        # wrapper still auto-retries with an even larger
                        # budget on the rare length-truncation past that.
                        max_tokens=100000,
                        temperature=0.2,
                        top_p=0.95,
                        tier="large",
                        reasoning_effort="low",
                    )

                    if not (ai_response and len(ai_response.strip()) > 10):
                        logger.warning(f"⚠️ [PRESENTATION] Legacy generation returned empty or short response (Attempt {attempt+1}/{max_attempts}). Retrying...")
                        retry_feedback = (
                            "\n\nYOUR PREVIOUS RESPONSE WAS EMPTY OR TOO SHORT. "
                            "Return ONE complete, valid JSON slide object with a "
                            "non-empty \"elements\" array — no markdown fences, no commentary."
                        )
                        await asyncio.sleep(min(2 ** attempt, 8))  # Exponential backoff: 1s, 2s, 4s, 8s
                        continue

                    # Parse + validate the slide INSIDE the retry loop. A
                    # response that parses to a slide with ZERO renderable
                    # elements is a generation FAILURE, not a valid empty
                    # slide — e.g. when glm-5.1 emits truncated/malformed JSON
                    # and the robust parser only recovers the nested
                    # background_image object. Previously this slipped past the
                    # retry gate (which only checked the raw string length) and
                    # shipped a BLANK slide into the deck. Fail it here so the
                    # remaining attempts can produce real content. (prod
                    # incident 2026-06-10: slide 5/5 → 0 elements.)
                    candidate = parse_json_robustly(extract_json_from_response(ai_response))
                    if isinstance(candidate, dict) and "elements" not in candidate and "type" in candidate:
                        # LLM returned a single flat element — wrap into a slide.
                        candidate = {"elements": [candidate]}
                    n_elements = len(candidate.get("elements", [])) if isinstance(candidate, dict) else 0
                    if n_elements == 0:
                        logger.warning(
                            f"⚠️ [PRESENTATION] Parsed slide has 0 elements "
                            f"(Attempt {attempt+1}/{max_attempts}) — likely truncated/malformed "
                            f"LLM JSON. Retrying with corrective feedback..."
                        )
                        retry_feedback = (
                            "\n\nYOUR PREVIOUS RESPONSE FAILED: it parsed to a slide with ZERO "
                            "renderable elements (the JSON was likely truncated or malformed). "
                            "Return ONE complete, valid JSON object with a non-empty \"elements\" "
                            "array. Keep it COMPACT — fewer, well-placed elements that fit within "
                            "the slide canvas — and make sure the JSON is fully closed."
                        )
                        await asyncio.sleep(min(2 ** attempt, 8))
                        continue

                    slide_data = candidate
                    if attempt > 0:
                        logger.info(f"✅ [PRESENTATION] Succeeded on attempt {attempt+1}")
                    break
                except Exception as e:
                    error_msg = str(e)
                    is_rate_or_overload = any(k in error_msg for k in ['429', '503', 'rate limit', 'UNAVAILABLE', 'high demand'])
                    logger.error(f"⚠️ [PRESENTATION] Legacy generation attempt {attempt+1}/{max_attempts} failed: {e}")
                    if attempt == max_attempts - 1:
                        raise e
                    # A JSON parse/validation failure (not a transient
                    # rate/overload error) means the model emitted bad output —
                    # tell it so it self-corrects on the next attempt.
                    if not is_rate_or_overload:
                        retry_feedback = (
                            "\n\nYOUR PREVIOUS RESPONSE COULD NOT BE PARSED AS JSON. "
                            "Return ONE complete, valid, fully-closed JSON slide object with a "
                            "non-empty \"elements\" array — no markdown fences, no commentary."
                        )
                    # Use longer backoff for rate limit / overload errors
                    backoff = min(2 ** (attempt + 1), 15) if is_rate_or_overload else min(2 ** attempt, 8)
                    await asyncio.sleep(backoff)  # Exponential backoff on errors

        # Fail loud: every attempt either errored, returned an empty/short
        # response, or parsed to a slide with 0 elements. Do NOT ship a blank
        # slide — surface the failure to the composer so it can retry/report.
        if slide_data is None:
            raise ValueError(
                f"AI returned no usable slide (0 elements) after {max_attempts} attempts"
            )

        # slide_data was parsed, flat-wrapped, and element-count-validated
        # inside the retry loop above. Defensive: strip any
        # [vault:...]/[doc:...]/[source:...] citation markers that leaked into
        # element text — grounding-only references that render as garbage.
        from services.personal_data_tool import strip_citation_tags
        if isinstance(slide_data, dict):
            slide_data = strip_citation_tags(slide_data)

        # Ensure all elements have unique IDs and carry over generationQuality if needed
        for i, element in enumerate(slide_data.get("elements", [])):
            if not element.get("id"):
                element["id"] = f"el_{int(time.time() * 1000)}_{i}"
            if element.get("type") == "image_placeholder":
                element["generationQuality"] = getattr(body, "generation_quality", "premium")
        
        logger.info(f"🎬 [PRESENTATION] Generated slide with {len(slide_data.get('elements', []))} elements")
        logger.info(f"📄 [DEBUG] Legacy Slide JSON: {json.dumps(slide_data)}")
        
        # Detect rogue background: LLM sometimes puts a full-canvas image_placeholder
        # inside elements[] instead of using the root-level background_image field
        if not slide_data.get("background_image"):
            elements = slide_data.get("elements", [])
            for i, el in enumerate(elements):
                if (el.get("type") == "image_placeholder"
                    and el.get("width", 0) >= 880 and el.get("height", 0) >= 460
                    and el.get("x", 99) <= 40 and el.get("y", 99) <= 40
                    and ("bg" in el.get("id", "").lower() or "background" in el.get("id", "").lower())):
                    slide_data["background_image"] = {"imageDescription": el.get("imageDescription", "")}
                    elements.pop(i)
                    logger.info(f"🔄 [PRESENTATION] Converted rogue elements[] background to root background_image")
                    break
        
        # Inject background image element if AI decided to generate one.
        # SKIP when the slide is dominated by an SVG diagram \u2014 the diagram
        # provides the full visual and a photographic backdrop just adds noise.
        has_svg_diagram = any(
            (el.get("type") == "svg_diagram")
            for el in slide_data.get("elements", [])
        )
        bg_image_data = slide_data.get("background_image")
        if has_svg_diagram:
            logger.info("\U0001F3A8 [PRESENTATION] Skipping background image (legacy): slide contains svg_diagram")
            bg_image_data = None
        if isinstance(bg_image_data, str):
            bg_image_data = {"imageDescription": bg_image_data}
        if bg_image_data and isinstance(bg_image_data, dict) and bg_image_data.get("imageDescription"):
            bg_element = {
                "id": f"bg_img_{int(time.time() * 1000)}",
                "type": "image_placeholder",
                "imageType": "background",
                "imageDescription": bg_image_data["imageDescription"],
                "x": 0,
                "y": 0,
                "width": 960,
                "height": 540,
                "zIndex": 0,
                "opacity": bg_image_data.get("opacity", 0.3),
                "generationQuality": "premium",
            }
            slide_data.setdefault("elements", []).insert(0, bg_element)
            logger.info(f"🎨 [PRESENTATION] Background image added (legacy): {bg_image_data['imageDescription'][:80]}")
        # No server-side fallback. If the LLM didn't emit background_image
        # (or this is an SVG diagram slide), the slide renders without one.
        
        # Fix numbered_step sequential numbering
        _fix_numbered_step_numbers(slide_data.get("elements", []))
        # Normalize icon fields (AI sometimes sends 'icon' instead of 'iconName')
        _normalize_icon_fields(slide_data.get("elements", []))

        # Resolve _data_request placeholders against the user's structured files.
        if DATA_FILLER_AVAILABLE:
            try:
                fill_report = await fill_data_requests(
                    slide_data,
                    user_id=user_id,
                    folder_ids=getattr(body, "folder_ids", None),
                    log_prefix="PRESENTATION-LEGACY",
                )
                if fill_report.get("data_warnings"):
                    slide_data["_data_warnings"] = fill_report["data_warnings"]
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"📊 [PRESENTATION-LEGACY] data filler raised: {exc}")

        # Layout refinement: LLM pass to fix misplaced objects/text (DISABLED — saving credits/latency)
        # logger.info("🔧 [LAYOUT-FIX] Running layout refinement pass on legacy slide...")
        # slide_data = await refine_slide_layout(slide_data, user_id)
        
        # Post-process: Fix overlapping elements (deterministic safety net)
        # slide_data = fix_overlapping_elements(slide_data)  # DISABLED: testing LLM-based layout fixer
        # Compact title position: pull layout up if title drifted too far down
        # slide_data = _compact_title_position(slide_data)  # DISABLED: testing LLM-based layout fixer
        
        # Post-process: Shrink font sizes to fit content within fixed-size legacy slots
        slide_data = fit_content_to_slots(slide_data)

        # Validate element positions: clamp out-of-bounds, fix invalid dimensions
        validate_element_positions(slide_data.get("elements", []), PRESENTATION_CANVAS)

        # Build response — include credit warning if layout fix hit insufficient credits.
        # critique_recommended is always True (see contract note in
        # generate_slide_with_template above): vision critique runs on
        # every rendered slide regardless of profile.
        response = {"success": True, "slide": slide_data, "critique_recommended": True}
        if slide_data.pop("_credits_exhausted", False):
            response["credits_warning"] = {
                "error": "insufficient_credits",
                "message": slide_data.pop("_credits_message", "Insufficient credits"),
                "balance": slide_data.pop("_credits_balance", 0),
            }
            logger.warning(f"💰 [PRESENTATION] Including credits_warning in slide response")
        else:
            slide_data.pop("_credits_message", None)
            slide_data.pop("_credits_balance", None)
        return response
        
    except HTTPException:
        raise  # Propagate 402 insufficient_credits and other HTTP errors as-is
    except Exception as e:
        logger.error(f"🎬 [PRESENTATION] Slide generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# @router.post("/presentation/generate-slides-batch")
# async def generate_slides_batch(request: BatchGenerateSlidesRequest):
#     """
#     Generate multiple slides in parallel batches (optimized speed).
#     PRE-FETCHES vault context once, then runs all AI calls in parallel.
#     """
#     logger.info(f"🎬 [PRESENTATION] Batch generating {len(request.items)} slides...")
    
#     import asyncio
    
#     # UNIFIED PARALLEL CONTEXT + GENERATION
#     # Optimization: Run Fetch+Gen in a single parallel task stream
#     # Latency = max(Fetch + Gen) rather than max(Fetch) + max(Gen)
#     logger.info(f"🎬 [PRESENTATION] Starting unified parallel generation for {len(request.items)} slides...")
    
#     # 1. Define unified worker function
#     async def process_slide_item(item):
#         """Fetch context and generate slide in one flow"""
#         vault_context = ""
        
#         # A. Fetch Context (if needed)
#         if item.folder_ids:
#             try:
#                 query = f"{item.presentation_goal} - {item.slide_info.get('title', '')}: {item.slide_info.get('content_hint', '')}"
                
#                 # FORCE PARALLELISM: Run blocking I/O in separate thread
#                 # This wrapper ensures a new event loop handles the async retrieval in a thread
#                 def run_in_thread(func, *args):
#                      import asyncio
#                      loop = asyncio.new_event_loop()
#                      asyncio.set_event_loop(loop)
#                      try:
#                          # Create and run coroutine INSIDE this loop
#                          return loop.run_until_complete(func(*args))
#                      finally:
#                          loop.close()

#                 vault_context = await asyncio.to_thread(
#                     run_in_thread, 
#                     retrieve_vault_context, 
#                     request.user_id,
#                     query,
#                     item.folder_ids,
#                     5 # top_k
#                 )
#             except Exception as e:
#                 logger.warning(f"⚠️ Threaded vault fetch failed, falling back to direct await: {e}")
#                 try:
#                      vault_context = await retrieve_vault_context(
#                         request.user_id,
#                         query,
#                         item.folder_ids,
#                         top_k=5
#                     )
#                 except Exception as e2:
#                     logger.warning(f"⚠️ Vault fetch warning (Slide {item.slide_index}): {e2}")
#                     vault_context = ""
        
#         # B. Generate Slide (using fetched context)
#         return await generate_slide_with_context(item, vault_context)

#     # 2. Execute unified tasks in parallel
#     all_results = []
#     chunk_size = 5
    
#     try:
#         for i in range(0, len(request.items), chunk_size):
#             chunk = request.items[i:i + chunk_size]
#             logger.info(f"🎬 [PRESENTATION] Processing batch {i//chunk_size + 1} ({len(chunk)} slides)")
            
#             # Create unified tasks
#             tasks = [process_slide_item(item) for item in chunk]
            
#             # Run parallel
#             results = await asyncio.gather(*tasks, return_exceptions=True)
            
#             # Process results
#             for idx, res in enumerate(results):
#                 if isinstance(res, Exception):
#                     logger.error(f"❌ Batch item {i+idx} failed: {res}")
#                     all_results.append({
#                         "success": False, 
#                         "error": str(res),
#                         "slide_index": chunk[idx].slide_index
#                     })
#                 else:
#                     all_results.append(res)

#     except Exception as e:
#         logger.error(f"🎬 [PRESENTATION] Batch processing failed: {e}")
#         raise HTTPException(status_code=500, detail=str(e))
        
#     return {
#         "success": True,
#         "slides": [r.get("slide") for r in all_results if r.get("success")],
#         "total": len(request.items),
#         "results": all_results
#     }


# async def generate_slide_with_context(request: GenerateSlideRequest, vault_context: str = ""):
#     """
#     Generate a single slide using PRE-FETCHED vault context.
#     This is the parallel-optimized version - no vault retrieval inside.
#     """
#     logger.info(f"🎬 [PRESENTATION] Generating slide {request.slide_index + 1}: {request.slide_info.get('title', 'Unknown')}")
    
#     # Build system prompt
#     # Build system prompt
#     style_info = ""
#     if request.style:
#         if request.style.get('id') == 'ai-auto':
#             style_info = """
# CRITICAL STYLE INSTRUCTION:
# The user has requested YOU (the AI) to decide the best color palette for this presentation.
# - Analyze the content and topic (e.g., medical, business, creative, tech).
# - SELECT A COLOR PALETTE that enhances the mood and readability.
# - Use this selected palette consistently for this slide.
# - Ensure HIGH CONTRAST between text and background.
# - You are free to choose background colors, text colors, and accents.
# """
#         else:
#             style_info = f"""
# CRITICAL STYLE RULES (YOU MUST FOLLOW THESE):
# - Background: {request.style.get('slideBackground', '#ffffff')}
# - Primary Text: {request.style.get('textPrimary', request.style.get('textStyles', {}).get('title', {}).get('color', '#000000'))}
# - Body Text: {request.style.get('textSecondary', request.style.get('textStyles', {}).get('body', {}).get('color', '#333333'))}
# - Accent: {request.style.get('accentColor', '#3B82F6')}
# - Font: {request.style.get('fontFamily', 'Arial')}

# IMPORTANT: You MUST use the exact hex codes provided above for text 'fill' properties. Do NOT default to white or black unless specified above.
# """
    
#     system_prompt = f"""You are a WORLD-CLASS presentation designer creating visually stunning, professional slides.

# DESIGN PHILOSOPHY:
# - Create BEAUTIFUL, visually-rich slides (not just text!)
# - Use shapes for visual hierarchy and grouping (cards, backgrounds, accents)
# - Use icons to represent concepts visually
# - Balance whitespace with content
# - Create visual interest through layout variety
# {style_info}

# SHAPE USAGE RULES (IMPORTANT):
# - Decorative shapes (circles, backgrounds, accents) are encouraged for visual appeal
# - ALWAYS place decorative shapes at LOW z-index (0-10) so functional elements remain visible
# - Functional shapes (card backgrounds) should use z-index 10-20
# - Lines are great for dividers and visual hierarchy
# - Ensure decorative shapes do NOT overlap or obscure text, icons, or cards

# ELEMENT TYPES YOU CAN USE:
# 1. text - Headlines, body text, bullets
# 2. shape - Rectangles, circles, lines for visual structure
# 3. icon - Lucide-style icon names (e.g., "bar-chart-3", "shield-check", "users", "lightbulb"). Use kebab-case.
# 4. card - Grouped element with background shape + icon + text
# 5. numbered_step - Process flow indicators. MUST include "number" field with sequential integer (1, 2, 3...). Each step MUST have a unique incrementing number.
# 6. image_placeholder - AI-generated image placeholder (use for high-impact visuals)

# IMAGE PLACEHOLDER STRATEGY:
# - Maintain a balance between image generation and text.
# - Use 'image_placeholder' ONLY when the concept requires visualization or an infographic.
# - If a concept is better explained with text, process flows, or icons, prioritize those over images.
# - MAXIMUM 1 content image per slide. The optional background_image is separate and does NOT count toward this limit.
# - Include "imageDescription" with DETAILED description for AI image generation.
# - Examples of good image descriptions:
#   - "Professional businessman giving speech at corporate podium with blue lighting"
#   - "Modern city skyline at sunset with golden hour lighting"
#   - "Team of diverse professionals collaborating around conference table"
# - Format:
#   {{
#     "id": "img_placeholder_1",
#     "type": "image_placeholder",
#     "imageDescription": "Detailed description of the image to generate",
#     "x": 50, "y": 120,
#     "width": 400, "height": 300,
#     "zIndex": 25
#   }}
# - Place images on LEFT or RIGHT side, with text on the opposite side.

# LAYOUT & SIZING RULES (CRITICAL):
# - Canvas: 960x540 pixels.
# - Safe Area: x: 40-920, y: 40-500. Do NOT place text outside this.
# - Sizing:
#   - Icons: Default 48px-64px. MAX 128px unless it is a faint background watermark (opacity < 0.2).
#   - Body Text: Width MUST be > 400px to avoid fragmentation.
# - Spacing:
#   - Avoid overlaps. If Card A is at x:50, w:300, next Card B MUST start > x:380.
#   - Do NOT cover text with icons.
#   - TEXT OVERLAP PREVENTION (CRITICAL): Calculate Y positions carefully!
#     - If title is at y:60 with height:80, next text MUST start at y >= 150
#     - If subtitle is at y:150 with height:50, next text MUST start at y >= 210
#     - Formula: next_y >= previous_y + previous_height + 10px gap
#     - NEVER place two text elements at the same or overlapping Y range

# LAYOUT SAFETY (CRITICAL - PREVENT TEXT/SHAPE OVERLAPS):
# - SAFE DISTANCE: Text must be at least 25px away from any icon or shape edge
# - If icon is at (x:100, y:150, size:60), text below MUST start at y >= 150 + 60 + 25 = 235
# - CHARACTER LIMITS with DYNAMIC FONT SIZING:
#   - Title (max 60 chars): 44px default, reduce to 32px if >50 chars
#   - Subtitle (max 100 chars): 28px default, reduce to 22px if >80 chars
#   - Body (max 250 chars per box): 20px default, reduce to 16px if >200 chars
# - TEXT HEIGHT CALCULATION: height = ceil(chars / (width / (fontSize * 0.6))) * fontSize * lineHeight
# - Include "lineHeight" (1.2-1.5) for ALL text elements - denser content uses 1.2, sparse uses 1.4
# - ALWAYS verify: text_y + text_height + 25 < next_element_y for elements below

# Z-INDEX ORDERING (CRITICAL FOR LAYERING):
# - Each element MUST have a "zIndex" property (0-100)
# - Background shapes/decorations: zIndex 0-10
# - Card backgrounds: zIndex 10-20
# - Icons: zIndex 30-40
# - Text content: zIndex 50-70
# - Foreground accents: zIndex 80-100
# - Elements are rendered BOTTOM-TO-TOP (lower zIndex = behind, higher = in front)

# COLOR RULES (CRITICAL FOR VISIBILITY):
# - Text on DARK backgrounds (#000000-#4B5563): MUST use LIGHT text (#FFFFFF, #E5E7EB, #F3F4F6).
# - Text on LIGHT backgrounds (#FFFFFF-#D1D5DB): MUST use DARK text (#111827, #374151, #1F2937).
# - Card backgrounds: Use muted versions of accent colors.
# - CHECK YOUR CONTRAST: Never place dark text on a dark card!
# - If you use a Dark Card Background, you MUST set the text fill to #FFFFFF.
# - FAILURE to do this results in invisible text.

# OUTPUT FORMAT:
# Canvas: 960x540 pixels. Generate a JSON object:
# {{
#   "title": "Slide title",
#   "elements": [
#     {{
#       "id": "text_1",
#       "type": "text",
#       "textType": "title|subtitle|body|bullet",
#       "content": "Your text",
#       "x": 50, "y": 40,
#       "width": 860, "height": 60,
#       "fontSize": 44,
#       "fontWeight": "bold",
#       "fill": "USE_PRIMARY_TEXT_COLOR_HERE",
#       "textAlign": "left|center|right",
#       "lineHeight": 1.3,
#       "zIndex": 60
#     }},
#     {{
#       "id": "shape_1",
#       "type": "shape",
#       "shapeType": "rectangle|circle|line",
#       "x": 50, "y": 150,
#       "width": 280, "height": 280,
#       "fill": "USE_ACCENT_OR_SECONDARY_COLOR",
#       "stroke": "USE_STROKE_COLOR",
#       "strokeWidth": 1,
#       "rx": 16,
#       "zIndex": 5
#     }},
#     {{
#       "id": "icon_1",
#       "type": "icon",
#       "iconName": "scale|shield-check|bar-chart-3|users",
#       "x": 80, "y": 180,
#       "size": 48,
#       "fill": "#4ade80",
#       "zIndex": 35
#     }},
#     {{
#       "id": "card_1",
#       "type": "card",
#       "x": 50, "y": 150,
#       "width": 280, "height": 280,
#       "backgroundColor": "#1f2937",
#       "borderRadius": 16,
#       "iconName": "leaf",
#       "title": "Card Title",
#       "description": "Card description text",
#       "zIndex": 15
#     }},
#     {{
#       "id": "step_1",
#       "type": "numbered_step",
#       "number": 1,
#       "x": 165, "y": 170,
#       "size": 80,
#       "circleColor": "#4ade80",
#       "label": "Step Label",
#       "zIndex": 40
#     }},
#     {{
#       "id": "step_2",
#       "type": "numbered_step",
#       "number": 2,
#       "x": 165, "y": 270,
#       "size": 80,
#       "circleColor": "#4ade80",
#       "label": "Step 2 Label",
#       "zIndex": 40
#     }}
#   ],
#   "backgroundColor": "#0f172a",
#   "speaker_notes": "Key talking points"
# }}

# HIERARCHY & GROUPING (CRITICAL):
# - Use the "children" array to group related elements.
# - IMPORTANT: Elements inside "children" use COORDINATES RELATIVE TO THEIR PARENT (x=0, y=0 is the top-left of the parent).
# - Use "type": "container" for invisible grouping or "type": "card" for visible grouping.
#
# EXAMPLE SCHEMA:
# {{
#   "elements": [
#     {{
#       "id": "main_card",
#       "type": "card",
#       "x": 50, "y": 100, "width": 400, "height": 300,
#       "children": [
#          {{ "type": "text", "content": "I am inside because I am a child!", "x": 20, "y": 20 }}
#       ]
#     }}
#   ]
# }}

# DESIGN TIPS:
# - For comparison slides: Use 3 cards side-by-side
# - Group related text/icons into a "card" or "container" so they move together.
# - Use relative coordinates for children to ensure they stay inside the box even if the box moves.
# - For lists, create a container for each item containing the bullet and text.
# - For process slides: Use numbered_step elements
# - For feature lists: Use cards with icons
# - Ensure NO top-level elements overlap.
# - Output ONLY valid JSON with no markdown formatting."""

#     # Previous slides context for continuity
#     prev_context = ""
#     if request.previous_slides:
#         prev_summaries = [f"Slide {i+1}: {s.get('title', 'Unknown')} - {s.get('content_summary', '')[:100]}" 
#                          for i, s in enumerate(request.previous_slides[-3:])]  # Last 3 slides
#         prev_context = f"\n\nPREVIOUS SLIDES FOR CONTEXT:\n" + "\n".join(prev_summaries)

#     user_prompt = f"""Design slide {request.slide_index + 1} of {request.total_slides}.

# PRESENTATION: {request.presentation_goal}
# TYPE: {request.presentation_type}

# SLIDE INFO:
# - Title: {request.slide_info.get('title', 'Untitled')}
# - Content: {request.slide_info.get('content_hint', '')}
# - Suggested Layout: {request.slide_info.get('layout', 'title_content')}
# {prev_context}

# {f"CONTEXT FROM USER'S DOCUMENTS:{chr(10)}{vault_context}" if vault_context else ""}

# {f"SPECIAL INSTRUCTIONS FROM USER (MUST FOLLOW):{chr(10)}{rrequest.special_instructions}" if request.special_instructions else ""}

# Generate the JSON object for this slide."""

#     try:
#         # Call LLM (synchronous, run in thread)
#         ai_response = await asyncio.to_thread(
#             llm_call,
#             system_prompt,
#             user_prompt,
#             None,  # uses configured model
#             request.user_id,
#             5000, # max_tokens
#             True # json_mode
#         )
        
#         # Parse JSON
#         json_str = ai_response.strip()
#         if json_str.startswith("```"):
#             json_str = json_str.split("```")[1]
#             if json_str.startswith("json"):
#                 json_str = json_str[4:]
#         json_str = json_str.strip()
        
#         slide_data = json.loads(json_str)
        
#         # Ensure all elements have unique IDs
#         for i, element in enumerate(slide_data.get("elements", [])):
#             if not element.get("id"):
#                 element["id"] = f"el_{int(time.time() * 1000)}_{i}"
        
#         logger.info(f"🎬 [PRESENTATION] Generated slide with {len(slide_data.get('elements', []))} elements")
#         logger.info(f"📄 [DEBUG] Context Slide JSON: {json.dumps(slide_data)}")
        
#         # Post-process to fix any overlapping elements
#         # Post-process: Sanitize (colors/heights) THEN fix overlaps
#         # slide_data = sanitize_slide_data(slide_data)
#         # slide_data = fix_overlapping_elements(slide_data)
        
#         return {"success": True, "slide": slide_data}
        
#     except Exception as e:
#         logger.error(f"🎬 [PRESENTATION] Slide generation failed: {e}")
#         return {"success": False, "error": str(e), "slide_index": request.slide_index}





@router.post("/presentation/enhance-slide")
async def enhance_slide(request: Request, body: EnhanceSlideRequest):
    """Edit a single slide.

    Single routing axis: ``body.deck_profile``. Profile wins over any stale
    ``template_id`` the UI may have attached.
      - ``general``   → legacy enhancement (LLM redesigns elements freely).
      - ``corporate`` → template-based slot enhancement (positions locked).
    """
    _profile = (getattr(body, 'deck_profile', None) or 'corporate').lower()
    logger.info(f"✨ [PRESENTATION] Enhancing slide: {body.instruction[:50]}... (profile={_profile}, skip_vault={body.skip_vault})")

    user_id = get_secure_user_id(request)

    if _profile in ('general', 'general_with_images'):
        body.template_id = None
        logger.info("✨ [PRESENTATION] deck_profile=general → legacy enhancement")
        return await enhance_slide_legacy(body, user_id)

    # Corporate. UI must supply template_id (matched at generation time and
    # carried with the slide). Falls back to legacy if it's somehow missing.
    if body.template_id:
        return await enhance_slide_with_template(body, user_id)
    logger.warning("✨ [PRESENTATION] corporate edit with no template_id — falling back to legacy")
    return await enhance_slide_legacy(body, user_id)


async def enhance_slide_with_template(body: EnhanceSlideRequest, user_id: str):
    """
    Template-based slide enhancement.
    AI only modifies slot CONTENT (text, iconName, imageDescription).
    Positions remain fixed from template definition.
    """
    from slide_templates import SLIDE_TEMPLATES, build_elements_from_template, apply_style_to_template, get_slot_prompt_format, get_example_json_for_template
    
    template_id = body.template_id
    template = SLIDE_TEMPLATES.get(template_id)
    
    if not template:
        logger.warning(f"✨ [PRESENTATION] Template '{template_id}' not found, falling back to legacy")
        return await enhance_slide_legacy(body, user_id)
    
    # Vault chunks now fetched agentically by the LLM via personal_data_tool
    # inside run_Enterprise_or_Personal_tool below — no pre-fetch.
    # For Edit All (is_update_all=False): respect skip_vault — grammar/formatting edits don't need vault
    # For Update All (is_update_all=True): always enable the tool
    vault_context = ""
    _should_fetch_vault = (body.is_update_all or not body.skip_vault) and bool(body.folder_ids)
    _enhance_use_personal = bool(_should_fetch_vault)
    if not _enhance_use_personal and body.skip_vault and not body.is_update_all:
        logger.info(f"✨ [PRESENTATION] Skipping vault tool (skip_vault={body.skip_vault}, is_update_all={body.is_update_all})")
    
    # Get structured data for charts (Excel, JSON, CSV, SaaS records)
    # Skip structured data for Edit All when vault is skipped (grammar/formatting edits)
    structured_data_context = ""
    if _should_fetch_vault:
        edit_slide_info = {
            "title": body.slide_content.get("title", "") if isinstance(body.slide_content, dict) else "",
            "content_hint": body.instruction,
        }
        structured_data_context = await _fetch_structured_schema_context(
            user_id, folder_ids=body.folder_ids, log_prefix="PRESENTATION_TEMPLATE",
            slide_info=edit_slide_info,
            user_query=body.presentation_goal or body.instruction,
        )
    
    # Extract current slot content from existing slide
    # Map element IDs to template slot names (e.g., "slot_title_123_0" -> "title")
    current_slots = {}
    original_id_by_slot = {}  # slot_name → original element ID (for ID preservation after rebuild)
    template_slot_names = list(template.get("slots", {}).keys())
    
    for element in body.slide_content.get("elements", []):
        element_id = element.get("slotId") or element.get("id", "")
        
        # Extract slot name from element ID (format: "slot_{name}_{timestamp}_{idx}")
        slot_name = None
        if element_id.startswith("slot_"):
            # Parse: slot_title_123_0 -> title, slot_left_icon_123_0 -> left_icon
            parts = element_id.split("_")
            # Try to find matching template slot name
            for tpl_slot in template_slot_names:
                tpl_parts = tpl_slot.split("_")
                # Check if element ID contains this slot name after "slot_"
                if "_".join(parts[1:1+len(tpl_parts)]) == tpl_slot:
                    slot_name = tpl_slot
                    break
        
        if not slot_name:
            slot_name = element_id  # Fallback to full ID
        
        # Track original element ID for later restoration (preserves UI image mapping)
        if slot_name in template_slot_names:
            original_id_by_slot[slot_name] = element.get("id", "")
        
        if element.get("type") == "text":
            current_slots[slot_name] = {
                "content": element.get("content", ""),
                "type": "text"
            }
        elif element.get("type") == "icon":
            current_slots[slot_name] = {
                "iconName": element.get("iconName", "circle"),
                "type": "icon"
            }
        elif element.get("type") == "card":
            current_slots[slot_name] = {
                "iconName": element.get("iconName", "circle"),
                "title": element.get("title", ""),
                "description": element.get("description", ""),
                "type": "card"
            }
        elif element.get("type") == "chart":
            current_slots[slot_name] = {
                "chartConfig": element.get("chartConfig", {}),
                "type": "chart"
            }
        elif element.get("type") == "image_placeholder" and element.get("imageType") == "background":
            # Background image — track under special key, not as a template slot
            current_slots["background_image"] = {
                "imageDescription": element.get("imageDescription", ""),
                "type": "background_image"
            }
        elif element.get("type") == "image_placeholder":
            current_slots[slot_name] = {
                "imageDescription": element.get("imageDescription", ""),
                "type": "image"
            }
        elif element.get("type") == "svg_diagram":
            # SVG diagram — preserve full payload so build_elements_from_template (or the
            # post-build re-injection below) can keep it intact through Edit All.
            current_slots[slot_name] = {
                "svgContent": element.get("svgContent", ""),
                "fillColor": element.get("fillColor", ""),
                "prompt": element.get("prompt", ""),
                "diagramKind": element.get("diagramKind", ""),
                "diagramTitle": element.get("diagramTitle", ""),
                "type": "svg_diagram",
            }
    
    # Get expected slots from template (fix: use template_id, not template object)
    slot_format = get_slot_prompt_format(template_id)
    example_json = get_example_json_for_template(template_id)
    
    # Build mode-aware rules based on is_update_all
    if body.is_update_all:
        # UPDATE ALL mode: vault-driven, compare-and-update
        mode_rules = """RULES (UPDATE ALL MODE — vault data refresh):
1. Return ALL slots with content - never omit any slot
2. COMPARE the current slide content against the vault/context data provided below
3. Update ONLY the parts where the data has changed — keep everything else VERBATIM
4. If a slot's content is still accurate per the vault data, return it UNCHANGED
5. Update 'imageDescription' of image_placeholder elements ONLY if the content change makes the current image irrelevant
6. You may restructure content if the new data tells a significantly different story
7. JSON only, no markdown"""
    else:
        # EDIT ALL mode: user-instruction-only, strict preservation
        mode_rules = """RULES (EDIT ALL MODE — follow user instruction strictly):
1. Return ALL slots with content - never omit any slot
2. ONLY modify what the instruction EXPLICITLY asks for (e.g. grammar fixes, translation, formatting)
3. For slots NOT affected by the instruction, return their content EXACTLY AS-IS — do NOT rephrase, rewrite, improve, or expand
4. Do NOT change imageDescription fields unless the instruction specifically asks to update images
5. Do NOT add new information, elaborate, or enrich content beyond what the instruction requests
6. Preserve the exact wording, tone, and length of unaffected content
7. NEVER modify svg_diagram slots (svgContent / fillColor / prompt / diagramKind / diagramTitle) unless the user instruction explicitly mentions diagrams, charts, or visuals — return them EXACTLY AS-IS, byte-for-byte
8. JSON only, no markdown"""
    
    # Storyboard slice — same deck-wide design language used by initial
    # generation. Threading it into edits keeps the edited slide visually
    # coherent with the rest of the deck (palette / typography / per-slide
    # intent). No-op when the client didn't supply deck_plan (older sessions).
    from services.storyboard import render_for_prompt as _render_storyboard_for_prompt
    _slide_idx_for_sb = body.slide_content.get("slide_index") or body.slide_content.get("order", 1) - 1 if isinstance(body.slide_content, dict) else 0
    try:
        _slide_idx_for_sb = int(_slide_idx_for_sb)
    except (TypeError, ValueError):
        _slide_idx_for_sb = 0
    _sb_block = _render_storyboard_for_prompt(getattr(body, "deck_plan", None), _slide_idx_for_sb)
    _sb_section = (
        f"\n\nDECK STORYBOARD (LOCKED — every slide shares this design):\n{_sb_block}\n"
        if _sb_block else ""
    )

    system_prompt = f"""Modify template slot content. Layout: {template.get('name')}.
{_sb_section}
{slot_format}

OUTPUT FORMAT: {example_json}

{mode_rules}

BACKGROUND IMAGE: If the slide has a background image, you will see "background_image" in current slots with its imageDescription.
To update it (e.g., when content changes significantly), include "background_image": {{"imageDescription": "new description matching updated content"}} in your response.
To keep it unchanged, simply omit "background_image" from your response."""

    # Build goal context section
    goal_section = ""
    if body.presentation_goal:
        goal_section = f"""OVERALL PRESENTATION GOAL (for context only):
{body.presentation_goal}

NOTE: The above is the overall presentation goal. Your current task is to edit THIS SPECIFIC SLIDE only based on the instruction below.

"""

    # Build vault tool nudge based on mode (replaces the old vault_context block)
    vault_section = ""
    if _enhance_use_personal:
        if body.is_update_all:
            vault_section = (
                f"\n\nDATA TOOL: `personal_data_tool` is available "
                f"(scoped to {len(body.folder_ids)} folder(s)). Call it with a focused "
                f"query for THIS slide's topic, fetch the LATEST data, then compare "
                f"against the current content and update ONLY parts that differ or are "
                f"outdated. Keep everything else verbatim. Cite vault facts with "
                f"[vault:<doc_id>]."
            )
        else:
            vault_section = (
                f"\n\nDATA TOOL: `personal_data_tool` is available "
                f"(scoped to {len(body.folder_ids)} folder(s)). Call it for relevant "
                f"facts to support the edit. Cite vault facts with [vault:<doc_id>]."
            )

    user_prompt = f"""{goal_section}SLIDE TITLE: {body.slide_content.get('title', 'Untitled')}
TEMPLATE: {template_id}

CURRENT SLIDE (all elements):
{json.dumps(body.slide_content, indent=2)}

INSTRUCTION: {body.instruction}
{vault_section}
{structured_data_context}

Return JSON with slot content updates only (not full elements):"""

    try:
        if _enhance_use_personal:
            from services.enterprise_tools import run_Enterprise_or_Personal_tool
            ai_response = await run_Enterprise_or_Personal_tool(
                prompt=user_prompt,
                system=_grounded_sys(system_prompt) + "\n\n" + COMPUTE_FACT_ROUTING_RULE,
                user_id=user_id,
                tier="large",
                temperature=0.2,
                max_tokens=8000,
                filter_tools="auto",
                use_personal_data=True,
                selected_folder_ids=body.folder_ids,
                max_results_cap=3,  # enhance-slide: max 3 chunks per call
                expose_enterprise_tools=False,
                personal_tool_expand_subqueries=False,
                extra_tools=[build_compute_fact_tool_schema()],
                extra_tool_dispatch=make_compute_fact_dispatcher(
                    user_id=user_id, folder_ids=body.folder_ids,
                    log_prefix="PRESENTATION-ENHANCE-FACT",
                ),
            )
        else:
            ai_response = await asyncio.to_thread(
                llm_call,
                system_prompt=_grounded_sys(system_prompt),
                user_prompt=user_prompt,
                model=None,
                user_id=user_id,
                max_tokens=8000,
                temperature=0.2,
                top_p=0.95,
                tier="large",
            )
        
        logger.info(f"✨ [presentation] Template AI response received: {repr(ai_response)}")
        
        # Parse JSON
        json_str = extract_json_from_response(ai_response)
        
        updated_slots = json.loads(json_str)
        
        # Handle if AI wrapped in "slots" key
        if "slots" in updated_slots:
            updated_slots = updated_slots["slots"]
        
        # Extract non-slot fields (backgroundColor, background_image, speaker_notes) before merging
        ai_background_color = updated_slots.pop("backgroundColor", None)
        ai_background_image = updated_slots.pop("background_image", None)
        ai_speaker_notes = updated_slots.pop("speaker_notes", None)
        
        # MERGE: Fill missing slots from existing slide content so edits preserve unchanged elements
        # current_slots was extracted above from body.slide_content — use it as the baseline
        merged_slots = dict(current_slots)  # Start with existing content
        for slot_name, slot_value in updated_slots.items():
            if slot_value:  # Only override with non-empty AI content
                merged_slots[slot_name] = slot_value
        
        logger.info(f"✨ [PRESENTATION] Slot merge: {len(current_slots)} existing + {len(updated_slots)} AI updates → {len(merged_slots)} merged")
        
        # Build final elements from template + merged content + style
        elements = build_elements_from_template(template, merged_slots, body.style or {})
        
        # Restore original element IDs so UI-side image restoration (by ID matching) works
        # build_elements_from_template generates fresh IDs with new timestamps, breaking imageMap restoration
        for el in elements:
            el_id = el.get("id", "")
            if el_id.startswith("slot_"):
                parts = el_id.split("_")
                for sn, orig_id in original_id_by_slot.items():
                    sp = sn.split("_")
                    if "_".join(parts[1:1+len(sp)]) == sn:
                        el["id"] = orig_id
                        break
        
        # Get styled background — AI override takes priority
        styled = apply_style_to_template(template, body.style or {})
        if ai_background_color:
            background_color = ai_background_color
            logger.info(f"✨ [PRESENTATION] Using AI-specified backgroundColor: {ai_background_color}")
        else:
            background_color = styled.get("backgroundColor", body.style.get("slideBackground", "#ffffff") if body.style else "#ffffff")
        
        enhanced_slide = {
            "template": template_id,
            "title": body.slide_content.get("title", ""),
            "elements": elements,
            "backgroundColor": background_color,
            "speaker_notes": ai_speaker_notes if ai_speaker_notes is not None else body.slide_content.get("speaker_notes", "")
        }
        
        # Inject background image if AI provided one
        if ai_background_image:
            if isinstance(ai_background_image, str):
                ai_background_image = {"imageDescription": ai_background_image}
            if ai_background_image.get("imageDescription"):
                bg_element = {
                    "id": f"bg_img_{int(time.time() * 1000)}",
                    "type": "image_placeholder",
                    "imageType": "background",
                    "imageDescription": ai_background_image["imageDescription"],
                    "x": 0,
                    "y": 0,
                    "width": 960,
                    "height": 540,
                    "zIndex": 0,
                    "opacity": ai_background_image.get("opacity", 0.3),
                    "generationQuality": getattr(body, "generation_quality", "premium"),
                }
                enhanced_slide["elements"].insert(0, bg_element)
        else:
            # Preserve original background image from the slide if AI didn't provide a new one
            # build_elements_from_template only rebuilds template slots, so bg images are lost
            for orig_el in body.slide_content.get("elements", []):
                if orig_el.get("type") == "image_placeholder" and orig_el.get("imageType") == "background":
                    enhanced_slide["elements"].insert(0, orig_el)
                    break

        # Preserve any svg_diagram elements that build_elements_from_template did not
        # re-emit (templates may not declare an svg_diagram slot, and the LLM may omit it).
        # Match by element id so we don't double-insert when the template already rebuilt it.
        rebuilt_ids = {el.get("id") for el in enhanced_slide.get("elements", []) if el.get("id")}
        rebuilt_has_svg_diagram = any(
            el.get("type") == "svg_diagram" for el in enhanced_slide.get("elements", [])
        )
        for orig_el in body.slide_content.get("elements", []):
            if orig_el.get("type") != "svg_diagram":
                continue
            orig_id = orig_el.get("id")
            if orig_id and orig_id in rebuilt_ids:
                continue
            if rebuilt_has_svg_diagram:
                # Template did rebuild *some* svg_diagram (different id); skip to avoid duplicates.
                continue
            enhanced_slide["elements"].append(orig_el)
            logger.info(f"✨ [PRESENTATION] Preserved svg_diagram element {orig_id} through AI edit")
        
        logger.info(f"✨ [PRESENTATION] Template slide enhanced with {len(elements)} elements")

        # Resolve _data_request placeholders against the user's structured files.
        if DATA_FILLER_AVAILABLE:
            try:
                fill_report = await fill_data_requests(
                    enhanced_slide,
                    user_id=user_id,
                    folder_ids=getattr(body, "folder_ids", None),
                    log_prefix="PRESENTATION-ENHANCE",
                )
                if fill_report.get("data_warnings"):
                    enhanced_slide["_data_warnings"] = fill_report["data_warnings"]
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"📊 [PRESENTATION-ENHANCE] data filler raised: {exc}")

        # AI-powered chart fix: detect malformed chartConfigs and ask AI to regenerate
        enhanced_slide = await _fix_malformed_charts_with_ai(enhanced_slide, user_id)
        
        # Fix numbered_step sequential numbering
        _fix_numbered_step_numbers(enhanced_slide.get("elements", []))
        # Normalize icon fields (AI sometimes sends 'icon' instead of 'iconName')
        _normalize_icon_fields(enhanced_slide.get("elements", []))
        # Fix overlapping elements (deterministic safety net)
        # enhanced_slide = fix_overlapping_elements(enhanced_slide)  # DISABLED: testing LLM-based layout fixer
        # Compact title position: pull layout up if title drifted too far down
        # enhanced_slide = _compact_title_position(enhanced_slide)  # DISABLED: testing LLM-based layout fixer
        # Post-process: Shrink font sizes to fit content within fixed-size template slots
        enhanced_slide = fit_content_to_slots(enhanced_slide)
        # Validate element positions: clamp out-of-bounds, fix invalid dimensions
        validate_element_positions(enhanced_slide.get("elements", []), PRESENTATION_CANVAS)

        # critique_recommended=True for every edit (template + legacy alike) —
        # see contract note in generate_slide_with_template.
        return {"success": True, "enhanced_slide": enhanced_slide, "critique_recommended": True}
        
    except json.JSONDecodeError as e:
        logger.error(f"✨ [PRESENTATION] JSON parse error in template enhancement: {e}")
        # Fall back to legacy enhancement
        return await enhance_slide_legacy(body, user_id)
    except HTTPException:
        raise  # Propagate 402 insufficient_credits and other HTTP errors as-is
    except Exception as e:
        logger.error(f"✨ [PRESENTATION] Template enhancement failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def enhance_slide_legacy(body: EnhanceSlideRequest, user_id: str):
    """Legacy slide enhancement — delegates to unified orchestrator.

    Threads ``deck_plan`` so the edit stays coherent with the deck's
    storyboard (same design language as initial generation). The
    orchestrator forwards the storyboard slice + free-form authoring
    guidance into the edit prompt.
    """
    result = await _orchestrator_enhance_slide_legacy(
        page_content=body.slide_content,
        instruction=body.instruction,
        user_id=user_id,
        canvas=PRESENTATION_CANVAS,
        style=body.style,
        folder_ids=body.folder_ids,
        skip_vault=body.skip_vault,
        goal=body.presentation_goal,
        content_type=body.presentation_type,
        icon_set=body.icon_set or "lucide",
        deck_plan=getattr(body, "deck_plan", None),
    )
    if result.get("success"):
        # critique_recommended mirrors the generation contract: every edited
        # slide (template or free-form) gets a vision-critique pass after
        # fabric re-renders, so subtle post-edit defects are caught before
        # the user sees them.
        return {
            "success": True,
            "enhanced_slide": result.get("enhanced_slide"),
            "critique_recommended": True,
        }
    return result


# ==================== Legacy Classification (Fallback) ====================

async def _legacy_classify(body, user_id: str) -> tuple:
    """
    Fallback classification when parallel classifier is unavailable.
    Returns: (intent, ai_message, chart_type, chart_query, create_topic)
    
    Note: supplementary_sources selection has been removed. SaaS data is now
    pre-embedded in Milvus and retrieved via semantic search.
    """
    system_prompt = """You are an intent classifier for a presentation editor AI assistant.
Classify the user's instruction into EXACTLY ONE category:
1. GREETING - Simple greetings, acknowledgments
2. HELP - Questions about capabilities
3. CREATE_NEW - Create a NEW slide
4. SIMPLE_EDIT - Layout/color/formatting changes (no vault needed)
5. DATA_ADDITION - Requires new information from vault
6. CHART_REQUEST - Visual data representation request
7. UPDATE_SLIDE - Refresh/update existing content

Output format (JSON only):
{"intent": "...", "ai_message": "brief message", "create_topic": null, "chart_type": null, "chart_query": null}"""

    user_prompt = f"""Classify: "{body.instruction}"
Slide elements: {[e.get('type', 'unknown') for e in body.slide_content.get('elements', [])]}"""

    try:
        ai_response = await asyncio.to_thread(
            llm_call,
            system_prompt=system_prompt, user_prompt=user_prompt,
            model=None, user_id=user_id, max_tokens=5000, temperature=0.2, top_p=0.95, json_mode=True,
            tier="large",
        )
        
        json_str = extract_json_from_response(ai_response)
        classification = json.loads(json_str)
        
        return (
            classification.get("intent", "simple_edit"),
            classification.get("ai_message", ""),
            classification.get("chart_type"),
            classification.get("chart_query") or body.instruction,
            classification.get("create_topic", "")
        )
    except Exception as e:
        logger.error(f"🎯 [LEGACY] Classification failed: {e}")
        return ("simple_edit", "", None, body.instruction, "")


# ==================== AI Orchestrator Endpoint ====================

async def _generate_slide_for_orchestrator(instruction, topic, goal, content_type, style, user_id):
    """Bridge: generate new slide for the single-page orchestrator."""
    from slide_templates import auto_match_template
    matched_template = auto_match_template(topic or "New Slide", instruction, 1, 10)
    slide_req = GenerateSlideRequest(
        slide_info={"title": topic or "New Slide", "content_hint": instruction, "layout": "title_content"},
        slide_index=1, total_slides=10,
        presentation_goal=goal or f"Create a slide about {topic}",
        presentation_type=content_type, style=style,
        template_id=matched_template,
    )
    result = await generate_slide_with_template(slide_req, user_id)
    return result

async def _enhance_slide_with_template_for_orchestrator(
    page_content, instruction, user_id, canvas, style, folder_ids,
    skip_vault, goal, content_type, template_id, icon_set,
    is_update_all=False,
):
    """Bridge: template-based enhancement for orchestrator."""
    enhance_req = EnhanceSlideRequest(
        slide_id=page_content.get('id', ''), slide_content=page_content,
        instruction=instruction, style=style, folder_ids=folder_ids,
        skip_vault=skip_vault, template_id=template_id,
        presentation_goal=goal, presentation_type=content_type, icon_set=icon_set,
        is_update_all=is_update_all,
    )
    return await enhance_slide_with_template(enhance_req, user_id)

@router.post("/presentation/orchestrate")
async def orchestrate_request(request: Request, body: OrchestrateRequest):
    """AI Orchestrator — delegates to unified edit_orchestrator.

    Profile-driven: general → legacy free-form generator + legacy enhance
    (storyboard injected via deck_plan); corporate → template-matched
    generator + template-slot enhance.
    """
    user_id = get_secure_user_id(request)

    _profile = (getattr(body, 'deck_profile', None) or 'corporate').lower()
    _is_general = _profile in ('general', 'general_with_images')
    _effective_template_id = None if _is_general else body.template_id

    async def _gen_slide_fn(instruction, topic, goal, content_type, style, _user_id):
        if _is_general:
            slide_req = GenerateSlideRequest(
                slide_info={"title": topic or "New Slide", "content_hint": instruction, "layout": "title_content"},
                slide_index=1, total_slides=10,
                presentation_goal=goal or f"Create a slide about {topic}",
                presentation_type=content_type, style=style,
                template_id=None,
                deck_profile='general',
            )
            return await generate_slide_legacy(slide_req, _user_id)
        return await _generate_slide_for_orchestrator(instruction, topic, goal, content_type, style, _user_id)

    return await orchestrate_edit(
        instruction=body.instruction,
        page_content=body.slide_content,
        page_id=body.slide_id,
        user_id=user_id,
        canvas=PRESENTATION_CANVAS,
        edit_mode=body.edit_mode,
        selected_elements=body.selected_elements,
        style=body.style,
        folder_ids=body.folder_ids,
        goal=body.presentation_goal,
        content_type=body.presentation_type,
        template_id=_effective_template_id,
        icon_set=body.icon_set,
        user_edit_scope=body.user_edit_scope,
        generate_page_fn=_gen_slide_fn,
        enhance_page_with_template_fn=None if _is_general else _enhance_slide_with_template_for_orchestrator,
        pages_summary=body.slides_summary,
        deck_plan=getattr(body, 'deck_plan', None),
    )


@router.post("/presentation/orchestrate-stream")
async def orchestrate_request_stream(request: Request, body: OrchestrateRequest):
    """Streaming variant of orchestrate — yields SSE events.

    Profile-driven: general → legacy free-form generator; corporate →
    template path.
    """
    user_id = get_secure_user_id(request)

    _profile = (getattr(body, 'deck_profile', None) or 'corporate').lower()
    _is_general = _profile in ('general', 'general_with_images')
    _effective_template_id = None if _is_general else body.template_id

    async def _gen_slide_fn(instruction, topic, goal, content_type, style, _user_id):
        if _is_general:
            slide_req = GenerateSlideRequest(
                slide_info={"title": topic or "New Slide", "content_hint": instruction, "layout": "title_content"},
                slide_index=1, total_slides=10,
                presentation_goal=goal or f"Create a slide about {topic}",
                presentation_type=content_type, style=style,
                template_id=None,
                deck_profile='general',
            )
            return await generate_slide_legacy(slide_req, _user_id)
        return await _generate_slide_for_orchestrator(instruction, topic, goal, content_type, style, _user_id)

    async def event_generator():
        async for event in orchestrate_edit_streaming(
            instruction=body.instruction,
            page_content=body.slide_content,
            page_id=body.slide_id,
            user_id=user_id,
            canvas=PRESENTATION_CANVAS,
            edit_mode=body.edit_mode,
            selected_elements=body.selected_elements,
            style=body.style,
            folder_ids=body.folder_ids,
            goal=body.presentation_goal,
            content_type=body.presentation_type,
            template_id=_effective_template_id,
            icon_set=body.icon_set,
            user_edit_scope=body.user_edit_scope,
            generate_page_fn=_gen_slide_fn,
            enhance_page_with_template_fn=None if _is_general else _enhance_slide_with_template_for_orchestrator,
            fast_path=body.fast_path,
            pages_summary=body.slides_summary,
            deck_plan=getattr(body, 'deck_plan', None),
        ):
            yield event

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# _extract_slide_full_text and _is_global_instruction — now in services/edit_orchestrator.py


# ==================== AI Orchestrate-All Endpoint (Smart Multi-Slide) ====================

async def _generate_slide_for_orchestrator_all(instruction, topic, goal, content_type, style, user_id):
    """Bridge: generate new slide for the all-pages orchestrator."""
    from slide_templates import auto_match_template
    matched_template = auto_match_template(topic or "New Slide", instruction, 1, 10)
    slide_req = GenerateSlideRequest(
        slide_info={"title": topic or "New Slide", "content_hint": instruction, "layout": "title_content"},
        slide_index=1, total_slides=10,
        presentation_goal=goal or f"Create a slide about {topic}",
        presentation_type=content_type, style=style,
        template_id=matched_template,
    )
    result = await generate_slide_with_template(slide_req, user_id)
    return result

@router.post("/presentation/orchestrate-all")
async def orchestrate_all_slides(request: Request, body: OrchestrateAllRequest):
    """Smart All-Slides Orchestrator — delegates to unified edit_orchestrator.

    Used by Edit-All / Update-All. Profile-driven: general → every new
    slide goes through legacy free-form generator + legacy enhance;
    corporate → template-matched generator + template-slot enhance.
    """
    user_id = get_secure_user_id(request)

    _profile = (getattr(body, 'deck_profile', None) or 'corporate').lower()
    _is_general = _profile in ('general', 'general_with_images')
    if _is_general:
        # Strip any stale template ids on the carried slides so re-matching
        # doesn't accidentally pull a template into a general edit.
        for _s in (body.full_slides or []):
            if isinstance(_s, dict) and 'template' in _s:
                _s['template'] = None

    async def _gen_slide_inner(instruction, topic, goal, content_type, style, _user_id):
        from slide_templates import auto_match_template
        matched_template = None if _is_general else auto_match_template(
            topic or "New Slide", instruction, 1, 10, deck_profile=_profile,
        )
        slide_req = GenerateSlideRequest(
            slide_info={"title": topic or "New Slide", "content_hint": instruction, "layout": "title_content"},
            slide_index=1, total_slides=10,
            presentation_goal=goal or f"Create a slide about {topic}",
            presentation_type=content_type, style=style,
            template_id=matched_template,
            deck_profile=_profile,
        )
        if _is_general:
            return await generate_slide_legacy(slide_req, _user_id)
        return await generate_slide_with_template(slide_req, _user_id)

    return await _orchestrator_orchestrate_all_edits(
        instruction=body.instruction,
        full_pages=body.full_slides,
        pages_summary=body.slides_summary,
        current_page_index=body.current_slide_index,
        user_id=user_id,
        canvas=PRESENTATION_CANVAS,
        style=body.style,
        folder_ids=body.folder_ids,
        goal=body.presentation_goal,
        content_type=body.presentation_type,
        icon_set=body.icon_set,
        generate_page_fn=_gen_slide_inner,
        is_update_all=body.is_update_all,
        enhance_page_with_template_fn=None if _is_general else _enhance_slide_with_template_for_orchestrator,
        deck_plan=getattr(body, 'deck_plan', None),
    )


@router.post("/presentation/orchestrate-all-stream")
async def orchestrate_all_slides_stream(request: Request, body: OrchestrateAllRequest):
    """Streaming variant of orchestrate-all — yields SSE events per slide."""
    user_id = get_secure_user_id(request)

    from slide_templates import auto_match_template as _slide_auto_match

    _profile = (getattr(body, 'deck_profile', None) or 'corporate').lower()
    _is_general = _profile in ('general', 'general_with_images')
    if _is_general:
        # Clear any stale template ids on the carried slides so re-matching
        # doesn't accidentally pull a template into a general edit.
        for _s in (body.full_slides or []):
            if isinstance(_s, dict) and 'template' in _s:
                _s['template'] = None

    async def _gen_slide_inner_stream(instruction, topic, goal, content_type, style, _user_id):
        matched_template = None if _is_general else _slide_auto_match(topic or "New Slide", instruction, 1, 10, deck_profile=_profile)
        slide_req = GenerateSlideRequest(
            slide_info={"title": topic or "New Slide", "content_hint": instruction, "layout": "title_content"},
            slide_index=1, total_slides=10,
            presentation_goal=goal or f"Create a slide about {topic}",
            presentation_type=content_type, style=style,
            template_id=matched_template,
            deck_profile=_profile,
        )
        if _is_general:
            return await generate_slide_legacy(slide_req, _user_id)
        return await generate_slide_with_template(slide_req, _user_id)

    async def event_generator():
        async for event in _orchestrator_orchestrate_all_edits_streaming(
            instruction=body.instruction,
            full_pages=body.full_slides,
            pages_summary=body.slides_summary,
            current_page_index=body.current_slide_index,
            user_id=user_id,
            canvas=PRESENTATION_CANVAS,
            style=body.style,
            folder_ids=body.folder_ids,
            goal=body.presentation_goal,
            content_type=body.presentation_type,
            icon_set=body.icon_set,
            generate_page_fn=_gen_slide_inner_stream,
            is_update_all=body.is_update_all,
            enhance_page_with_template_fn=None if _is_general else _enhance_slide_with_template_for_orchestrator,
            outline_changed=body.outline_changed,
            auto_match_template_fn=(None if _is_general else (_slide_auto_match if body.outline_changed else None)),
            deck_plan=getattr(body, 'deck_plan', None),
        ):
            yield event

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ==================== Agentic Whole-Deck Editor (Claude-on-PowerPoint) ====================

def _build_deck_meta(body: "AgentEditRequest") -> Dict[str, Any]:
    return {
        "style": body.style or {},
        "header_footer": body.header_footer or {},
        "slide_numbers": body.slide_numbers or {},
        "goal": body.presentation_goal or "",
        "presentation_type": body.presentation_type,
    }


@router.post("/presentation/agent-edit-stream")
async def presentation_agent_edit_stream(request: Request, body: AgentEditRequest):
    """Agentic deck edit (SSE). Sends the whole deck + chat message; the LLM
    returns operations the frontend applies (edit/add/delete/reorder slides,
    style, header/footer, slide numbers)."""
    user_id = get_secure_user_id(request)
    user_email = getattr(request.state, "user_email", None)

    # OCR-first: pasted screenshots → text prepended to the instruction context.
    # Slide media (image_placeholder markers) is untouched — this is a separate field.
    from services.ocr_context import prepend_ocr_to_instruction
    instruction = await prepend_ocr_to_instruction(
        body.instruction, body.image_attachments, user_id=user_id, user_email=user_email,
    )

    async def event_generator():
        async for event in agent_edit_deck_loop_streaming(
            instruction=instruction,
            slides=body.slides,
            user_id=user_id,
            canvas=PRESENTATION_CANVAS,
            current_index=body.current_slide_index,
            deck_meta=_build_deck_meta(body),
            chat_history=body.chat_history,
            folder_ids=body.folder_ids,
            selected_element_ids=body.selected_element_ids,
        ):
            yield event

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/presentation/agent-edit")
async def presentation_agent_edit(request: Request, body: AgentEditRequest):
    """Non-streaming agentic deck edit. Returns {success, chat_message, operations}."""
    user_id = get_secure_user_id(request)
    return await agent_edit_deck(
        instruction=body.instruction,
        slides=body.slides,
        user_id=user_id,
        canvas=PRESENTATION_CANVAS,
        current_index=body.current_slide_index,
        deck_meta=_build_deck_meta(body),
        chat_history=body.chat_history,
        folder_ids=body.folder_ids,
    )


async def enhance_image_element_with_ai(
    element: Dict[str, Any],
    instruction: str,
    user_id: str,
    style: Optional[Dict[str, Any]] = None,
    vault_context: str = ""
) -> Dict[str, Any]:
    """AI-enhance an image element — delegates to orchestrator."""
    return await _orchestrator_enhance_image(
        element=element, instruction=instruction, user_id=user_id,
        style=style, vault_context=vault_context,
    )


async def enhance_single_element(
    element: Dict[str, Any],
    instruction: str,
    user_id: str,
    style: Optional[Dict[str, Any]] = None,
    folder_ids: Optional[List[str]] = None,
    skip_vault: bool = True,
    page_content: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """AI-enhance a single element — delegates to orchestrator with page context."""
    return await _orchestrator_enhance_single(element, instruction, user_id, PRESENTATION_CANVAS, style, folder_ids, skip_vault, page_content)


async def enhance_multiple_elements(
    elements: List[Dict[str, Any]],
    instruction: str,
    user_id: str,
    style: Optional[Dict[str, Any]] = None,
    folder_ids: Optional[List[str]] = None,
    skip_vault: bool = True,
    page_content: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """AI-enhance multiple elements — delegates to orchestrator with page context."""
    return await _orchestrator_enhance_multi(elements, instruction, user_id, PRESENTATION_CANVAS, style, folder_ids, skip_vault, page_content)


@router.post("/presentation/generate-chart-data")
async def generate_chart_data_endpoint(request: Request, body: ChartDataRequest):
    """Generate Chart.js config — delegates to orchestrator."""
    user_id = get_secure_user_id(request)
    return await _orchestrator_generate_chart(body.chart_type, body.query, user_id, body.folder_ids, body.page_context, body.source_context)


# ==================== Persistence Endpoints ====================

@router.post("/presentation/save")
async def save_presentation(http_request: Request, body: SavePresentationRequest):
    """
    Save presentation to MongoDB.
    
    SECURITY: Uses authenticated user_id from JWT token (via middleware).
    
    Args:
        http_request: FastAPI request (contains JWT auth)
        body: Presentation data to save
    """
    authenticated_user_id = get_secure_user_id(http_request)

    logger.info(f"💾 [PRESENTATION] Saving presentation: {body.title} | ID: {body.id if body.id else 'NEW'} for user: {authenticated_user_id}")

    # Personal-SA ownership stamp: presentations are personal-output
    # resources, owned by the user's Personal SA. Reject if the JWT lacks
    # personal_sa_id — the user must get their SAs provisioned (admin
    # panel "Fix Service Accounts").
    _personal_sa_id = getattr(http_request.state, "personal_sa_id", "") or ""
    _owner_org_id = getattr(http_request.state, "org_id", "") or ""
    if not _personal_sa_id:
        logger.warning(
            "[PRESENTATION] reject: personal_sa_id missing for user=%s org=%s",
            authenticated_user_id, _owner_org_id,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "code": "personal_sa_id_missing",
                "message": (
                    "Cannot save: your Personal Service Account is not provisioned. "
                    "Sign out + sign in to refresh, or contact your admin to run "
                    "'Fix Service Accounts' on your user record."
                ),
            },
        )

    db = get_mongo_db()
    if db is None:
        logger.error("❌ [PRESENTATION] Database connection unavailable during save")
        raise HTTPException(status_code=500, detail="Database not available")
    
    try:
        # Pydantic validation passed, now analyze payload
        slide_count = len(body.slides)
        total_elements = sum(len(s.get('elements', [])) for s in body.slides)
        
        logger.info(f"💾 [PRESENTATION] Payload Analysis: {slide_count} slides, {total_elements} total elements")
        
        if slide_count == 0:
            logger.warning(f"⚠️ [PRESENTATION] Saving presentation '{body.title}' with 0 slides!")

        collection = db["presentations"]
        
        # Prepare ID for S3 processing
        if body.id:
            presentation_id = body.id
            is_new = False
        else:
            presentation_id = f"pres_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
            is_new = True

        # Process thumbnail if provided (base64 -> S3)
        thumbnail_url = None
        if body.thumbnail:
            try:
                if body.thumbnail.startswith('data:image'):
                    thumbnail_url = image_processor.upload_base64_image(
                        body.thumbnail,
                        authenticated_user_id,  # Use authenticated user
                        "presentations",
                        f"{presentation_id}_thumbnail"
                    )
                    logger.info(f"🖼️ [PRESENTATION] Thumbnail uploaded to S3: {thumbnail_url}")
                elif body.thumbnail.startswith('http'):
                    thumbnail_url = body.thumbnail
            except Exception as thumb_err:
                logger.warning(f"⚠️ [PRESENTATION] Thumbnail processing failed: {thumb_err}")

        # Process images (Extract Base64 -> S3) - Use authenticated user
        updated_slides, active_keys = await image_processor.process_presentation_slides(
            body.slides,
            authenticated_user_id,  # Use authenticated user
            presentation_id
        )

        # Garbage Collect unused images - Use authenticated user
        image_processor.garbage_collect(authenticated_user_id, "presentations", presentation_id, active_keys)

        presentation_data = {
            "title": body.title,
            "goal": body.goal,
            "style": body.style,
            "type": body.presentation_type,
            "slides": updated_slides,
            "user_id": authenticated_user_id,  # SECURITY: Use authenticated user from JWT
            "team_id": body.team_id,
            # SA ownership: presentations live on the user's Personal SA so
            # they're deleted with the user (vs. work SA which is transferable).
            "owner_type": "service_account",
            "owner_id": _personal_sa_id,
            "org_id": _owner_org_id or None,
            "thumbnail": thumbnail_url,
            # Either spelling; the singular wins when both are sent.
            "folder_id": body.folder_id or (body.folder_ids[0] if body.folder_ids else None),
            "updated_at": datetime.utcnow()
        }
        
        if not is_new:
            # Update existing - SECURITY: Ensure user owns the presentation or has write access
            result = collection.update_one(
                {"_id": body.id, "user_id": authenticated_user_id},
                {"$set": presentation_data}
            )
            if result.matched_count == 0:
                # Check if user has shared write access via centralized permissions
                try:
                    from services.authorization_service import get_authorization_service
                    auth_service = get_authorization_service()
                    access_result = await auth_service.check_access(
                        user_id=authenticated_user_id,
                        resource_id=body.id,
                        resource_type="presentation",
                        required_permission="write"
                    )
                    if access_result.get("allowed"):
                        # User has write access - update without user_id filter but preserve original owner
                        existing = collection.find_one({"_id": body.id})
                        if existing:
                            presentation_data["user_id"] = existing["user_id"]  # Preserve original owner
                            result = collection.update_one(
                                {"_id": body.id},
                                {"$set": presentation_data}
                            )
                            if result.matched_count > 0:
                                logger.info(f"💾 [PRESENTATION] Updated shared presentation: {body.id} by collaborator {authenticated_user_id}")
                            else:
                                raise HTTPException(status_code=404, detail="Presentation not found")
                        else:
                            raise HTTPException(status_code=404, detail="Presentation not found")
                    else:
                        logger.warning(f"⚠️ [PRESENTATION] Update failed: Presentation {body.id} not found for user {authenticated_user_id}")
                        raise HTTPException(status_code=404, detail="Presentation not found or access denied")
                except HTTPException:
                    raise
                except Exception as auth_err:
                    logger.warning(f"⚠️ [PRESENTATION] Auth check failed during save: {auth_err}")
                    raise HTTPException(status_code=404, detail="Presentation not found or access denied")
            else:
                logger.info(f"💾 [PRESENTATION] Updated existing presentation: {body.id}")
        else:
            # Create new
            presentation_data["created_at"] = datetime.utcnow()
            presentation_data["_id"] = presentation_id
            result = collection.insert_one(presentation_data)
            logger.info(f"💾 [PRESENTATION] Created new presentation: {presentation_id}")
        
        # Return slides with presigned URLs so frontend can update its local state
        # This prevents re-uploading all images/icons on subsequent saves
        response_slides = copy.deepcopy(updated_slides)
        response_slides = image_processor.inject_presigned_urls_presentation(response_slides)
        
        return {"success": True, "id": presentation_id, "slides": response_slides}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💾 [PRESENTATION] Save failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/presentation/load/{presentation_id}")
async def load_presentation(presentation_id: str, request: Request):
    """
    Load presentation from MongoDB.
    
    SECURITY: Validates that the authenticated user owns the presentation or has shared access.
    
    Args:
        presentation_id: Presentation ID
        request: FastAPI request (contains JWT auth)
    """
    authenticated_user_id = get_secure_user_id(request)
    
    logger.info(f"📂 [PRESENTATION] Loading: {presentation_id} for authenticated user: {authenticated_user_id}")
    
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    
    try:
        collection = db["presentations"]
        shared_collection = db["shared_with_me"]
        
        # First, find the presentation
        presentation = collection.find_one({"_id": presentation_id})
        
        if not presentation:
            logger.warning(f"⚠️ [PRESENTATION] Load failed: Presentation {presentation_id} not found")
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        # SECURITY: Verify ownership or shared access
        presentation_owner = presentation.get("user_id")
        
        # Check if user owns the presentation
        is_owner = (presentation_owner == authenticated_user_id)
        
        # Check if presentation is shared with user and get permission level
        is_shared = False
        user_permission = None
        shared_entry = None
        
        if not is_owner:
            # Check legacy shared_with_me collection
            shared_entry = shared_collection.find_one({
                "user_id": authenticated_user_id,
                "source_id": presentation_id,
                "content_type": "presentation"
            })
            if shared_entry:
                is_shared = True
                user_permission = shared_entry.get("permission", "read")
            else:
                # Check authorization service for centralized permissions
                try:
                    from services.authorization_service import get_authorization_service
                    auth_service = get_authorization_service()
                    access_result = await auth_service.check_access(
                        user_id=authenticated_user_id,
                        resource_id=presentation_id,
                        resource_type="presentation",
                        required_permission="read"
                    )
                    if access_result.get("allowed"):
                        is_shared = True
                        user_permission = access_result.get("permission", "read")
                except Exception as auth_e:
                    logger.warning(f"⚠️ [PRESENTATION] Auth service check failed: {auth_e}")
        
        if not is_owner and not is_shared:
            logger.warning(f"🔒 Access denied: User {authenticated_user_id} tried to access presentation {presentation_id} owned by {presentation_owner}")
            raise HTTPException(
                status_code=403, 
                detail="Access denied. You don't have permission to view this presentation."
            )
        
        # Convert ObjectId to string if needed
        presentation["id"] = str(presentation.pop("_id"))
        
        # Check if document has any collaboration shares (to determine if collaboration should be enabled)
        is_shared_for_collaboration = False
        if is_owner:
            # Check if owner has shared with anyone for collaboration
            try:
                from services.authorization_service import get_authorization_service
                auth_service = get_authorization_service()
                perm_record = await auth_service.db.resource_permissions.find_one({
                    "resource_id": presentation_id,
                    "resource_type": "presentation"
                })
                if perm_record:
                    shared_with = perm_record.get("shared_with", [])
                    shared_with_teams = perm_record.get("shared_with_teams", [])
                    is_shared_for_collaboration = len(shared_with) > 0 or len(shared_with_teams) > 0
            except Exception as e:
                logger.warning(f"⚠️ [PRESENTATION] Could not check collaboration shares: {e}")
                # Also check legacy collection
                legacy_shares = list(shared_collection.find({
                    "source_id": presentation_id,
                    "content_type": "presentation"
                }).limit(1))
                is_shared_for_collaboration = len(legacy_shares) > 0
        else:
            # Non-owner accessing = document IS shared for collaboration
            is_shared_for_collaboration = True
        
        # Add sharing metadata for frontend collaboration access control
        presentation["sharing"] = {
            "is_shared_for_collaboration": is_shared_for_collaboration,
            "user_permission": "owner" if is_owner else user_permission,
            "is_owner": is_owner
        }
        
        # Inject Presigned URLs for secure viewing
        slide_count = 0
        if "slides" in presentation:
            slide_count = len(presentation["slides"])
            presentation["slides"] = image_processor.inject_presigned_urls_presentation(presentation["slides"])
        else:
            logger.warning(f"⚠️ [PRESENTATION] Loaded presentation {presentation_id} has NO 'slides' key")

        logger.info(f"📂 [PRESENTATION] Loaded successfully: {presentation_id} ({slide_count} slides, collab={is_shared_for_collaboration}, perm={presentation['sharing']['user_permission']})")
        return {"success": True, "presentation": presentation}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"📂 [PRESENTATION] Load CRITICAL failure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/presentation/list")
async def list_presentations(request: Request, team_id: str = None, all_workspaces: bool = False, skip: int = 0, limit: int = 20):
    """
    List user's presentations or team presentations, including those shared with them.
    
    SECURITY: Uses authenticated user_id from JWT token.
    """
    authenticated_user_id = get_secure_user_id(request)
    
    logger.info(f"📋 [PRESENTATION] Listing presentations for authenticated user: {authenticated_user_id}, team: {team_id}, all_workspaces: {all_workspaces}")
    
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    
    try:
        collection = db["presentations"]
        shared_collection = db["shared_with_me"]
        
        # Build query based on team context
        if all_workspaces:
            # User-level: all presentations across all workspaces
            match_query = {"user_id": authenticated_user_id}
        elif team_id:
            # Team workspace: show all team presentations for authenticated user
            match_query = {"team_id": team_id, "user_id": authenticated_user_id}
        else:
            # Personal workspace: show user's personal presentations (no team_id)
            match_query = {
                "user_id": authenticated_user_id,
                "$or": [
                    {"team_id": {"$exists": False}},
                    {"team_id": None}
                ]
            }
        
        # 1. Get User's Own Presentations (or team presentations)
        pipeline = [
            {"$match": match_query},
            {"$sort": {"updated_at": -1}},
            {"$skip": skip},
            {"$limit": limit},
            {"$project": {
                "title": 1, 
                "goal": 1, 
                "style": 1, 
                "created_at": 1, 
                "updated_at": 1, 
                "thumbnail": 1,
                "user_id": 1,
                "team_id": 1,
                # The shell opens a deck straight from this row and takes its
                # data store from folder_id. Leaving it out of the projection
                # meant every deck opened detached: the folder view came up
                # empty and a reopened deck had no documents to read, even when
                # the value was sitting in Mongo.
                "folder_id": 1,
                "slide_count": {"$size": {"$ifNull": ["$slides", []]}}
            }}
        ]
        
        own_presentations = list(collection.aggregate(pipeline))
        own_count = collection.count_documents(match_query)

        # 2. Get Shared Presentations (only for personal workspace)
        # Note: Pagination here is tricky if we want to mix them seamlessly.
        # For MVP, we append shared items to the start or end, or just fetch all shared (usually few).
        # Let's fetch all shared items for now.
        shared_presentations = []
        if not team_id or all_workspaces:
            # SECURITY: Get shared presentations for authenticated user
            # Method 1: Legacy shared_with_me collection
            shared_entries = list(shared_collection.find({
                "user_id": authenticated_user_id,
                "content_type": "presentation"
            }))
            
            shared_docs = []
            if shared_entries:
                shared_ids = [entry["source_id"] for entry in shared_entries]
                # Fetch details for these IDs
                shared_docs = list(collection.find(
                    {"_id": {"$in": shared_ids}},
                    {
                        "title": 1, "goal": 1, "style": 1, 
                        "created_at": 1, "updated_at": 1, "thumbnail": 1,
                        "slides": 1 # To count
                    }
                ))
            
            # Map back to add shared metadata
            doc_map = {str(doc["_id"]): doc for doc in shared_docs}
            
            for entry in shared_entries:
                sid = entry["source_id"]
                if sid in doc_map:
                    doc = doc_map[sid]
                    slides = doc.get("slides", [])
                    
                    # Generate presigned URL for thumbnail
                    thumbnail_url = doc.get("thumbnail")
                    if thumbnail_url and thumbnail_url.startswith("s3://"):
                        try:
                            thumbnail_url = image_processor.generate_presigned_url(thumbnail_url)
                        except Exception:
                            thumbnail_url = None

                    shared_presentations.append({
                        "id": str(doc["_id"]),
                        "title": doc.get("title", "Untitled"),
                        "goal": doc.get("goal"),
                        "style": doc.get("style"),
                        "slide_count": len(slides),
                        "created_at": doc.get("created_at"),
                        "updated_at": doc.get("updated_at"),
                        "thumbnail": thumbnail_url,
                        "isShared": True,
                        "sharedBy": entry.get("owner_id"),
                        "permission": entry.get("permission", "read")
                    })
            
            # Method 2: Also check authorization service for shared presentations
            try:
                from services.authorization_service import get_authorization_service
                auth_service = get_authorization_service()
                
                accessible_result = await auth_service.get_accessible_resources(
                    user_id=authenticated_user_id,
                    resource_type="presentation",
                    team_id=None
                )
                
                if accessible_result.get("success"):
                    # Get shared resource IDs (not owned by user, not already in shared_presentations)
                    existing_shared_ids = {p["id"] for p in shared_presentations}
                    auth_shared_ids = [
                        r["resource_id"] for r in accessible_result.get("shared_details", [])
                        if not r.get("is_owner", False) and r["resource_id"] not in existing_shared_ids
                    ]
                    
                    if auth_shared_ids:
                        # Fetch presentation details for these
                        from bson import ObjectId
                        auth_shared_query = {"_id": {"$in": [ObjectId(sid) if ObjectId.is_valid(sid) else sid for sid in auth_shared_ids]}}
                        auth_shared_docs = list(collection.find(
                            auth_shared_query,
                            {"title": 1, "goal": 1, "style": 1, "created_at": 1, "updated_at": 1, "thumbnail": 1, "slides": 1, "user_id": 1}
                        ))
                        
                        for doc in auth_shared_docs:
                            slides = doc.get("slides", [])
                            thumbnail_url = doc.get("thumbnail")
                            if thumbnail_url and thumbnail_url.startswith("s3://"):
                                try:
                                    thumbnail_url = image_processor.generate_presigned_url(thumbnail_url)
                                except Exception:
                                    thumbnail_url = None
                            
                            shared_presentations.append({
                                "id": str(doc["_id"]),
                                "title": doc.get("title", "Untitled"),
                                "goal": doc.get("goal"),
                                "style": doc.get("style"),
                                "slide_count": len(slides),
                                "created_at": doc.get("created_at"),
                                "updated_at": doc.get("updated_at"),
                                "thumbnail": thumbnail_url,
                                "isShared": True,
                                "sharedBy": doc.get("user_id"),
                                "permission": "read"
                            })
                        
                        logger.info(f"📤 [PRESENTATION] Found {len(auth_shared_ids)} additional shared presentations via auth service")
            except Exception as auth_e:
                logger.warning(f"⚠️ [PRESENTATION] Could not check auth service for shared presentations: {auth_e}")

        # Format Own Presentations
        result = []
        for pres in own_presentations:
            thumbnail_url = pres.get("thumbnail")
            if thumbnail_url and thumbnail_url.startswith("s3://"):
                try:
                    thumbnail_url = image_processor.generate_presigned_url(thumbnail_url)
                except Exception as url_err:
                    logger.warning(f"⚠️ [PRESENTATION] Failed to generate thumbnail URL: {url_err}")
                    thumbnail_url = None
            
            result.append({
                "id": str(pres.get("_id")),
                "title": pres.get("title", "Untitled"),
                "goal": pres.get("goal"),
                "style": pres.get("style"),
                "slide_count": pres.get("slide_count", 0),
                "created_at": pres.get("created_at"),
                "updated_at": pres.get("updated_at"),
                "thumbnail": thumbnail_url,
                "isShared": False
            })
        
        # Combine (Shared first, then Own)
        final_list = shared_presentations + result
        
        return {
            "success": True,
            "presentations": final_list,
            "total": own_count + len(shared_presentations),
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"📋 [PRESENTATION] List failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/presentation/{presentation_id}")
async def delete_presentation(presentation_id: str, request: Request):
    """
    Delete a presentation. Only the owner can delete.
    """
    authenticated_user_id = get_secure_user_id(request)
    
    logger.info(f"🗑️ [PRESENTATION] Deleting: {presentation_id} by authenticated user: {authenticated_user_id}")
    
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    
    try:
        collection = db["presentations"]
        
        # Delete S3 folder first using authenticated user
        image_processor.delete_document_folder(authenticated_user_id, "presentations", presentation_id)

        # SECURITY: Only delete if user owns the presentation
        result = collection.delete_one({
            "_id": presentation_id,
            "user_id": authenticated_user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Presentation not found or access denied")
        
        logger.info(f"✅ [PRESENTATION] Deleted: {presentation_id} by {authenticated_user_id}")
        return {"success": True, "message": "Presentation deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"🗑️ [PRESENTATION] Delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
