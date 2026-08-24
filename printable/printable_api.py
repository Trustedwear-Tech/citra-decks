# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
printable API - AI-powered printable generation endpoints

This module provides endpoints for generating printable outlines, PAGES,
styles, and images using LLM multimodal capabilities.

Endpoints:
- POST /printable/generate-outline - Generate PAGE outline from goal
- POST /printable/generate-style - Generate AI style/theme
- POST /printable/generate-PAGE - Generate single PAGE content
- POST /printable/generate-image - Generate image using vision API
- POST /printable/enhance-PAGE - AI enhancement for existing PAGE
- POST /printable/save - Save printable to MongoDB
- GET /printable/load - Load printable from MongoDB
- GET /printable/list - List user's printables
"""

from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, status, Depends, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import logging
import os
import json
import ast
import asyncio
from llm_oss import llm_call as _llm_call_base, llm_call_streaming as _llm_call_streaming_base
import time
import uuid
import copy
from datetime import datetime
import re
from citra_auth import get_secure_user_id

# Printable stays on GLM-5.1 even though the platform large tier now defaults to
# deepseek-v4-pro (see Citra-Service/.env LLM_LARGE_MODEL). Pin via
# PRINTABLE_LLM_MODEL; when a caller passes model=None on the large tier we
# substitute the pinned model so every large-tier printable call routes to
# GLM-5.1 without touching individual call sites. base_url/api_key still come
# from the LLM_LARGE_* tier config.
_SURFACE_LLM_MODEL = os.getenv("PRINTABLE_LLM_MODEL", "z-ai/glm-5.1").strip()


def llm_call(*args, model=None, tier="large", **kwargs):
    if model is None and tier == "large":
        model = _SURFACE_LLM_MODEL or None
    return _llm_call_base(*args, model=model, tier=tier, **kwargs)


def llm_call_streaming(*args, model=None, tier="large", **kwargs):
    if model is None and tier == "large":
        model = _SURFACE_LLM_MODEL or None
    return _llm_call_streaming_base(*args, model=model, tier=tier, **kwargs)

# Unified edit orchestrator (shared with presentation_api)
from services.edit_orchestrator import (
    PRINTABLE_CANVAS,
    orchestrate_edit,
    orchestrate_edit_streaming,
    orchestrate_all_edits,
    orchestrate_all_edits_streaming,
    enhance_page_legacy as _orchestrator_enhance_page_legacy,
    enhance_page_legacy_streaming as _orchestrator_enhance_page_legacy_streaming,
    enhance_single_element as _orchestrator_enhance_single_element,
    enhance_multiple_elements as _orchestrator_enhance_multiple_elements,
    enhance_image_element as _orchestrator_enhance_image_element,
    generate_chart_data as _orchestrator_generate_chart_data,
    validate_element_positions,
    build_page_context_summary,
)
from services.agent_deck_editor import agent_edit_deck_streaming, agent_edit_deck, agent_edit_deck_loop_streaming

# Structured data: schema-only previews from structured_file_metadata.
# Per-row data is no longer pre-fetched here — page LLMs see schema +
# 3 sample values per column. For computed chart values, callers should hit
# the composer/generate-chart endpoint, which routes through execute_code.
# For inline scalar facts (single numbers, top-N, aggregates) embedded in
# page text, the page LLM can call `compute_fact` (vault-only sandbox).
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

# Data filler: resolves _data_request placeholders the page LLM emits when it
# needs file-backed values. Kept as a fallback safety net for any leftover
# placeholders; the primary grounding path is now the prefetch-then-generate
# planner below.
try:
    from services.structured_data_filler import fill_data_requests
    DATA_FILLER_AVAILABLE = True
except ImportError:
    DATA_FILLER_AVAILABLE = False

# Prefetch-then-generate planner: at page-gen time, plan the aggregations this
# page needs against the user's structured files, run them in the sandbox, and
# inject the real numbers into the prompt so the page LLM never has to invent
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
    log_prefix: str = "printable",
    page_info: Optional[Dict[str, Any]] = None,
    user_query: Optional[str] = None,
) -> str:
    """Return a schema-preview block for the page prompt, optionally enriched
    with a COMPUTED DATA block produced by the data planner.

    When ``page_info`` and ``user_query`` are provided AND the planner is
    available, this triggers a single ``plan_and_compute`` call scoped to the
    current page so the page LLM sees real numbers instead of guessing.

    Empty string if no structured files in scope. Never raises.
    """
    if not STRUCTURED_DATA_AVAILABLE:
        return ""

    # Preferred path: goal-aware data overview (cached at outline time).
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
                block = "\n\n" + format_overview_for_prompt(overview, role="page")
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

        # Optional: prefetch-then-generate. Plan + compute aggregations scoped
        # to this single page and inline the result so the page LLM can copy
        # exact chart configs / stats / lists.
        if (
            DATA_PLANNER_AVAILABLE
            and page_info
            and user_query
            and isinstance(page_info, dict)
        ):
            try:
                title = (
                    page_info.get("title")
                    or page_info.get("page_title")
                    or page_info.get("slide_title")
                    or ""
                )
                desc = (
                    page_info.get("content_hint")
                    or page_info.get("description")
                    or page_info.get("summary")
                    or page_info.get("page_description")
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
    open_stack = []

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
        elif ch == ']':
            if open_stack and open_stack[-1] == '[':
                open_stack.pop()

    if not open_stack:
        return text  # Already balanced

    repair = text
    if in_string:
        repair += '"'

    for bracket in reversed(open_stack):
        if bracket == '{':
            last_comma = repair.rfind(',')
            last_open = repair.rfind('{')
            cut_pos = max(last_comma, last_open)
            if cut_pos > 0:
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
    logger.warning(f"📊 [PRINTABLE] {len(charts_to_fix)} malformed chart(s) detected ({chart_ids}), requesting AI fix...")

    # Clean internal flags before sending to AI
    for _, el in charts_to_fix:
        el["chartConfig"].pop("_ai_fix_needed", None)

    system_prompt = (
        "You are a Chart.js configuration expert. You will receive a page JSON with chart elements "
        "that have placeholder/demo chartConfig because the original AI-generated config was malformed.\n\n"
        "Generate valid, contextually appropriate Chart.js chartConfig for each chart element ID listed.\n\n"
        "Rules:\n"
        "- type: one of bar, line, pie, doughnut, radar, polarArea, scatter, bubble\n"
        "- data.labels: array of descriptive strings (3-6 items)\n"
        "- data.datasets: array with at least one object containing label (string), data (numbers array), backgroundColor (array of hex color strings)\n"
        "- Infer what the chart should show from the page title and surrounding text elements\n"
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
        f"Page title: {data.get('title', 'Untitled')}\n\n"
        f"Page elements:\n{json.dumps(context_elements, indent=2)}\n\n"
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
                logger.info(f"📊 [PRINTABLE] Chart '{el_id}' fixed by AI")
            else:
                el["chartConfig"] = dict(_CHART_DEMO_FALLBACK)
                logger.warning(f"📊 [PRINTABLE] AI fix for '{el_id}' still invalid, using demo fallback")

        logger.info(f"📊 [PRINTABLE] AI chart fix: {fixed_count}/{len(charts_to_fix)} successful")

    except Exception as e:
        logger.error(f"📊 [PRINTABLE] AI chart fix failed: {e}, using demo fallback for all")
        for _, el in charts_to_fix:
            el["chartConfig"] = dict(_CHART_DEMO_FALLBACK)

    return data


def sanitize_PAGE_data(PAGE_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize PAGE elements to ensure visibility and prevent overflow.
    1. Fixes numbered_step sequential numbering.
    2. Recalculates heights for text/cards based on content length.
    3. Enforces color contrast for text against backgrounds.
    """
    elements = PAGE_data.get("elements", [])
    
    # Fix numbered_step numbering before any other processing
    _fix_numbered_step_numbers(elements)
    
    bg_color = PAGE_data.get("backgroundColor", "#ffffff")
    
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

    PAGE_text_color = get_contrast_color(bg_color)

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
            # Approx chars per line (avg char width ~0.55 * fontSize)
            chars_per_line = max(1, width / (font_size * 0.55)) 
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
                elem["textColor"] = PAGE_text_color
            if not elem.get("titleColor") or has_low_contrast(elem.get("titleColor", ""), bg_color):
                elem["titleColor"] = PAGE_text_color
            if not elem.get("descriptionColor") or has_low_contrast(elem.get("descriptionColor", ""), bg_color):
                elem["descriptionColor"] = PAGE_text_color
            # Ensure number is visible - use contrast against circle color if needed, 
            # but usually number is white on colored circle. Let's assume white.

        elif etype == "text":
            # Check 'color' field (legacy / freeform pages)
            if not elem.get("color") or has_low_contrast(elem.get("color", ""), bg_color):
                elem["color"] = PAGE_text_color
            # Check 'fill' field (template-built pages) — only override if contrast is bad
            fill_val = elem.get("fill", "")
            if fill_val and has_low_contrast(fill_val, bg_color):
                elem["fill"] = PAGE_text_color

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

    return PAGE_data


def _estimate_text_height(elem: Dict[str, Any]) -> float:
    """
    Estimate the rendered height of a text element based on content wrapping.
    Uses the same formula as the frontend's validateTextElement for consistency.
    """
    # General path emits `text`, corporate path emits `content`. Accept either
    # so this estimator works for both — otherwise titles from the legacy
    # free-form generator are treated as 0-line and overflow detection silently
    # no-ops on the very elements that need it most.
    content = elem.get("content") or elem.get("text") or ""
    if not content:
        return elem.get("height", 60)
    
    font_size = elem.get("fontSize", 20)
    line_height = elem.get("lineHeight", 1.4)
    width = elem.get("width", 400)
    char_width_ratio = 0.55  # Match frontend's charWidthRatio
    
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


def _elements_overlap_horizontally(el1: Dict, el2: Dict) -> bool:
    """Check if two elements share horizontal space."""
    l1 = el1.get("x", 0)
    r1 = l1 + el1.get("width", 100)
    l2 = el2.get("x", 0)
    r2 = l2 + el2.get("width", 100)
    return l1 < r2 and l2 < r1


def fix_overlapping_elements(PAGE_data: Dict[str, Any], min_gap: int = 15) -> Dict[str, Any]:
    """
    Post-process PAGE data to detect and fix overlapping elements.
    
    Strategy:
    1. Compute accurate text heights via character-wrapping estimation
    2. Sort all positionable elements by Y
    3. For each pair of vertically & horizontally overlapping elements, push the lower one down
    4. Also fix children within cards/shapes that overflow their parent bounds
    
    Args:
        PAGE_data: The PAGE JSON from AI generation
        min_gap: Minimum vertical gap between elements (pixels)
        
    Returns:
        Modified PAGE_data with corrected positions
    """
    elements = PAGE_data.get("elements", [])
    if not elements:
        return PAGE_data
    
    SAFE_BOTTOM = 1080
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
            padding_bottom = 15
            if child_bottom > parent_height - padding_bottom:
                available_height = max(30, parent_height - child_y - padding_bottom)
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
                if child_y < prev_bottom + 8:  # 8px min gap inside cards
                    child["y"] = prev_bottom + 8
                    corrections_made += 1
    
    # === PHASE 2: Fix top-level element overlaps ===
    # Only process top-level positionable elements
    # NOTE: "shape" intentionally excluded — shapes are backgrounds, dividers, accent
    # lines, and decorative elements. Including them causes catastrophic cascading
    # overlap fixes (e.g. a full-page background rect pushes ALL content to the bottom).
    positionable_types = {"text", "card", "numbered_step", "image_placeholder", "chart"}
    positionable = [e for e in elements if e.get("type", "") in positionable_types]
    
    if len(positionable) < 2:
        if corrections_made > 0:
            logger.info(f"🔧 [OVERLAP] Total corrections: {corrections_made} (children only)")
        return PAGE_data
    
    # Sort by Y position
    positionable.sort(key=lambda e: e.get("y", 0))
    
    # Compute effective height for each element
    for elem in positionable:
        if elem.get("type") == "text":
            elem["_effective_height"] = _estimate_text_height(elem)
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
    CANVAS_HEIGHT = 1123
    BOTTOM_MARGIN = 40
    for elem in positionable:
        ey = elem.get("y", 0)
        eh = elem.get("height")
        if eh is not None and isinstance(ey, (int, float)) and isinstance(eh, (int, float)):
            bottom_edge = ey + eh
            if bottom_edge > CANVAS_HEIGHT - BOTTOM_MARGIN:
                new_y = CANVAS_HEIGHT - BOTTOM_MARGIN - eh
                if new_y >= BOTTOM_MARGIN:
                    logger.info(f"🔧 [OVERLAP] Clamped '{elem.get('id', '?')}' bottom {bottom_edge} → moved y from {ey} to {new_y}")
                    elem["y"] = round(new_y)
                    corrections_made += 1
                else:
                    max_h = CANVAS_HEIGHT - 2 * BOTTOM_MARGIN
                    logger.info(f"🔧 [OVERLAP] Clamped '{elem.get('id', '?')}' height {eh} → {max_h} (too tall for canvas)")
                    elem["y"] = BOTTOM_MARGIN
                    elem["height"] = round(max_h)
                    corrections_made += 1

    if corrections_made > 0:
        logger.info(f"🔧 [OVERLAP] Total corrections: {corrections_made} elements repositioned")
    
    return PAGE_data

# Import existing utilities

from persona import generate_persona_system_prompt
from services.image_processor import image_processor

# Structured data services for chart generation (re-import for module-scope alias used below)
try:
    from services.structured_prompt_builder import StructuredPromptBuilder  # noqa: F401
except ImportError:
    pass

router = APIRouter()


def _grounded_sys(base: str) -> str:
    """Prefix a system prompt with the canonical strict-grounding header.
    Used by factual content generators (page outlines, slot fills).
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

# Semaphore to limit concurrent page generation calls (prevents API rate limiting)
_page_generation_semaphore = asyncio.Semaphore(3)

# Log structured data availability
if not STRUCTURED_DATA_AVAILABLE:
    logger.warning("⚠️ [PRINTABLE] Structured data services not available for chart generation")

# MongoDB client for persistence
_mongo_db = None

def get_mongo_db():
    """Get MongoDB database connection."""
    global _mongo_db
    if _mongo_db is None:
        try:
            from citra_mongo import get_sync_database
            _mongo_db = get_sync_database()
            logger.info("🎬 [printable] MongoDB connection established")
        except Exception as e:
            logger.error(f"🎬 [printable] MongoDB connection failed: {e}")
            _mongo_db = None
    return _mongo_db


# ==================== Request/Response Models ====================

class GenerateOutlineRequest(BaseModel):
    goal: str = Field(..., description="printable goal/topic")
    printable_type: str = Field(default="informative", description="Type: informative, persuasive, instructional, pitch, report")
    target_audience: Optional[str] = Field(default=None, description="Target audience description")
    PAGE_count: int = Field(default=10, ge=1, le=30, description="Number of PAGES to generate")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs for context")
    use_internet_search: bool = Field(default=False, description="Fetch latest data from internet and embed in vault")
    prefetched_corpus: Optional[List[dict]] = Field(
        default=None,
        description=(
            "Caller-supplied research corpus [{text, title?, source?}]. When "
            "supplied (e.g. quick/main chat already did a fast search), each "
            "entry is embedded into the vault before outline generation, so "
            "the normal outline + per-page retrieval grounds the report on it "
            "— no deep-research sandbox spawn needed."
        ),
    )
    existing_outline: Optional[List[dict]] = Field(default=None, description="Existing page outline [{title, outline}] to refine rather than regenerate from scratch")
    deck_profile: str = Field(
        default="corporate",
        description=(
            "Single routing axis. 'corporate' → matcher picks a template from "
            "the executive A4 catalog, then slot-fill generation. 'general' → "
            "template path skipped entirely, LLM designs each page from "
            "scratch via the legacy free-form generator."
        ),
    )


class PAGEOutline(BaseModel):
    title: str
    content_hint: str
    layout: str = "title_content"
    image_prompt: Optional[str] = None


class GenerateOutlineResponse(BaseModel):
    success: bool
    PAGES: List[Dict[str, Any]]
    message: Optional[str] = None


class GenerateStyleRequest(BaseModel):
    prompt: str = Field(..., description="Style description prompt")


class StyleDefinition(BaseModel):
    name: str
    fontFamily: str
    textPrimary: str
    textSecondary: str
    accentColor: str
    PAGEBackground: str
    preview: Dict[str, str]


class GeneratePAGERequest(BaseModel):
    PAGE_info: Dict[str, Any] = Field(..., description="PAGE outline information")
    PAGE_index: int = Field(..., description="Index of this PAGE in printable")
    total_PAGES: int = Field(..., description="Total number of PAGES")
    printable_goal: str = Field(..., description="Overall printable goal")
    printable_type: str = Field(default="informative", description="printable type")
    style: Optional[Dict[str, Any]] = Field(default=None, description="Style definition")
    template_id: Optional[str] = Field(default=None, description="Template ID for template-based generation")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs")
    previous_PAGES: Optional[List[Dict[str, Any]]] = Field(default=None, description="Previous PAGES for context")
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
            "Pre-fetched per-page vault passages block (from "
            "/printable/prefetch-vault-chunks). When supplied, this page "
            "generation call skips its own /embeddings + Milvus + Mongo "
            "round-trip — the document-level prefetch already paid that "
            "cost in a single batched embed."
        ),
    )
    deck_plan: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Document-level storyboard produced by /printable/generate-outline-stream "
            "(SSE event type=storyboard). Contains the document's palette, typography "
            "scale, motif, and a per-page plan. When supplied, every page grounds its "
            "colours and visual mode in this shared design language."
        ),
    )
    deck_profile: str = Field(
        default="corporate",
        description=(
            "Single routing axis. 'corporate' → template path. 'general' → "
            "legacy free-form path (LLM designs the page from scratch)."
        ),
    )


class GenerateImageRequest(BaseModel):
    prompt: str = Field(..., description="Image generation prompt")
    style: Optional[str] = Field(default="professional", description="Image style")


class EnhancePAGERequest(BaseModel):
    PAGE_id: str = Field(..., description="PAGE ID")
    PAGE_content: Dict[str, Any] = Field(..., description="Current PAGE content")
    instruction: str = Field(..., description="Enhancement instruction")
    style: Optional[Dict[str, Any]] = Field(default=None, description="Style definition")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs for context")
    template_id: Optional[str] = Field(default=None, description="Template ID for template-based PAGES")
    printable_goal: Optional[str] = Field(default=None, description="Overall printable goal for context")
    printable_type: str = Field(default="informative", description="printable type: informative, persuasive, instructional, pitch, report")
    icon_set: str = Field(default="lucide", description="Icon set to use: lucide, ionicons")
    skip_vault: bool = Field(default=False, description="Whether to skip vault retrieval (for simple edits)")
    generation_quality: Optional[str] = Field(default="premium", description="Quality of generation for images: premium, medium, basic")
    is_update_all: bool = Field(default=False, description="True for 'Update All' (vault refresh), False for 'Edit All' (user instruction only)")
    deck_profile: str = Field(
        default="corporate",
        description=(
            "Single routing axis. 'corporate' → template-based edit. "
            "'general' → legacy free-form edit (LLM redesigns the page)."
        ),
    )
    deck_plan: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Document-level storyboard threaded into the edit prompt so edits stay coherent with the rest of the document.",
    )


class OrchestrateRequest(BaseModel):
    instruction: str = Field(..., description="User's natural language instruction")
    PAGE_content: Dict[str, Any] = Field(..., description="Current PAGE content")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs")
    # New fields for direct execution
    PAGE_id: Optional[str] = Field(default=None, description="PAGE ID for enhancement")
    style: Optional[Dict[str, Any]] = Field(default=None, description="Style definition")
    template_id: Optional[str] = Field(default=None, description="Template ID for template-based PAGES")
    # Selection mode fields
    edit_mode: str = Field(default='PAGE', description="'PAGE' for full PAGE, 'element' for single, 'multi' for multiple")
    selected_elements: Optional[List[Dict[str, Any]]] = Field(default=None, description="Array of selected elements to edit")
    # Overall printable context
    printable_goal: Optional[str] = Field(default=None, description="Overall printable goal for context")
    printable_type: str = Field(default="informative", description="printable type: informative, persuasive, instructional, pitch, report")
    icon_set: str = Field(default="lucide", description="Icon set to use: lucide, ionicons")
    # Agentic scope field
    user_edit_scope: str = Field(default='page', description="Frontend radio: 'element', 'page', 'all'")
    generation_quality: Optional[str] = Field(default="premium", description="Quality of generation for images: premium, medium, basic")
    fast_path: Optional[str] = Field(default=None, description="Skip classification: 'layout_fix' for direct page enhancement")
    # Document context for single-page edits
    pages_summary: Optional[List[Dict[str, Any]]] = Field(default=None, description="Lightweight page summaries for document-level context")
    deck_profile: str = Field(
        default="corporate",
        description="'corporate' → template path. 'general' → legacy free-form path.",
    )
    deck_plan: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Document-level storyboard threaded into the edit prompt so edits stay coherent with the rest of the document.",
    )


class OrchestrateResponse(BaseModel):
    success: bool = Field(default=True, description="Success status")
    intent: str = Field(..., description="Classified intent: simple_edit, data_addition, chart_request")
    requires_vault: bool = Field(default=False, description="Whether vault data is needed")
    
    # Direct execution results
    enhanced_PAGE: Optional[Dict[str, Any]] = Field(default=None, description="Result of enhance_PAGE if applicable")
    enhanced_element: Optional[Dict[str, Any]] = Field(default=None, description="Result of single element edit")
    enhanced_elements: Optional[List[Dict[str, Any]]] = Field(default=None, description="Result of multi-element edit")
    chart_config: Optional[Dict[str, Any]] = Field(default=None, description="Result of generate_chart_data if applicable")
    
    # Legacy/Meta fields
    chart_type: Optional[str] = Field(default=None, description="Chart type if chart_request")
    chart_query: Optional[str] = Field(default=None, description="Query for chart data generation")


class OrchestrateAllRequest(BaseModel):
    """Request for smart all-pages orchestration (single API call replaces N individual calls)"""
    instruction: str = Field(..., description="User's natural language instruction")
    pages_summary: List[Dict[str, Any]] = Field(..., description="Lightweight summaries: [{slide_index, slide_id, text_summary, element_types, title}]")
    full_pages: List[Dict[str, Any]] = Field(..., description="Complete PAGE data for all pages")
    current_page_index: int = Field(default=0, description="Currently viewed page index")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs")
    style: Optional[Dict[str, Any]] = Field(default=None, description="Style definition")
    printable_goal: Optional[str] = Field(default=None, description="Overall printable goal")
    printable_type: str = Field(default="informative", description="Printable type")
    icon_set: str = Field(default="lucide", description="Icon set to use")
    is_update_all: bool = Field(default=False, description="True for Update All (vault refresh with image regeneration), False for Edit All (user instruction only)")
    outline_changed: bool = Field(default=False, description="True when outlines were regenerated — triggers template re-matching")
    deck_profile: str = Field(
        default="corporate",
        description="'corporate' → template re-matching per page. 'general' → legacy free-form per page.",
    )
    deck_plan: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Document-level storyboard threaded into every per-page edit prompt so all edits stay storyboard-coherent.",
    )


class AgentEditRequest(BaseModel):
    """Agentic whole-document edit — the entire document is sent in one shot and
    the LLM decides what to change, returning a list of operations."""
    instruction: str = Field(..., description="User's natural-language chat message")
    pages: List[Dict[str, Any]] = Field(..., description="The ENTIRE document — every page with full elements (images as markers)")
    current_page_index: int = Field(default=0, description="Index of the page the user is viewing")
    style: Optional[Dict[str, Any]] = Field(default=None, description="Document style/theme")
    header_footer: Optional[Dict[str, Any]] = Field(default=None, description="Header/footer config")
    slide_numbers: Optional[Dict[str, Any]] = Field(default=None, description="Page-number config")
    printable_goal: Optional[str] = Field(default=None, description="Overall document goal")
    printable_type: str = Field(default="informative", description="Document type")
    chat_history: Optional[List[Dict[str, Any]]] = Field(default=None, description="Recent chat turns [{role,text}]")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs for grounding")
    selected_element_ids: Optional[List[str]] = Field(default=None, description="Element ids the user has selected on the canvas ('this' refers to them)")
    image_attachments: Optional[List[Dict[str, Any]]] = Field(default=None, description="Screenshots pasted into the chat: [{name, mimeType, base64}]. OCR'd server-side and prepended to the instruction.")


class ChartDataRequest(BaseModel):
    chart_type: str = Field(..., description="Chart type: bar, line, pie, doughnut, radar, polarArea, scatter, bubble")
    query: str = Field(..., description="Description of data to visualize")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs")
    page_context: Optional[Dict[str, Any]] = Field(default=None, description="Current PAGE/page content for AI context")
    source_context: Optional[str] = Field(default=None, description="Source type: printable or report")


class ChartDataResponse(BaseModel):
    success: bool
    chart_config: Dict[str, Any] = Field(default=None, description="Chart.js compatible config")
    message: Optional[str] = None


class SaveprintableRequest(BaseModel):
    id: Optional[str] = Field(default=None, description="printable ID (for updates)")
    title: str = Field(..., description="printable title")
    goal: Optional[Dict[str, Any]] = Field(default=None, description="printable goal")
    style: Optional[Dict[str, Any]] = Field(default=None, description="Style definition")
    PAGES: List[Dict[str, Any]] = Field(..., description="PAGE data")
    team_id: Optional[str] = Field(default=None, description="Team/Workspace ID (null for personal workspace)")
    printable_type: str = Field(default="informative", description="printable type")
    thumbnail: Optional[str] = Field(default=None, description="Thumbnail image (base64 or URL)")
    folder_id: Optional[str] = Field(default=None, description="Printable's dedicated folder (one per artifact)")
# ... (previous models)

class BatchGeneratePAGESRequest(BaseModel):
    items: List[GeneratePAGERequest] = Field(..., description="List of PAGES to generate")

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
        logger.warning("🎬 [printable] Shared vault context not available, using local")
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
        logger.warning(f"🎬 [printable] Vault retrieval failed: {e}")
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
    
    logger.info(f"🎬 [printable] Context formatted. Flattened {chunk_count} chunks from {len(grouped_content)} documents")
    
    return "\n\n---\n\n".join(formatted_parts)


# ==================== AI Generation Helpers ====================



# ==================== API Endpoints ====================

@router.post("/printable/generate-outline", response_model=GenerateOutlineResponse, deprecated=True)
async def generate_outline(request: Request, body: GenerateOutlineRequest):
    """
    LEGACY / DEPRECATED — Marked for deletion.
    UI exclusively uses /printable/generate-outline-stream.
    This non-streaming variant lacks internet search support.
    Remove once confirmed no external callers depend on it.
    """
    # SECURITY: Resolve user_id from JWT token
    user_id = get_secure_user_id(request)
    
    logger.info(f"🎬 [printable] Generating outline for: {body.goal[:50]}...")

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
                logger.info(f"🌊 [PRINTABLE] Prefetched structured data ({len(structured_data_context)} chars)")
        except Exception as e:
            logger.warning(f"🌊 [PRINTABLE] Structured data prefetch failed (non-blocking): {e}")

    # Prefetch unstructured-file metadata so the outline LLM knows which
    # PDF/DOCX/TXT files match the goal and can call personal_data_tool.
    unstructured_metadata_context = None
    if body.folder_ids:
        try:
            from services.unstructured_file_listing import prefetch_unstructured_metadata_for_outline
            unstructured_metadata_context = await prefetch_unstructured_metadata_for_outline(
                user_id=user_id, folder_ids=body.folder_ids, query=body.goal,
            )
            if unstructured_metadata_context:
                logger.info(f"📄 [PRINTABLE] Prefetched unstructured metadata ({len(unstructured_metadata_context)} chars)")
        except Exception as e:
            logger.warning(f"📄 [PRINTABLE] Unstructured metadata prefetch failed (non-blocking): {e}")
    
    # Build system prompt - STATIC CONTENT FIRST for caching
    # PROFILE-AWARE outline prompt. The user-picked deck_profile decides
    # whether we lock to executive A4 templates, allow a mix with charts +
    # selective images, or open the full library.
    _profile = getattr(body, 'deck_profile', None) or 'corporate_boardroom'

    if _profile == 'corporate_with_visuals':
        system_prompt = f"""You are designing a CORPORATE A4 report with strategic visuals. The base look is executive (typography-led, kicker → action-title → subhead spine), augmented by data charts, diagrams, and the occasional hero photograph where it materially helps the argument.

OUTPUT: {{"PAGES":[{{"title":"<action title — a CLAIM, not a topic>","content_hint":"2-3 sentences","layout":"<layout name>","kicker":"SHORT UPPERCASE LABEL","image_prompt":"<photo description — only for image-bearing layouts>","speaker_notes":"optional"}}]}}

PRIMARY LAYOUTS (executive A4 family — use as the backbone):
  exec_pg_cover, exec_pg_argument, exec_pg_stat_grid, exec_pg_features_2x2,
  exec_pg_industries_2x2, exec_pg_sovereignty_dark, exec_pg_closing_dark

PERMITTED EXTRAS (use when the page content earns them):
  chart_focus / chart_left / chart_right / chart_and_image / data_dashboard /
  stats_highlight / big_number / report_chart_focus  — for data-heavy pages
  process_steps / org_hierarchy / infographic_diagram / timeline  — for structural content
  title_image / image_left / image_right  — at most 1-2 pages per report where one hero photo earns its place

RULES:
- You MUST generate EXACTLY {body.PAGE_count} PAGES. Not more, not less.
- Action titles, not topic titles. The `title` field MUST be the page's claim.
- KICKER on every body page — short uppercase label (≤ 7 words).
- IMAGE BUDGET — at most 1-2 photographic pages per report. Most pages are text + colour + charts.
- DARK / LIGHT RHYTHM — page 1 and page N are dark; architecture pages can be dark; body stays light.
- VARIETY — never two consecutive pages of the same layout.
- IMAGE-PROMPT RULES (when emitting one): NAME CONCRETE PHYSICAL SUBJECTS DIRECTLY (animal, plant, object, person, place) — diffusion models render them accurately; euphemisms produce wrong subjects. Use visual analogues ONLY for abstract non-visual concepts (technical jargon, scientific processes, business metrics, brand names). No quoted strings. No "labeled / titled / saying / with text" phrasing.
- DATA ACCURACY: do NOT fabricate numbers. Use only values from provided context.

JSON only, no markdown."""
    elif _profile == 'general_with_images':
        system_prompt = f"""Expert printable designer. Create PAGE outlines with narrative arc and rich imagery.

OUTPUT: {{"PAGES":[{{"title":"...","content_hint":"2-3 sentences","layout":"title|title_content|two_column|image_focus|bullet_points|quote|comparison|chart|exec_pg_*","image_prompt":"A concise description of a PHOTO","speaker_notes":"optional"}}]}}

RULES:
- You MUST generate EXACTLY {body.PAGE_count} PAGES. Not more, not less.
- First=title PAGE, Last=CTA/summary. Include image_focus PAGES where appropriate. The exec_pg_* family is also available when a tighter look fits.
- EVERY non-exec page MUST include "image_prompt" — describe a PHOTOGRAPH only. NEVER request infographics, org charts, diagrams, flowcharts, or images containing text/labels/numbers.
- IMAGE-PROMPT RULES (CRITICAL — get the SUBJECT right): NAME CONCRETE PHYSICAL SUBJECTS DIRECTLY (animal, plant, object, person, place, food, vehicle, building, body part, weather, landscape) — diffusion models render concrete nouns accurately and do NOT leak them as text. Euphemisms like "small elongated creature with striped patterns" produce wrong subjects (e.g. a lizard instead of a caterpillar). Use visual analogues ONLY for abstract non-visual concepts (technical jargon, scientific processes, business metrics, brand names). No quoted strings. No "labeled / titled / saying / with text" phrasing. Pattern: <concrete subject>, <action>, <setting>, <lighting>, <composition>, <colour/mood>.
- DATA ACCURACY: do NOT hallucinate facts, numbers, or claims. Use only verifiable information from provided context. If data is unavailable, omit rather than invent.
JSON only, no markdown."""
    else:
        # Default — corporate_boardroom — strict executive A4 mode
        system_prompt = f"""Citra is an enterprise platform. EVERY printable you produce is a consultant-grade executive report — boardroom polish, typography-led, no filler photography. There is no separate "casual" mode.

OUTPUT: {{"PAGES":[{{"title":"<action title — a CLAIM, not a topic>","content_hint":"2-3 sentences","layout":"<one of the 7 layout names below>","kicker":"SHORT UPPERCASE LABEL (e.g. PILLAR 1 · BUSINESS PROCESS AUTOMATION)","speaker_notes":"optional talk-track"}}]}}

THE 7 LAYOUTS — every page picks exactly one:
  exec_pg_cover           → Page 1 ONLY. Dark navy cover, two-tone headline, three pillar pills. No image.
  exec_pg_argument        → THE WORKHORSE body page. Kicker + action title + subhead + heading + intro paragraph + 5-7 bullets. Use for any body page making one claim.
  exec_pg_stat_grid       → 4 headline KPIs / "by the numbers" / business impact. Light bg, 2x2 stat cards with coloured accent bars, optional explainer block. No image.
  exec_pg_features_2x2    → 4 distinct capabilities / value props in a 2x2 grid. Light bg, coloured icon circles. No image.
  exec_pg_industries_2x2  → 4 verticals each with 4-6 checkmark use-cases. Light bg, vertical coloured side-rules. No image.
  exec_pg_sovereignty_dark → Architecture / security / governance / trust posture. Dark bg, 4 dark cards in 2x2 + light governance panel. No image.
  exec_pg_closing_dark    → Last page ONLY. Dark navy, 2x2 numbered reason cards + cyan CTA strap. No image.

THE SPINE — every report follows this rhythm:
  Page 1                 : exec_pg_cover           (dark)
  Pages 2..N-1           : a varied mix from {{ exec_pg_argument (workhorse), exec_pg_stat_grid, exec_pg_features_2x2, exec_pg_industries_2x2, exec_pg_sovereignty_dark }}
  Page N                 : exec_pg_closing_dark    (dark)

VARIETY RULES:
- You MUST generate EXACTLY {body.PAGE_count} PAGES. Not more, not less. This is a strict requirement.
- Vary the body layout — do NOT use exec_pg_argument twice in a row. Alternate with stat_grid / features / industries / sovereignty for rhythm.
- exec_pg_sovereignty_dark is appropriate ONLY when the report speaks to trust / data-residency / security posture — don't shoehorn it.

ACTION TITLES, never topic titles. The `title` field MUST be the page's CLAIM. Examples:
  ✗ Topic:   "Q4 results"                       | ✓ Action:  "Q4 missed growth but cash position improved"
  ✗ Topic:   "Citra overview"                   | ✓ Action:  "Operations that run themselves. Owned by your team."
  ✗ Topic:   "Industries"                       | ✓ Action:  "Built for regulated, complex enterprises"
A reader skimming page titles alone should be able to reconstruct your argument.

KICKER — every body page gets a short uppercase label in the `kicker` field. Examples: "PILLAR 1 · BUSINESS PROCESS AUTOMATION", "BUSINESS IMPACT", "ARCHITECTURE & SOVEREIGNTY", "INDUSTRIES & USE CASES", "WHY BUY CITRA". Keep kickers ≤ 7 words.

NO IMAGES. Citra's executive aesthetic is typography + colour blocks + icons + simple shapes. DO NOT emit an `image_prompt` field on any page. Filler photography cheapens enterprise reports. Charts and stat numbers are first-class elements in the layouts themselves and are NOT images.

DATA ACCURACY: Do NOT hallucinate or fabricate facts, numbers, or claims in content_hint. Use ONLY verifiable information from provided context. If data is unavailable, omit rather than invent.

JSON only, no markdown."""

    # Pre-bind: lite-mode vault retrieval using the goal as query. Replaces
    # the previous agentic loop (~30-45 s) with a single Milvus top-k pull
    # (~1-2 s) followed by one synthesis call.
    outline_vault_block = ""
    if _outline_use_personal:
        from services.personal_data_tool import retrieve_vault_context_for_prompt
        outline_vault_block = await retrieve_vault_context_for_prompt(
            query=body.goal,
            user_id=user_id,
            folder_ids=body.folder_ids,
            max_results=8,
            log_prefix="PRINTABLE-OUTLINE-LEGACY-LITE",
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
(IMPORTANT: These are REAL aggregates from the user's files — top categories, totals, date ranges, breakdowns. Anchor every page title and content_hint on these actual values. Reference real names, real numbers, real periods. Do NOT write generic narrative when concrete facts are available, and never invent numbers.)"""

    user_prompt = f"""Create EXACTLY {body.PAGE_count} PAGES for a printable outline. The PAGES array must contain exactly {body.PAGE_count} items.

GOAL: {body.goal}
TYPE: {body.printable_type}
AUDIENCE: {body.target_audience or 'General professional audience'}
{context_section}

REMINDER: Output EXACTLY {body.PAGE_count} PAGES in the PAGES array. No more, no less."""

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
        PAGES = outline_data.get("PAGES", outline_data)
        
        # Enforce exact page count: truncate if AI returned more than requested
        requested_count = body.PAGE_count
        if len(PAGES) > requested_count:
            logger.info(f"🎬 [printable] Trimming {len(PAGES)} PAGES to requested {requested_count}")
            PAGES = PAGES[:requested_count]
        
        # Add IDs to PAGES
        PAGES_with_ids = []
        for i, PAGE in enumerate(PAGES):
            PAGES_with_ids.append({
                "id": f"PAGE_{int(time.time() * 1000)}_{i}",
                "order": i + 1,
                **PAGE
            })
        
        logger.info(f"🎬 [printable] Generated {len(PAGES_with_ids)} PAGE outlines (requested: {requested_count})")
        
        return GenerateOutlineResponse(
            success=True,
            PAGES=PAGES_with_ids,
            message=f"Generated {len(PAGES_with_ids)} PAGES"
        )
        
    except json.JSONDecodeError as e:
        logger.error(f"🎬 [printable] JSON parse error: {e}")
        raise HTTPException(status_code=500, detail="Failed to parse AI response")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"🎬 [printable] Outline generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/printable/generate-outline-stream")
async def generate_outline_stream(request: Request, body: GenerateOutlineRequest):
    """
    Stream PAGE outline generation with Server-Sent Events (SSE).
    
    Immediately returns response and streams PAGES as they are generated,
    providing better UX by showing progress in real-time.
    
    SSE Event Format:
    - {"type": "progress", "message": "...", "step": 1}
    - {"type": "PAGE", "index": 0, "PAGE": {...}}
    - {"type": "done", "total": 5}
    - {"type": "error", "message": "..."}
    """
    # SECURITY: Resolve user_id from JWT token
    user_id = get_secure_user_id(request)

    logger.info(f"🌊 [printable] Starting streaming outline for: {body.goal[:50]}...")

    async def generate_stream():
        try:
            # Send initial progress
            yield f"data: {json.dumps({'type': 'progress', 'message': 'Analyzing your printable goal...', 'step': 1})}\n\n"

            # Internet prefetch: run BEFORE vault retrieval so the freshly
            # embedded internet doc is picked up by the same vault retrieval
            # call used for outline + page generation.
            # Vault gate matches the per-page gate (`saas_enabled()`):
            # folder selection IS the vault toggle — the UI sends
            # `folder_ids=[]` when the toggle is OFF and the selected
            # folders when ON. `body.use_personal_data` is not required, so
            # the outline path doesn't sit at a stricter gate than per-page.
            _vault_enabled = bool(body.folder_ids)
            if body.use_internet_search:
                try:
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Searching the internet for latest data...', 'step': 2})}\n\n"
                    from services.internet_prefetch import prefetch_internet_research
                    prefetch_results = await prefetch_internet_research(
                        goal=body.goal,
                        doc_type=body.printable_type or "printable",
                        target_audience=body.target_audience,
                        user_id=user_id,
                        folder_id=(body.folder_ids[0] if body.folder_ids else None),
                        num_queries=1,
                    )
                    for r in prefetch_results:
                        yield f"data: {json.dumps({'type': 'internet_research', 'document_id': r['document_id'], 'folder_id': r['folder_id'], 'word_count': r['word_count']})}\n\n"
                    if prefetch_results:
                        logger.info(f"🌐 [PRINTABLE] Internet prefetch embedded {len(prefetch_results)} doc(s) in vault")
                        # Ensure vault retrieval uses the folder we just embedded
                        # to (so outline + page gen can see the internet doc).
                        if not _vault_enabled and body.folder_ids:
                            _vault_enabled = True
                except Exception as e:
                    logger.warning(f"🌐 [PRINTABLE] Internet prefetch failed (non-blocking): {e}")
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Internet search skipped, continuing...', 'step': 2})}\n\n"

            # Caller-supplied research corpus — quick / main chat already did
            # a fast search and handed the findings in. Embed it into the
            # vault (same path as the internet prefetch above) so the normal
            # outline + per-page retrieval grounds the report on it. No deep-
            # research sandbox spawn.
            if body.prefetched_corpus:
                try:
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Preparing your research...', 'step': 2})}\n\n"
                    from services.internet_prefetch import prefetch_corpus
                    corpus_results = await prefetch_corpus(
                        corpus=body.prefetched_corpus,
                        doc_type=body.printable_type or "printable",
                        user_id=user_id,
                        folder_id=(body.folder_ids[0] if body.folder_ids else None),
                    )
                    for r in corpus_results:
                        yield f"data: {json.dumps({'type': 'internet_research', 'document_id': r['document_id'], 'folder_id': r['folder_id'], 'word_count': r['word_count']})}\n\n"
                    if corpus_results:
                        logger.info(f"🌐 [PRINTABLE] Corpus prefetch embedded {len(corpus_results)} doc(s) in vault")
                        # The corpus IS the grounding data — enable vault
                        # retrieval and pin folder scope to where it landed.
                        if not body.folder_ids:
                            body.folder_ids = [corpus_results[0]["folder_id"]]
                        _vault_enabled = True
                except Exception as e:
                    logger.warning(f"🌐 [PRINTABLE] Corpus prefetch failed (non-blocking): {e}")
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Research prep skipped, continuing...', 'step': 2})}\n\n"

            # Vault chunks are fetched agentically by the LLM via
            # personal_data_tool in the `run_Enterprise_or_Personal_tool` call below
            # — no pre-fetch.
            vault_context = ""
            _use_personal_for_outline = bool(_vault_enabled) and bool(body.folder_ids)
            if _use_personal_for_outline:
                yield f"data: {json.dumps({'type': 'progress', 'message': 'Preparing data tools for outline...', 'step': 2})}\n\n"

            yield f"data: {json.dumps({'type': 'progress', 'message': 'Creating PAGE outline...', 'step': 3})}\n\n"
            
            # Prefetch structured data once for all pages
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
                        logger.info(f"🌊 [PRINTABLE] Prefetched structured data for all pages ({len(structured_data_context)} chars)")
                except Exception as e:
                    logger.warning(f"🌊 [PRINTABLE] Structured data prefetch failed (non-blocking): {e}")

            # Prefetch unstructured-file metadata so the outline LLM knows
            # which PDF/DOCX/TXT files match the goal.
            unstructured_metadata_context = None
            if body.folder_ids:
                try:
                    from services.unstructured_file_listing import prefetch_unstructured_metadata_for_outline
                    unstructured_metadata_context = await prefetch_unstructured_metadata_for_outline(
                        user_id=user_id, folder_ids=body.folder_ids, query=body.goal,
                    )
                    if unstructured_metadata_context:
                        logger.info(f"📄 [PRINTABLE] Prefetched unstructured metadata for all pages ({len(unstructured_metadata_context)} chars)")
                except Exception as e:
                    logger.warning(f"📄 [PRINTABLE] Unstructured metadata prefetch failed (non-blocking): {e}")

            # Build prompts (same as non-streaming version)
            system_prompt = f"""Expert printable designer. Create PAGE outlines with narrative arc.

OUTPUT: {{"suggested_topic":"A concise 1-2 sentence topic that best captures the document focus given the GOAL and CONTEXT","PAGES":[{{"id":1,"title":"...","content_hint":"2-3 sentences","layout":"title|title_content|two_column|image_focus|bullet_points|quote|comparison","image_prompt":"A concise description of a PHOTO (not infographic, not org chart, not diagram — a real photograph)","speaker_notes":"optional"}}]}}

RULES:
- You MUST generate EXACTLY {body.PAGE_count} PAGES. Not more, not less. This is a strict requirement.
- First=title PAGE, Last=CTA/summary, include image_focus PAGES where appropriate.
- Each PAGE MUST have a numeric "id" field.
- EVERY page MUST include "image_prompt" — it MUST describe a PHOTOGRAPH only (real-world scene, objects, people, nature, architecture, etc.). NEVER request infographics, org charts, diagrams, flowcharts, or any image containing text/labels/numbers.
- IMAGE-PROMPT RULES (CRITICAL — get the SUBJECT right): NAME CONCRETE PHYSICAL SUBJECTS DIRECTLY. If the page is about a caterpillar, write "caterpillar"; about a vineyard, write "vineyard"; about an MRI machine, write "MRI machine". Diffusion models render concrete physical nouns (animals, plants, objects, vehicles, food, buildings, body parts, weather, landscapes, people) accurately and DO NOT leak them as text. Euphemisms ("small elongated crawling creature with striped patterns") produce wrong subjects (e.g. a lizard instead of a caterpillar). Use visual analogues ONLY for ABSTRACT / NON-VISUAL concepts that have no physical form: technical jargon ("OAuth", "Kubernetes"), scientific processes ("Krebs cycle", "mitosis"), business metrics ("Q3 revenue"), brand/product names — replace those with generic analogues (e.g. "abstract organic structures with glowing connections" instead of "Krebs cycle diagram"). DO NOT use phrases like reading/titled/labeled/saying/with-text/with-caption. DO NOT include any quoted strings — quoted text gets rendered literally. Pattern: <concrete subject>, <action>, <setting>, <lighting>, <composition>, <colour/mood>.
- The "suggested_topic" MUST reflect the best focus for this document given the goal and any vault context provided — you have FULL FREEDOM to rewrite it completely if the data warrants a different angle.
- DATA ACCURACY: Do NOT hallucinate or fabricate facts, numbers, or claims. Use ONLY verifiable information from provided context. If data is unavailable, omit rather than invent.
- JSON only, no markdown."""

            context_section = ""
            if vault_context:
                context_section = f"""\n\nRELEVANT CONTEXT FROM USER'S DOCUMENTS:
{vault_context}
(IMPORTANT: Use this context ONLY if it is directly relevant to the GOAL.)"""

            # Pre-bind: lite-mode vault retrieval (no sub-query expansion, no
            # reranker, no agentic tool-loop) using the goal as query. Replaces
            # the previous agentic loop that fanned out 4-5 personal_data_tool
            # calls per outline (~30-45 s) with a single Milvus top-k pull
            # (~1-2 s) followed by one synthesis call.
            outline_vault_block = ""
            if _use_personal_for_outline:
                from services.personal_data_tool import retrieve_vault_context_for_prompt
                outline_vault_block = await retrieve_vault_context_for_prompt(
                    query=body.goal,
                    user_id=user_id,
                    user_email=getattr(getattr(request, 'state', None), 'user_email', None),
                    folder_ids=body.folder_ids,
                    max_results=8,
                    log_prefix="PRINTABLE-OUTLINE-LITE",
                    adaptive_threshold=True,
                    adaptive_floor=5,
                )

            if outline_vault_block:
                context_section += f"\n\n{outline_vault_block}"

            if unstructured_metadata_context:
                context_section += f"\n\n{unstructured_metadata_context}"

            if structured_data_context:
                context_section += f"""\n\nSTRUCTURED DATA FROM USER'S FILES (real precomputed values from uploaded spreadsheets/CSVs):
{structured_data_context}
(IMPORTANT: These are REAL aggregates from the user's files — top categories, totals, date ranges, breakdowns. Anchor every page title and content_hint on these actual values. Reference real names, real numbers, real periods. Do NOT write generic narrative when concrete facts are available, and never invent numbers.)"""

            existing_outline_section = ""
            if body.existing_outline:
                outline_items = json.dumps([{"id": item.get('id', i+1), "title": item.get('title', ''), "content_hint": item.get('outline', '')} for i, item in enumerate(body.existing_outline)])
                existing_outline_section = f"""\n\nEXISTING PAGE OUTLINE (use the SAME "id" values so changes map back to original pages):
{outline_items}

IMPORTANT: Return EXACTLY {len(body.existing_outline)} pages, each keeping its original "id".
- If a page is still relevant to the GOAL and CONTEXT: refine its title and content_hint.
- If a page is NO LONGER valid or applicable given the goal/context: completely rewrite its title and content_hint to something that IS relevant. Do NOT keep outdated or irrelevant content.
- You have full freedom to overhaul every page if the data warrants it. The only constraint is keeping the same count and the same id values."""

            user_prompt = f"""Create EXACTLY {body.PAGE_count} PAGES for a printable outline. The PAGES array must contain exactly {body.PAGE_count} items.

GOAL: {body.goal}
TYPE: {body.printable_type}
AUDIENCE: {body.target_audience or 'General professional audience'}
{context_section}{existing_outline_section}

REMINDER: Output EXACTLY {body.PAGE_count} PAGES in the PAGES array. No more, no less."""

            # Debug: dump exactly what the LLM will see so we can prove the
            # structured data reached the prompt intact (no truncation).
            logger.info(
                f"🌊 [printable][stream] PROMPT DUMP — system={len(system_prompt)}c "
                f"user={len(user_prompt)}c structured_block={len(structured_data_context or '')}c"
            )
            logger.info(
                f"🌊 [printable][stream] USER PROMPT >>>\n{user_prompt}\n<<< END USER PROMPT"
            )

            # Single streaming LLM call — vault chunks pre-injected via
            # outline_vault_block (lite-mode retrieval). Compute_fact /
            # personal_data_tool tool-calling intentionally dropped here.
            full_response = ""
            chunk_count = 0
            for chunk in llm_call_streaming(
                system_prompt=_grounded_sys(system_prompt),
                user_prompt=user_prompt,
                model=None,
                user_id=user_id,
                max_tokens=8000,
                temperature=0.2,
                top_p=0.95,
                json_mode=True,
                tier="large",
            ):
                full_response += chunk
                chunk_count += 1
                if chunk_count % 10 == 0:
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Generating PAGE details...', 'step': 4})}\n\n"
            
            # Parse the complete response
            yield f"data: {json.dumps({'type': 'progress', 'message': 'Finalizing outline...', 'step': 5})}\n\n"
            
            json_str = extract_json_from_response(full_response)
            outline_data = json.loads(json_str)
            
            # Handle double-encoded JSON
            if isinstance(outline_data, str):
                outline_data = json.loads(outline_data)
            
            if isinstance(outline_data, dict):
                PAGES = outline_data.get("PAGES") or outline_data.get("pages") or outline_data.get("slides")
                if PAGES is None:
                    # Check if dict itself looks like a single page
                    if outline_data.get("title") or outline_data.get("content_hint"):
                        logger.warning(f"🌊 [printable] Parsed dict looks like a single page — wrapping in list")
                        PAGES = [outline_data]
                    else:
                        # Try to find any list value
                        for key, val in outline_data.items():
                            if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                                PAGES = val
                                break
                        if PAGES is None:
                            PAGES = []
            elif isinstance(outline_data, list):
                PAGES = outline_data
            else:
                PAGES = []
            
            # Stream suggested topic if present
            suggested_topic = outline_data.get("suggested_topic", "")
            if suggested_topic:
                yield f"data: {json.dumps({'type': 'topic', 'topic': suggested_topic})}\n\n"
            
            # Enforce exact page count: truncate if AI returned more than requested
            requested_count = body.PAGE_count
            if len(PAGES) > requested_count:
                logger.info(f"🌊 [printable] Trimming {len(PAGES)} PAGES to requested {requested_count}")
                PAGES = PAGES[:requested_count]
            
            # Stream each PAGE individually
            for i, PAGE in enumerate(PAGES):
                original_id = PAGE.get('id', i + 1)
                PAGE_with_id = {
                    "id": f"PAGE_{int(time.time() * 1000)}_{i}",
                    "order": i + 1,
                    "original_id": original_id,
                    **{k: v for k, v in PAGE.items() if k != 'id'}
                }
                yield f"data: {json.dumps({'type': 'PAGE', 'index': i, 'PAGE': PAGE_with_id})}\n\n"
                # Small delay for visual effect
                await asyncio.sleep(0.1)

            # Storyboard pass — see presentation-side equivalent. Single LLM
            # call that produces the document's shared design language (palette
            # + typography + per-page intent). Client passes the returned dict
            # as `deck_plan` on every /printable/generate-PAGE call.
            try:
                yield f"data: {json.dumps({'type': 'progress', 'message': 'Planning document design...', 'step': 6})}\n\n"
                from services.storyboard import generate_storyboard
                storyboard = await generate_storyboard(
                    outline=PAGES,
                    goal=body.goal,
                    doc_type=body.printable_type or "informative",
                    surface="printable",
                    user_id=user_id,
                )
                yield f"data: {json.dumps({'type': 'storyboard', 'storyboard': storyboard})}\n\n"
            except Exception as _sb_exc:
                logger.warning(f"📐 [printable] storyboard pass failed (non-blocking): {_sb_exc}")

            # Send completion
            yield f"data: {json.dumps({'type': 'done', 'total': len(PAGES), 'message': f'Generated {len(PAGES)} PAGES'})}\n\n"
            
            logger.info(f"🌊 [printable] Streamed {len(PAGES)} PAGE outlines")
            
        except json.JSONDecodeError as e:
            logger.error(f"🌊 [printable] JSON parse error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to parse AI response'})}\n\n"
        except Exception as e:
            logger.error(f"🌊 [printable] Streaming error: {e}")
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


@router.post("/printable/generate-style")
async def generate_style(request: Request, body: GenerateStyleRequest):
    """
    Generate a custom printable style/theme using AI.
    """
    # SECURITY: Resolve user_id from JWT token
    user_id = get_secure_user_id(request)
    
    logger.info(f"🎨 [printable] Generating style: {body.prompt[:50]}...")
    
    system_prompt = """printable design expert. Generate color scheme.

OUTPUT: {"name":"Theme","fontFamily":"Inter","textPrimary":"#hex","textSecondary":"#hex","accentColor":"#hex","PAGEBackground":"#hex","preview":{"titleColor":"#hex","bodyColor":"#hex"}}

JSON only, no markdown."""

    user_prompt = f"""Create a printable style theme based on this description:

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
            max_tokens=4096,
            temperature=0.2,
            top_p=0.95,
            json_mode=True,
            tier="large",
        )
        
        # Parse JSON
        json_str = extract_json_from_response(ai_response)
        
        style_data = json.loads(json_str)
        
        logger.info(f"🎨 [printable] Generated style: {style_data.get('name')}")
        
        return {"success": True, "style": style_data}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"🎨 [printable] Style generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class PrefetchVaultChunksRequest(BaseModel):
    """Document-level batch vault prefetch input (printable / report).

    Submit ONE call with the full outline; the server batches all
    per-page queries into a single OpenAI `/embeddings` request and
    parallelises the Milvus+Mongo lookups. The response is a list of
    formatted vault blocks aligned 1:1 with the input outline — clients
    pass each block back into `/printable/generate-PAGE` via the
    `prefetched_vault_block` field so per-page generation skips its
    own retrieval cost.
    """
    outline: List[Dict[str, Any]] = Field(..., description="Ordered list of PAGE info dicts with at least 'title' and optionally 'content_hint'")
    folder_ids: Optional[List[str]] = Field(default=None, description="Vault folder IDs to scope retrieval")
    printable_goal: Optional[str] = Field(default=None, description="Fallback query when a page has no title/content_hint")
    max_results: int = Field(default=3, description="Max chunks per page block")


@router.post("/printable/prefetch-vault-chunks")
async def prefetch_vault_chunks_for_printable(request: Request, body: PrefetchVaultChunksRequest):
    """Batch-prefetch vault passages for every page in one shot.

    Eliminates the N concurrent OpenAI `/embeddings` calls (and their
    rate-limit retries) that we'd otherwise pay when the client fires
    `/printable/generate-PAGE` for every page in parallel. The blocks
    returned here are intended to be passed back to each page
    generation call via `prefetched_vault_block`.
    """
    user_id = get_secure_user_id(request)

    if not body.outline:
        return {"success": True, "blocks": []}
    if not body.folder_ids:
        return {"success": True, "blocks": ["" for _ in body.outline]}

    queries: List[str] = []
    for page in body.outline:
        title = (page.get("title") or "").strip() if isinstance(page, dict) else ""
        content_hint = (page.get("content_hint") or "").strip() if isinstance(page, dict) else ""
        composed = f"{title}. {content_hint}".strip(" .")
        queries.append(composed or (body.printable_goal or ""))

    from services.personal_data_tool import retrieve_vault_contexts_batch
    blocks = await retrieve_vault_contexts_batch(
        queries=queries,
        user_id=user_id,
        folder_ids=body.folder_ids,
        max_results=max(1, min(int(body.max_results or 3), 10)),
        log_prefix="PRINTABLE-PREFETCH",
    )
    return {"success": True, "blocks": blocks}


class CritiquePageRequest(BaseModel):
    """Vision-critique input for an A4 page: rendered PNG + element list.

    Client captures the fabric canvas via ``toDataURL('image/png')`` after
    page render and POSTs it with the current element JSON. Server runs
    one vision-LLM pass and returns the patched element list.
    """
    elements: List[Dict[str, Any]] = Field(..., description="Current element list to critique")
    screenshot: str = Field(..., description="PNG screenshot as a data URL (image/png;base64,...)")
    page_info: Optional[Dict[str, Any]] = Field(default=None, description="Optional page context (title, content_hint)")
    canvas: Optional[Dict[str, Any]] = Field(default=None, description="Canvas dims {width, height} — defaults to A4 794x1123")


@router.post("/printable/critique-page")
async def critique_page(request: Request, body: CritiquePageRequest):
    """One-shot vision critique on a rendered A4 page."""
    user_id = get_secure_user_id(request)
    from services.visual_critique import critique_and_patch
    result = await critique_and_patch(
        elements=body.elements,
        screenshot=body.screenshot,
        slide_info=body.page_info,
        canvas=body.canvas or {"width": 794, "height": 1123},
        user_id=user_id,
    )
    return {"success": True, **result}


@router.post("/printable/generate-PAGE")
async def generate_PAGE(request: Request, body: GeneratePAGERequest):
    """
    Generate a single A4 page.

    Single routing axis: ``body.deck_profile``.
      - ``general``   → legacy free-form generator (LLM designs from scratch).
        ``template_id`` is ignored.
      - ``corporate`` → template path: LLM matcher picks a template from the
        executive A4 catalog (keyword fallback), then slot-fill generation.
    """
    # SECURITY: Resolve user_id from JWT token
    user_id = get_secure_user_id(request)

    logger.info(f"🎬 [printable] Generating PAGE {body.PAGE_index + 1}: {body.PAGE_info.get('title', 'Unknown')}")

    _profile = (getattr(body, 'deck_profile', None) or 'corporate').lower()

    # ─── GENERAL: legacy free-form path ────────────────────────────────────
    if _profile in ('general', 'general_with_images'):
        body.template_id = None
        logger.info("🎬 [printable] deck_profile=general → legacy free-form generator")
        return await generate_PAGE_legacy(body, user_id)

    # ─── CORPORATE: template path ──────────────────────────────────────────
    if not body.template_id or body.template_id == 'ai_auto':
        from .printable_templates import auto_match_template, llm_match_template
        page_title = body.PAGE_info.get('title', '')
        page_instruction = body.PAGE_info.get('content_hint', body.PAGE_info.get('instruction', ''))
        page_layout = body.PAGE_info.get('layout', '')
        page_image_prompt = body.PAGE_info.get('image_prompt', '')

        llm_matched = await asyncio.to_thread(
            llm_match_template,
            page_title, page_instruction, body.PAGE_index, body.total_PAGES,
            page_layout, page_image_prompt, bool(body.structured_data_context), user_id,
            _profile,
        )
        if llm_matched:
            body.template_id = llm_matched
            logger.info(f"🎬 [printable] LLM-matched template: {body.template_id} for page '{page_title}' (layout={page_layout}, has_image_prompt={bool(page_image_prompt)})")
        else:
            body.template_id = auto_match_template(
                page_title, page_instruction, body.PAGE_index, body.total_PAGES,
                layout=page_layout, image_prompt=page_image_prompt,
                has_structured_data=bool(body.structured_data_context),
                deck_profile=_profile,
            )
            logger.info(f"🎬 [printable] Keyword-matched template (LLM fallback): {body.template_id} for page '{page_title}' (layout={page_layout}, has_image_prompt={bool(page_image_prompt)}, profile={_profile})")

    return await generate_PAGE_with_template(body, user_id)


async def generate_PAGE_with_template(request: GeneratePAGERequest, user_id: str):
    """
    Template-based page generation for A4 documents.
    
    AI only fills slot content (text, icon names, image descriptions).
    Positions come from the predefined A4 template.
    """
    from .printable_templates import (
        PAGE_TEMPLATES,
        get_slot_prompt_format,
        get_example_json_for_template,
        build_elements_from_template,
        apply_style_to_template,
    )
    # The exec footer helper is the same for slides and pages — it lives
    # in the shared slide_templates module and reads canvas_width/height
    # from the caller so the same function serves 16:9 and A4.
    from slide_templates import inject_exec_footer
    
    template_id = request.template_id
    template = PAGE_TEMPLATES.get(template_id)
    
    if not template:
        logger.warning(f"🎬 [printable] Template '{template_id}' not found, falling back to three_cards")
        template_id = "three_cards"
        template = PAGE_TEMPLATES.get(template_id)
    
    logger.info(f"🎬 [printable] Using template: {template_id}")
    
    # Get vault context for content — only if SaaS conditions are all met
    _has_prefetched = bool(request.structured_data_context)
    from composer_query import saas_enabled as _saas_enabled
    _should_fetch_saas = _saas_enabled(
        use_personal_data=request.use_personal_data,
        folder_ids=request.folder_ids,
        include_supplementary=request.include_supplementary
    )
    logger.info(
        f"🎬 [printable] SaaS fetch: {'enabled' if _should_fetch_saas else 'disabled'} "
        f"(personal={request.use_personal_data}, folders={bool(request.folder_ids)}, "
        f"supplementary={request.include_supplementary}, prefetched={_has_prefetched})"
    )
    # Vault chunks are PRE-FETCHED via lite-mode retrieval (no sub-query
    # expansion, no reranker, no agentic tool-loop) and injected into the
    # prompt below. Recovers the pre-refactor 1-RTT latency shape for
    # per-page generation.
    vault_context = ""
    _use_personal_for_page = bool(_should_fetch_saas) and bool(request.folder_ids)

    # Get structured data for charts — use prefetched if available, otherwise fetch per-page
    structured_data_context = ""
    if _has_prefetched:
        structured_data_context = request.structured_data_context
        logger.info(f"🎬 [printable] Using prefetched structured data ({len(structured_data_context)} chars)")
    elif _should_fetch_saas:
        structured_data_context = await _fetch_structured_schema_context(
            user_id, folder_ids=request.folder_ids, log_prefix="printable",
            page_info=request.PAGE_info,
            user_query=request.printable_goal,
        )

    # Pre-bind: focused Milvus top-k for THIS page, query keyed to title +
    # content_hint. Returns "" when folders are empty / no match.
    #
    # Fast path: when the client supplied a `prefetched_vault_block`
    # (document-level batch prefetch via /printable/prefetch-vault-chunks),
    # skip the per-page /embeddings + Milvus + Mongo round-trip entirely.
    # The batch endpoint already produced this block from a single OpenAI
    # embed call for all pages, avoiding the rate-limit retry storm we'd
    # otherwise see when N pages fire concurrent embed requests.
    page_vault_block = ""
    if request.prefetched_vault_block:
        page_vault_block = request.prefetched_vault_block
        logger.info(
            f"⚡ [PRINTABLE-PAGE-LITE] using prefetched vault block "
            f"({len(page_vault_block)} chars) — skipping per-page retrieval"
        )
    elif _use_personal_for_page:
        from services.personal_data_tool import retrieve_vault_context_for_prompt
        _page_query = (
            f"{request.PAGE_info.get('title', '')}. "
            f"{request.PAGE_info.get('content_hint', '')}"
        ).strip(" .")
        page_vault_block = await retrieve_vault_context_for_prompt(
            query=_page_query or request.printable_goal,
            user_id=user_id,
            folder_ids=request.folder_ids,
            max_results=3,
            log_prefix="PRINTABLE-PAGE-LITE",
        )
    
    # Build simplified system prompt for template-based generation
    slot_format = get_slot_prompt_format(template_id)
    example_json = get_example_json_for_template(template_id)
    
    # Determine icon instruction based on set
    icon_instruction = "kebab-case Lucide names (chart-bar, shield-check, users, lightbulb, rocket)"
    if request.icon_set == "ionicons":
        icon_instruction = "kebab-case Ionicons names (home-outline, settings-sharp, partly-sunny, add-circle)"

    # Determine Color Freedom Level
    # 'ai-auto' or no style -> Full Creative Freedom
    # Specific style -> Adhere to palette, but allow purposeful overrides
    is_auto_style = not request.style or request.style.get('id') == 'ai-auto'
    if is_auto_style:
        style_rule = "Style: full palette freedom."
    else:
        style_rule = f"Style palette: bg={request.style.get('PAGEBackground')}, text={request.style.get('textPrimary')}. Override per element when needed."

    # Background image rule — driven by the deck profile, not by template
    # prefix. The new "corporate" profile (merged exec + visuals) ALWAYS
    # emits a deck-coherent photographic background derived from the
    # storyboard's shared `background_style`. "general" leaves it to the
    # LLM per page.
    _is_exec_pg_template = (request.template_id or "").startswith("exec_pg_")
    from printable.printable_templates import profile_always_emits_background as _profile_always_bg
    _profile = getattr(request, 'deck_profile', None) or 'corporate'
    _profile_requires_bg = _profile_always_bg(_profile)
    _is_general_profile = (_profile in ("general", "general_with_images"))
    _deck_bg_style = (request.deck_plan or {}).get("background_style") if isinstance(getattr(request, "deck_plan", None), dict) else None
    _deck_bg_desc = (_deck_bg_style or {}).get("description") if isinstance(_deck_bg_style, dict) else None
    _deck_bg_motif = (_deck_bg_style or {}).get("motif") if isinstance(_deck_bg_style, dict) else None
    _deck_bg_palette = (_deck_bg_style or {}).get("palette_overlay") if isinstance(_deck_bg_style, dict) else None

    if _profile_requires_bg:
        _bg_hint_bits = []
        if _deck_bg_motif:
            _bg_hint_bits.append(f"motif={_deck_bg_motif}")
        if _deck_bg_palette:
            _bg_hint_bits.append(f"palette={_deck_bg_palette}")
        _bg_hint = (" (" + ", ".join(_bg_hint_bits) + ")") if _bg_hint_bits else ""
        _bg_desc_block = f'\n  Document-wide bg description (apply to THIS page too): "{_deck_bg_desc}".' if _deck_bg_desc else ""
        bg_image_rule = (
            'background_image (REQUIRED — corporate profile): emit sibling field '
            '"background_image": {"imageDescription":"...","imageType":"background"}. '
            f'The imageDescription MUST conform to the DOCUMENT\'S SHARED background style{_bg_hint} '
            f'so every page reads as part of one book — same atmosphere, same lighting, '
            f'same texture family, same palette overlay. Vary the specific scene per page, '
            f'but keep the visual language IDENTICAL.{_bg_desc_block}'
        )
    else:
        # General profile: completely up to the LLM. No prescription.
        bg_image_rule = "background_image: your call — emit a sibling `background_image` field if it serves the page."

    # See services/authoring_guidance.py — single source of truth that
    # presentation and printable share.
    from services.authoring_guidance import COMMON_AUTHORING_GUIDANCE_PRINTABLE
    from services.storyboard import render_for_prompt as _render_storyboard_for_prompt

    _storyboard_block = _render_storyboard_for_prompt(getattr(request, "deck_plan", None), request.PAGE_index)

    system_prompt = f"""You are designing page {request.PAGE_index + 1} of {request.total_PAGES} in a {request.printable_type} A4 document.

{COMMON_AUTHORING_GUIDANCE_PRINTABLE}

{(
    (
        "Document storyboard (LOCKED — every page shares this design):"
        if not _is_general_profile
        else (
            "Document storyboard (GUIDANCE ONLY, NOT MANDATORY — general profile gives you full creative freedom). "
            "Treat the palette, typography, motif, background style and per-page intent below as a reference "
            "for document cohesion. Use your own design intuition to make this page great: deviate from the palette / "
            "intent / template_family whenever the page's content suggests a better treatment. Don't optimize for "
            "matching the storyboard — optimize for the best possible page for this content."
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
    if request.previous_PAGES:
        prev_summaries = [f"Page {i+1}: {s.get('title', 'Unknown')}" 
                         for i, s in enumerate(request.previous_PAGES[-2:])]
        prev_context = f"\nPREVIOUS PAGES: " + ", ".join(prev_summaries)

    user_prompt = f"""Fill content for page {request.PAGE_index + 1} of {request.total_PAGES} in an A4 document.

Document Goal: {request.printable_goal}
TYPE (CRITICAL - STRICTLY FOLLOW): {request.printable_type}

PAGE INFO:
- Title: {request.PAGE_info.get('title', 'Untitled')}
- Content: {request.PAGE_info.get('content_hint', '')}
{prev_context}

{f"CONTEXT FROM USER'S DOCUMENTS:{chr(10)}{vault_context}" if vault_context else ""}
{structured_data_context}
{page_vault_block}
{f"SPECIAL INSTRUCTIONS FROM USER (MUST FOLLOW):{chr(10)}{request.special_instructions}" if request.special_instructions else ""}

Generate the JSON with slot content for this A4 page. Ensure content is appropriate for document/report format."""

    try:
        # Single LLM call per page — vault chunks are already injected via
        # `page_vault_block` above (lite-mode pre-fetch), so the agentic
        # tool-loop is no longer needed for slot synthesis. RETRY logic
        # handles empty responses and shape-mismatched JSON (model returns
        # a flat {"content": "..."} envelope instead of the slot-keyed
        # schema). Compute_fact / personal_data_tool tool-calling is
        # intentionally dropped here — structured aggregates already arrive
        # via `structured_data_context`, and per-page vault passages
        # already arrive via `page_vault_block`.
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
                    user_id=user_id,
                    # 32k output budget. With reasoning enabled, the model
                    # can spend several thousand tokens on internal reasoning
                    # before emitting the JSON. The prior 8k→16k caps were
                    # still being hit on pages with extra_elements + rich
                    # slots, causing truncated JSON parsed as "empty
                    # response"; doubled to 32k for headroom.
                    max_tokens=32000,
                    temperature=0.2,
                    top_p=0.95,
                    tier="large",
                    reasoning_effort="low",
                )

                if not ai_response or len(ai_response.strip()) <= 10:
                    logger.warning(f"⚠️ [printable] Empty/short response (attempt {attempt+1}/3). Retrying…")
                    await asyncio.sleep(1)
                    continue

                try:
                    json_str = extract_json_from_response(ai_response)
                    slot_data = json.loads(json_str)
                except Exception as parse_err:
                    last_parse_error = str(parse_err)
                    logger.warning(f"⚠️ [printable] JSON parse failed (attempt {attempt+1}/3): {parse_err}. Retrying…")
                    retry_hint = (
                        f"\n\nPREVIOUS ATTEMPT RETURNED INVALID JSON ({parse_err}). "
                        f"Output a single valid JSON object with the exact slot keys: {required_slots}."
                    )
                    await asyncio.sleep(1)
                    continue

                # Defensive: strip any [vault:...]/[doc:...]/[source:...]
                # citation markers that leaked through into slot text. Done
                # BEFORE extracting slots so downstream code (background_image,
                # missing-slot retry, build_elements_from_template) sees the
                # cleaned tree.
                from services.personal_data_tool import strip_citation_tags
                if isinstance(slot_data, dict):
                    slot_data = strip_citation_tags(slot_data)

                slots = slot_data.get("slots", slot_data) if isinstance(slot_data, dict) else {}
                if not isinstance(slots, dict):
                    slots = {}

                def _slot_has_substantive_content(s_val) -> bool:
                    """A slot counts as filled only when it actually carries
                    rendering content — not just `{"fill": "#xxx"}`.
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
                        f"⚠️ [printable] Shape mismatch: parsed keys {list(slots.keys())} "
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

                # Partial-mismatch detector: shape is right but a required
                # slot was left blank/missing (e.g. `exec_pg_argument` `bullets`
                # which the LLM consistently drops). One targeted retry with
                # an explicit per-slot example.
                if required_slots and missing_slots and attempt < 2 and not _is_general_profile:
                    logger.warning(
                        f"⚠️ [printable] Required slots missing: {missing_slots} "
                        f"(template={template_id}, attempt {attempt+1}/3). Retrying…"
                    )
                    _slot_examples = {
                        "bullets": '"• Demand grows 40% in emerging markets by 2030\\n• Renewables overtake coal in the power mix\\n• Investment in transmission must double\\n• Hydrogen scales as a long-duration storage backbone"',
                        "title": '"Your Action-Oriented Page Title Here"',
                        "subhead": '"One-sentence subhead that explains the page claim."',
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

                break
            except Exception as e:
                logger.error(f"⚠️ [printable] Template generation attempt {attempt+1} failed: {e}")
                if attempt == 2:
                    raise e
                await asyncio.sleep(1)

        if not ai_response or slot_data is None:
            raise ValueError(f"AI returned empty/invalid response after 3 attempts (last_parse_error={last_parse_error})")

        # Log raw AI response for debugging
        logger.debug(f"🎬 [printable] Raw AI response for template {template_id}: {ai_response[:500]}...")

        logger.info(f"🎬 [printable] Parsed slots: {list(slots.keys())}")

        missing_slots = [s for s in required_slots if not _slot_has_substantive_content(slots.get(s))]
        if missing_slots:
            logger.warning(f"🎬 [printable] Missing required slots after retries: {missing_slots}")

        # Last-resort fallback for `bullets` slots — if the LLM still won't
        # produce content after 3 attempts, synthesize bullets from the
        # other slots so the page isn't blank. Mirrors the slides-side
        # rescue path that prevents `exec_pg_argument` from rendering as
        # a solid white card.
        # GENERAL profile: no bullets fallback — template is pure guidance.
        for _slot_name, _slot_def in (template.get("slots", {}).items() if not _is_general_profile else []):
            if _slot_def.get("type") != "bullets":
                continue
            if _slot_has_substantive_content(slots.get(_slot_name)):
                continue
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
            _content_hint = (request.PAGE_info.get("content_hint") or "").strip()
            if _content_hint:
                _source_bits.append(_content_hint)
            _joined = " ".join(_source_bits)
            import re as _re_local
            _sentences = [s.strip() for s in _re_local.split(r"(?<=[.!?])\s+", _joined) if len(s.strip()) >= 8]
            if not _sentences:
                _sentences = [
                    f"Key takeaway from {request.PAGE_info.get('title', 'this page')}.",
                    "Refer to the title and subhead for the headline argument.",
                    "Supporting evidence is detailed in the source material.",
                    "See the takeaway for the bottom-line conclusion.",
                ]
            _fallback_lines = [f"• {s}" for s in _sentences[:5]]
            slots[_slot_name] = {"content": "\n".join(_fallback_lines)}
            logger.warning(
                f"🩹 [printable] Synthesized fallback bullets for slot '{_slot_name}' "
                f"({len(_fallback_lines)} lines from {len(_source_bits)} source slots)"
            )

        # Build final elements from template + slot content + style
        elements = build_elements_from_template(template, slots, request.style or {})

        # Escape hatch: the authoring guidance tells the LLM it may emit
        # an `extra_elements` array alongside `slots` for any element the
        # template doesn't have (custom SVG, accent shapes, extra cards,
        # source notes, etc.). Each entry is a fully-positioned element.
        _extra_elements = slot_data.get("extra_elements") if isinstance(slot_data, dict) else None
        if isinstance(_extra_elements, list) and _extra_elements:
            # Same overlap-guard as the presentation side — drop extras that
            # geometrically collide with filled content slots, so the LLM can't
            # silently double the body text + caption rows at the same coords.
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

            # Empty for general profile → no extra_element ever dropped for overlap.
            _filled_content_bboxes = []
            if not _is_general_profile:
                for _el in elements:
                    if not isinstance(_el, dict):
                        continue
                    if _el.get("type") not in ("text", "chart", "svg_diagram", "image_placeholder"):
                        continue
                    if _el.get("type") == "image_placeholder" and _el.get("imageType") == "background":
                        continue
                    _b = _bbox(_el)
                    if _b and _area(_b) > 100:
                        _filled_content_bboxes.append((_el.get("id", "?"), _b, _el.get("type")))

            _accepted = 0
            _dropped_overlap = 0
            _page_idx_ms = int(time.time() * 1000)
            for _i, _extra in enumerate(_extra_elements):
                if not isinstance(_extra, dict):
                    continue
                _etype = _extra.get("type")
                if _etype not in ("text", "shape", "image_placeholder", "chart", "svg_diagram", "icon", "bullets", "numbered_steps", "card"):
                    logger.warning(f"🎨 [printable] extra_elements[{_i}] dropped: unknown type={_etype!r}")
                    continue
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
                            f"🎨 [printable] extra_elements[{_i}] (type={_etype}) dropped: "
                            f"overlaps filled slot '{_sid}' (type={_stype}, "
                            f"{int(_ov_e*100)}% of extra / {int(_ov_s*100)}% of slot)"
                        )
                        _dropped_overlap += 1
                        continue
                if _etype == "bullets":
                    _raw = _extra.get("content", "")
                    if isinstance(_raw, list):
                        _raw = "\n".join(f"• {str(x).strip().lstrip('•').lstrip('-').lstrip('*').strip()}" for x in _raw if str(x).strip())
                    elif isinstance(_raw, str) and _raw and "•" not in _raw:
                        _raw = "\n".join(f"• {line.strip().lstrip('-').lstrip('*').strip()}" for line in _raw.split("\n") if line.strip())
                    _extra["type"] = "text"
                    _extra["textType"] = _extra.get("textType", "bullets")
                    _extra["content"] = _raw
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
                                logger.warning(f"🎨 [printable] extra_elements[{_i}] svg sanitize failed: {_err}")
                        except Exception as _sanitize_exc:
                            logger.warning(f"🎨 [printable] extra_elements[{_i}] svg sanitize errored: {_sanitize_exc}")
                if not _extra.get("id"):
                    _extra["id"] = f"extra_{_page_idx_ms}_{_i}"
                if "zIndex" not in _extra:
                    _extra["zIndex"] = 25
                elements.append(_extra)
                _accepted += 1
                if _ebbox and _etype in ("text", "chart", "svg_diagram", "image_placeholder"):
                    _filled_content_bboxes.append((_extra.get("id", "?"), _ebbox, _etype))
            if _accepted or _dropped_overlap:
                logger.info(
                    f"🎨 [printable] Accepted {_accepted}/{len(_extra_elements)} extra_elements "
                    f"({_dropped_overlap} dropped for overlap)"
                )

        # CORPORATE profile: enforce + synthesize bg if missing. GENERAL
        # profile: no guard — take whatever the LLM emitted (including
        # no bg if it chose that). The old "drop bg for exec / has_image=False
        # template" rule is intentionally GONE for general.
        bg_image_data = slot_data.get("background_image")
        if _profile_requires_bg and not bg_image_data and _deck_bg_desc:
            bg_image_data = {"imageDescription": _deck_bg_desc, "imageType": "background"}
            logger.info(
                f"\U0001F3A8 [PRINTABLE] Synthesized fallback background_image from document storyboard "
                f"(template={template.get('id')}, profile={_profile})"
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
                "width": 794,
                "height": 1123,
                "zIndex": 0,
                "opacity": 0.3,
                "generationQuality": "premium",
            }
            elements.insert(0, bg_element)
            logger.info(f"🎨 [PRINTABLE] Background image added: {bg_image_data['imageDescription'][:80]}")
        # No server-side fallback. If the LLM didn't emit background_image,
        # the page renders without one.
        
        # Get styled background
        styled = apply_style_to_template(template, request.style or {})
        
        # Final pass: Ensure generationQuality is set for image placeholders
        for el in elements:
            if el.get("type") == "image_placeholder":
                el["generationQuality"] = getattr(request, "generation_quality", "premium")

        # Priority: 1. AI Override, 2. Style Default, 3. White
        # EXCEPT for executive templates with a declared backgroundColor
        # (every `exec_pg_*` template, including the `_dark` family): the
        # template itself is the authoritative design surface — the AI
        # must not turn an `exec_pg_cover` page into white. apply_style_to_template
        # already routes the template's own bg into `styled["backgroundColor"]`,
        # so we just need to stop the AI value from winning here.
        ai_bg = slot_data.get("backgroundColor")
        style_bg = request.style.get("PAGEBackground", "#ffffff") if request.style else "#ffffff"
        _template_locks_bg = (
            bool(template.get("backgroundColor"))
            and template_id.startswith(("exec_", "exec_pg_"))
            and not _is_general_profile
        )
        if _template_locks_bg:
            background_color = styled.get("backgroundColor") or template.get("backgroundColor")
            if ai_bg and ai_bg.lower() != background_color.lower():
                logger.info(
                    f"🎨 [printable] Ignoring AI backgroundColor={ai_bg} for "
                    f"template {template_id} — template-locked to {background_color}"
                )
        else:
            background_color = ai_bg or styled.get("backgroundColor", style_bg)
        
        PAGE_data = {
            "template": template_id,
            "title": request.PAGE_info.get("title", ""),
            "elements": elements,
            "backgroundColor": background_color,
        }
        
        logger.info(f"🎬 [printable] Template PAGE generated with {len(elements)} elements")
        logger.info(f"📄 [DEBUG] Template PAGE JSON: {json.dumps(PAGE_data)}")

        # Resolve _data_request placeholders against the user's structured files.
        if DATA_FILLER_AVAILABLE:
            try:
                fill_report = await fill_data_requests(
                    PAGE_data,
                    user_id=user_id,
                    folder_ids=getattr(request, "folder_ids", None),
                    log_prefix="PRINTABLE",
                )
                if fill_report.get("data_warnings"):
                    PAGE_data["_data_warnings"] = fill_report["data_warnings"]
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"📊 [PRINTABLE] data filler raised: {exc}")

        # AI-powered chart fix: detect malformed chartConfigs and ask AI to regenerate
        PAGE_data = await _fix_malformed_charts_with_ai(PAGE_data, user_id)
        
        # Fix numbered_step sequential numbering
        _fix_numbered_step_numbers(PAGE_data.get("elements", []))

        # Layout refinement: second LLM pass to fix misplaced objects/text (DISABLED — saving credits/latency)
        # logger.info("🔧 [LAYOUT-FIX] Running layout refinement pass on template page...")
        # PAGE_data = await refine_PAGE_layout(PAGE_data, user_id)

        # Inject the consistent executive footer on every exec_pg_* page
        # (CITRA | DOC on the left, page / total on the right). A4 canvas
        # is 794×1123; the helper places the footer 24px above the bottom.
        inject_exec_footer(
            PAGE_data["elements"],
            template,
            deck_title=(getattr(request, "PAGE_goal", "") or getattr(request, "presentation_goal", "") or "")[:48],
            page=int(getattr(request, "PAGE_index", 0) or 0) + 1,
            total=int(getattr(request, "total_PAGES", 1) or 1),
            canvas_width=794,
            canvas_height=1123,
        )

        # Build response — include credit warning if layout fix hit insufficient credits.
        # critique_recommended is always True — vision critique runs on every
        # rendered page regardless of profile. Templated corporate pages can
        # still have subtle defects the deterministic post-processor misses
        # (overflow against template padding, icon-text overlap inside cards,
        # low-contrast text on the storyboard-locked background).
        response = {
            "success": True,
            "PAGE": PAGE_data,
            "critique_recommended": True,
        }
        if PAGE_data.pop("_credits_exhausted", False):
            response["credits_warning"] = {
                "error": "insufficient_credits",
                "message": PAGE_data.pop("_credits_message", "Insufficient credits"),
                "balance": PAGE_data.pop("_credits_balance", 0),
            }
            logger.warning(f"💰 [PRINTABLE] Including credits_warning in page response")
        else:
            PAGE_data.pop("_credits_message", None)
            PAGE_data.pop("_credits_balance", None)
        return response
        
    except json.JSONDecodeError as e:
        logger.error(f"🎬 [printable] JSON parse error in template generation: {e}")
        # Retry with bullets template as safe fallback
        logger.info("🎬 [printable] Retrying with bullets template as fallback")
        request.template_id = "bullets"
        return await generate_PAGE_with_template(request, user_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"🎬 [printable] Template PAGE generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def refine_PAGE_layout(PAGE_data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    Second LLM pass: Fix layout issues in a generated page.
    Corrects misplaced objects, overlapping text, off-canvas elements,
    and poor spacing. Does NOT change content — only geometry.
    Returns the corrected PAGE_data dict (falls back to original on failure).
    """
    system_prompt = """You are a Document Layout QA Expert. Your ONLY job is to fix the spatial layout of a JSON page for an A4 document.

CANVAS: 794×1123 pixels (A4 portrait at 96 DPI). ABSOLUTE BOUNDS: x ≥ 40, y ≥ 40, x+width ≤ 754, y+height ≤ 1080. NOTHING may exceed these limits.

STRICT RULES — FOLLOW EVERY ONE:
1. PRESERVE ALL ELEMENTS — never add, remove, merge, or reorder elements.
2. PRESERVE ALL CONTENT — never change "content", "title", "description", "iconName", "imageDescription", "imageType", "chartConfig", "number", or "shapeType".
3. PRESERVE ALL STYLING — never change "color", "fill", "backgroundColor", "borderRadius", "opacity", "borderColor", "fontFamily", "fontWeight", "fontStyle", or "lineHeight".
4. YOU MAY ONLY MODIFY these geometry/layout fields: "x", "y", "width", "height", "fontSize", "zIndex", "textAlign".
5. Also fix children geometry (relative x, y, width, height, fontSize inside parent).

LAYOUT FIXES TO APPLY:
• No element may extend beyond the ABSOLUTE BOUNDS (x+width ≤ 754, y+height ≤ 1080). Clamp or resize. This is the highest priority rule.
• OVERLAP DETECTION: For each element compute left=x, top=y, right=x+width, bottom=y+height. Two elements overlap if left1 < right2 AND right1 > left2 AND top1 < bottom2 AND bottom1 > top2. Check EVERY pair. Images, cards, text, shapes — ALL have bounding boxes. Do NOT layer cards or text on top of images. Maintain ≥10px gap between all element bounding boxes.
• Cards MUST use flat properties (title, description, iconName) directly on the card element. Do NOT split card content into separate sibling text/icon elements.
• Text: estimate rendered height as (ceil(len(content) / floor(width / (fontSize*0.6)))) × fontSize × lineHeight. Ensure the element's height accommodates this.
• If elements are stacked vertically, sort by visual hierarchy: title first, then subtitle, body, images/charts last.
• Background shapes (type:"shape" spanning most of the canvas) should have zIndex ≤ 1; content should have higher zIndex.
• Icons inside cards should be positioned before the title text (lower y).
• For A4 documents: prefer full-width elements (width close to 714px) for readability. Keep consistent left margin.

OUTPUT: Return the COMPLETE corrected JSON object with the same structure. JSON only — no markdown, no commentary."""

    user_prompt = f"""Fix the layout of this 794×1123 A4 document page. Only adjust positions, sizes, fontSize, zIndex, and textAlign. Keep all content and styling intact.

{json.dumps(PAGE_data)}"""

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
            return PAGE_data

        json_str = extract_json_from_response(response)
        fixed = parse_json_robustly(json_str)

        # Sanity: ensure element count didn't change
        orig_count = len(PAGE_data.get("elements", []))
        fixed_count = len(fixed.get("elements", []))
        if fixed_count != orig_count:
            logger.warning(f"⚠️ [LAYOUT-FIX] Element count mismatch (orig={orig_count}, fixed={fixed_count}), using original")
            return PAGE_data

        logger.info(f"✅ [LAYOUT-FIX] Page layout refined successfully ({fixed_count} elements)")
        return fixed

    except HTTPException as he:
        if he.status_code == 402:
            logger.warning(f"⚠️ [LAYOUT-FIX] Insufficient credits during layout refinement, using original layout")
            detail = he.detail if isinstance(he.detail, dict) else {}
            PAGE_data["_credits_exhausted"] = True
            PAGE_data["_credits_message"] = detail.get("message", "Insufficient credits") if detail else str(he.detail)
            PAGE_data["_credits_balance"] = detail.get("balance", 0) if detail else 0
        else:
            logger.error(f"⚠️ [LAYOUT-FIX] HTTP {he.status_code} during layout refinement: {he.detail}, using original")
        return PAGE_data
    except Exception as e:
        logger.error(f"⚠️ [LAYOUT-FIX] Layout refinement failed: {e}, using original")
        return PAGE_data



async def generate_PAGE_legacy(request: GeneratePAGERequest, user_id: str):
    """
    Generate content for a single PAGE.
    
    Creates text elements, suggests images, and applies layout
    based on the PAGE outline and printable style.
    """
    logger.info(f"🎬 [printable] Generating PAGE {request.PAGE_index + 1}: {request.PAGE_info.get('title', 'Unknown')}")
    
    # Get vault context for content — only if SaaS conditions are all met
    _has_prefetched = bool(request.structured_data_context)
    from composer_query import saas_enabled as _saas_enabled
    _should_fetch_saas = _saas_enabled(
        use_personal_data=request.use_personal_data,
        folder_ids=request.folder_ids,
        include_supplementary=request.include_supplementary
    )
    logger.info(
        f"🎬 [printable] Legacy SaaS fetch: {'enabled' if _should_fetch_saas else 'disabled'} "
        f"(personal={request.use_personal_data}, folders={bool(request.folder_ids)}, "
        f"supplementary={request.include_supplementary}, prefetched={_has_prefetched})"
    )
    # Vault chunks PRE-FETCHED via lite-mode retrieval (no sub-query
    # expansion, no reranker, no agentic tool-loop). Recovers pre-refactor
    # 1-RTT latency for ai-free / legacy printable per-page generation.
    vault_context = ""
    _legacy_use_personal = bool(_should_fetch_saas) and bool(request.folder_ids)

    # Get structured data for charts — use prefetched if available, otherwise fetch per-page
    structured_data_context = ""
    if _has_prefetched:
        structured_data_context = request.structured_data_context
        logger.info(f"🎬 [printable] Legacy PAGE: Using prefetched structured data ({len(structured_data_context)} chars)")
    elif _should_fetch_saas:
        structured_data_context = await _fetch_structured_schema_context(
            user_id, folder_ids=request.folder_ids, log_prefix="printable",
            page_info=request.PAGE_info,
            user_query=request.printable_goal,
        )

    # Pre-bind: focused Milvus top-k for THIS page. Returns "" when
    # vault is disabled / no match. Honors `prefetched_vault_block` from
    # the document-level /printable/prefetch-vault-chunks call so the
    # legacy path benefits from the same batch-embed optimization.
    legacy_page_vault_block = ""
    if request.prefetched_vault_block:
        legacy_page_vault_block = request.prefetched_vault_block
        logger.info(
            f"⚡ [PRINTABLE-PAGE-LEGACY-LITE] using prefetched vault block "
            f"({len(legacy_page_vault_block)} chars) — skipping per-page retrieval"
        )
    elif _legacy_use_personal:
        from services.personal_data_tool import retrieve_vault_context_for_prompt
        _legacy_page_query = (
            f"{request.PAGE_info.get('title', '')}. "
            f"{request.PAGE_info.get('content_hint', '')}"
        ).strip(" .")
        legacy_page_vault_block = await retrieve_vault_context_for_prompt(
            query=_legacy_page_query or request.printable_goal,
            user_id=user_id,
            folder_ids=request.folder_ids,
            max_results=3,
            log_prefix="PRINTABLE-PAGE-LEGACY-LITE",
        )

    # Style override — only when the user pinned a specific style (not "ai-auto").
    style_block = ""
    if request.style and request.style.get('id') and request.style.get('id') != 'ai-auto':
        style_block = (
            f"\nUSER-PINNED STYLE: bg={request.style.get('PAGEBackground', request.style.get('slideBackground', '#fff'))}, "
            f"title={request.style.get('textPrimary', '#000')}, "
            f"body={request.style.get('textSecondary', '#333')}, "
            f"accent={request.style.get('accentColor', '#3B82F6')}, "
            f"font={request.style.get('fontFamily', 'Arial')}. Use these unless the storyboard above is supplied."
        )

    # Storyboard slice (document-wide design language).
    from services.storyboard import render_for_prompt as _render_storyboard_for_prompt
    from services.authoring_guidance import FREEFORM_AUTHORING_GUIDANCE_PRINTABLE
    _storyboard_block = _render_storyboard_for_prompt(getattr(request, "deck_plan", None), request.PAGE_index)
    storyboard_section = (
        f"\nDOCUMENT STORYBOARD (document-wide design language — palette, typography, motif, per-page intent — "
        f"apply consistently across this page):\n{_storyboard_block}\n"
        if _storyboard_block else ""
    )

    icon_lib = "Ionicons (kebab-case, e.g. home-outline)" if request.icon_set == "ionicons" else "Lucide (kebab-case)"

    system_prompt = f"""You are designing page {request.PAGE_index + 1} of {request.total_PAGES} ({request.printable_type}) in an A4 document.

{FREEFORM_AUTHORING_GUIDANCE_PRINTABLE}

Icons: {icon_lib}.
{storyboard_section}{style_block}

IMAGE PROMPTS (image_placeholder.imageDescription) — describe a photographic scene only:
- Never include text, words, letters, numbers, labels, captions, watermarks, or signage in the description.
- Ground the scene in the page's geographic / cultural context inferred from goal + title + vault. People, architecture, vegetation, clothing, food, festivals must match the locale (e.g. India → Indian people, locally accurate streets and buildings; never default to Western faces unless the locale is explicitly Western).
- Pattern: <scene>, <lighting>, <composition>, <style cue>, <colour cue>.

CHARTS — when the page is about numbers/trends, PREFER a `chart` element over an image. Chart types: bar | line | pie | doughnut | radar | polarArea | scatter | bubble. Format:
{{"type":"chart","x":..,"y":..,"width":500,"height":340,"chartConfig":{{"type":"bar","data":{{"labels":[...],"datasets":[{{"label":"...","data":[...],"backgroundColor":["#3B82F6","#10B981"]}}]}}}}}}
Scatter/bubble use point objects. If a `=== COMPUTED DATA ===` block appears below, use its `value` verbatim — those are the ONLY trusted numbers; never fabricate aggregates from schema samples.

SVG DIAGRAMS — for org charts / process flows / cycles / venn / funnel / anatomy diagrams, emit a `svg_diagram` element with `svgContent` (raw SVG string), `fillColor`, `diagramKind`, `diagramTitle`. Use when a structural diagram tells the story better than text or a chart.

BACKGROUND IMAGE — optional top-level field `background_image: {{"imageDescription": "..."}}` (sibling of `elements`, NOT inside it). Scene only, no text.

DESIGN — one idea per page, vary rhythm vs previous pages, bullets ≤ 14 words, titles ≤ 8 words. Text colour must contrast with whatever the text sits on (card bg, not page bg, for text inside cards). A4 is portrait — design vertically.

TEXT SIZING (CRITICAL — most pages break here):
- For every text element you MUST size `fontSize` and `height` so the `text`/`content` fits the bounding box WITHOUT wrapping the title or clipping body text. Wrapped titles cascade over the element below them and break the layout.
- Estimate visible text width (rough): bold chars ≈ `fontSize × 0.55 × char_count`. Regular ≈ `fontSize × 0.48 × char_count`. The text MUST fit `width` at that fontSize on ONE line (titles, kickers, stat values) OR `height` must accommodate the wrapped lines (body paragraphs).
- TITLES: pick a fontSize that fits the WHOLE title text on one line of the given `width`. If the title is long, EITHER reduce fontSize (e.g. 44→32→28) OR increase `width` (use the full page width 714px after 40px margins). Do NOT set `height: 55` and `fontSize: 44` if the title is more than ~24 characters — it WILL wrap and overflow into the elements below.
- BODY PARAGRAPHS: pick a `height` large enough for wrapped lines (estimate lines = ceil(char_count / chars_per_line) where chars_per_line ≈ `width / (fontSize × 0.5)`; then `height ≈ lines × fontSize × 1.5`). If a paragraph wouldn't fit, prefer a smaller fontSize (12-13) and explicit `lineHeight: 1.4` over forcing the height up.
- STAT NUMBERS / KICKERS: keep them short (≤ 8 chars for stats, ≤ 6 words for kickers). One line, no wrap.
- Canvas is A4 portrait 794×1123. Maximum safe title width is 714 (40px margin each side). Never let any element extend past the page edges.

DATA ACCURACY — never hallucinate numbers, dates, names, claims. Use only verifiable facts from the COMPUTED DATA / vault / context. If unbacked, omit.

Output: one JSON object: {{"title":"...", "elements":[...], "background_image":{{...}}|null, "backgroundColor":"#RRGGBB"}}. JSON only, no markdown."""

    # Previous pages context for continuity
    prev_context = ""
    if request.previous_PAGES:
        prev_summaries = [f"Page {i+1}: {s.get('title', 'Unknown')} - {s.get('content_summary', '')[:100]}" 
                         for i, s in enumerate(request.previous_PAGES[-3:])]  # Last 3 pages
        prev_context = f"\n\nPREVIOUS PAGES FOR CONTEXT:\n" + "\n".join(prev_summaries)

    user_prompt = f"""Design page {request.PAGE_index + 1} of {request.total_PAGES} for an A4 document.

Document Goal: {request.printable_goal}
TYPE (CRITICAL - STRICTLY FOLLOW): {request.printable_type}

PAGE INFO:
- Title: {request.PAGE_info.get('title', 'Untitled')}
- Content: {request.PAGE_info.get('content_hint', '')}
- Suggested Layout: {request.PAGE_info.get('layout', 'title_content')}
{prev_context}

{legacy_page_vault_block}
{structured_data_context}

{f"SPECIAL INSTRUCTIONS FROM USER (MUST FOLLOW):{chr(10)}{request.special_instructions}" if request.special_instructions else ""}

Generate the JSON object for this A4 page. Ensure layout is proper with no overlapping elements for clean pixel-perfect document rendering."""

    try:
        # Call llm_oss (sync, run in thread) with RETRY logic
        ai_response = ""
        PAGE_data = None
        max_attempts = 4
        # Corrective feedback appended to the user prompt on each retry so the
        # model SELF-CORRECTS instead of blindly re-rolling the same prompt.
        # Empty on the first attempt; populated with the specific failure
        # reason (empty / 0-element / unparseable) before each retry.
        retry_feedback = ""

        # Visibility: the composer fires every page in parallel, but the
        # semaphore admits only 3 at a time. Log the wait so a queued page
        # isn't mistaken for a hang — the gap between these two lines is the
        # time this page spent waiting for a free generation slot.
        _page_no = request.PAGE_index + 1
        logger.info(f"⏳ [printable] Page {_page_no}/{request.total_PAGES} waiting for LLM generation slot")
        async with _page_generation_semaphore:
            logger.info(f"▶️ [printable] Page {_page_no}/{request.total_PAGES} acquired generation slot — calling LLM")
            for attempt in range(max_attempts):
                try:
                    # Single LLM call per page — vault chunks are pre-injected
                    # via legacy_page_vault_block (lite-mode retrieval).
                    # Compute_fact / personal_data_tool tool-calling dropped
                    # to recover pre-refactor latency.
                    ai_response = await asyncio.to_thread(
                        llm_call,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt + retry_feedback,
                        user_id=user_id,
                        # 100k output budget. glm-5.1 in reasoning mode
                        # regularly spends 15-25K tokens reasoning before
                        # emitting the JSON, and rich pages then need a large
                        # visible JSON body on top of that. At 50K we still saw
                        # batch failures where the reasoning trace plus a heavy
                        # page left too little room for complete JSON (parsed to
                        # 0 elements / `finish_reason=length`). 100K leaves
                        # generous headroom for reasoning AND the full page,
                        # well inside the model's 128K context window (input is
                        # only a few thousand tokens here). The llm_oss wrapper
                        # still auto-retries with an even larger budget on the
                        # rare length-truncation past that.
                        max_tokens=100000,
                        temperature=0.2,
                        top_p=0.95,
                        tier="large",
                        reasoning_effort="low",
                    )

                    if not (ai_response and len(ai_response.strip()) > 10):
                        logger.warning(f"⚠️ [printable] Legacy generation returned empty or short response (Attempt {attempt+1}/{max_attempts}). Retrying...")
                        retry_feedback = (
                            "\n\nYOUR PREVIOUS RESPONSE WAS EMPTY OR TOO SHORT. "
                            "Return ONE complete, valid JSON page object with a "
                            "non-empty \"elements\" array — no markdown fences, no commentary."
                        )
                        await asyncio.sleep(min(2 ** attempt, 8))  # Exponential backoff: 1s, 2s, 4s, 8s
                        continue

                    # Parse + validate the page INSIDE the retry loop. A
                    # response that parses to a page with ZERO renderable
                    # elements is a generation FAILURE, not a valid empty page
                    # — e.g. when glm-5.1 emits truncated/malformed JSON and the
                    # robust parser only recovers a nested object. Previously
                    # this slipped past the retry gate (which only checked raw
                    # string length) and shipped a BLANK page. Fail it here so
                    # the remaining attempts can produce real content.
                    candidate = parse_json_robustly(extract_json_from_response(ai_response))
                    if isinstance(candidate, dict) and "elements" not in candidate and "type" in candidate:
                        # AI returned a single flat element — wrap into a page.
                        candidate = {"elements": [candidate]}
                    n_elements = len(candidate.get("elements", [])) if isinstance(candidate, dict) else 0
                    if n_elements == 0:
                        logger.warning(
                            f"⚠️ [printable] Parsed page has 0 elements "
                            f"(Attempt {attempt+1}/{max_attempts}) — likely truncated/malformed "
                            f"LLM JSON. Retrying with corrective feedback..."
                        )
                        retry_feedback = (
                            "\n\nYOUR PREVIOUS RESPONSE FAILED: it parsed to a page with ZERO "
                            "renderable elements (the JSON was likely truncated or malformed). "
                            "Return ONE complete, valid JSON object with a non-empty \"elements\" "
                            "array. Keep it COMPACT — fewer, well-placed elements that fit within "
                            "the page canvas — and make sure the JSON is fully closed."
                        )
                        await asyncio.sleep(min(2 ** attempt, 8))
                        continue

                    PAGE_data = candidate
                    if attempt > 0:
                        logger.info(f"✅ [printable] Succeeded on attempt {attempt+1}")
                    break
                except Exception as e:
                    error_msg = str(e)
                    is_rate_or_overload = any(k in error_msg for k in ['429', '503', 'rate limit', 'UNAVAILABLE', 'high demand'])
                    logger.error(f"⚠️ [printable] Legacy generation attempt {attempt+1}/{max_attempts} failed: {e}")
                    if attempt == max_attempts - 1:
                        raise e
                    # A JSON parse/validation failure (not a transient
                    # rate/overload error) means the model emitted bad output —
                    # tell it so it self-corrects on the next attempt.
                    if not is_rate_or_overload:
                        retry_feedback = (
                            "\n\nYOUR PREVIOUS RESPONSE COULD NOT BE PARSED AS JSON. "
                            "Return ONE complete, valid, fully-closed JSON page object with a "
                            "non-empty \"elements\" array — no markdown fences, no commentary."
                        )
                    # Use longer backoff for rate limit / overload errors
                    backoff = min(2 ** (attempt + 1), 15) if is_rate_or_overload else min(2 ** attempt, 8)
                    await asyncio.sleep(backoff)  # Exponential backoff on errors

        # Fail loud: every attempt either errored, returned an empty/short
        # response, or parsed to a page with 0 elements. Do NOT ship a blank
        # page — surface the failure to the composer so it can retry/report.
        if PAGE_data is None:
            raise ValueError(
                f"AI returned no usable page (0 elements) after {max_attempts} attempts"
            )

        # PAGE_data was parsed, flat-wrapped, and element-count-validated
        # inside the retry loop above. Defensive: strip any
        # [vault:...]/[doc:...]/[source:...] citation markers that leaked into
        # element text.
        from services.personal_data_tool import strip_citation_tags
        if isinstance(PAGE_data, dict):
            PAGE_data = strip_citation_tags(PAGE_data)

        # Ensure all elements have unique IDs and carry over generationQuality if needed
        for i, element in enumerate(PAGE_data.get("elements", [])):
            if not element.get("id"):
                element["id"] = f"el_{int(time.time() * 1000)}_{i}"
            if element.get("type") == "image_placeholder":
                element["generationQuality"] = getattr(request, "generation_quality", "premium")
        
        logger.info(f"🎬 [printable] Generated PAGE with {len(PAGE_data.get('elements', []))} elements")
        logger.info(f"📄 [DEBUG] Legacy PAGE JSON: {json.dumps(PAGE_data)}")
        
        # Detect rogue background: LLM sometimes puts a full-canvas image_placeholder
        # inside elements[] instead of using the root-level background_image field
        if not PAGE_data.get("background_image"):
            elements = PAGE_data.get("elements", [])
            for i, el in enumerate(elements):
                if (el.get("type") == "image_placeholder"
                    and el.get("width", 0) >= 714 and el.get("height", 0) >= 1000
                    and el.get("x", 99) <= 40 and el.get("y", 99) <= 40
                    and ("bg" in el.get("id", "").lower() or "background" in el.get("id", "").lower())):
                    PAGE_data["background_image"] = {"imageDescription": el.get("imageDescription", "")}
                    elements.pop(i)
                    logger.info(f"🔄 [PRINTABLE] Converted rogue elements[] background to root background_image")
                    break
        
        # Inject background image element if AI decided to generate one
        bg_image_data = PAGE_data.get("background_image")
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
                "width": 794,
                "height": 1123,
                "zIndex": 0,
                "opacity": bg_image_data.get("opacity", 0.3),
                "generationQuality": "premium",
            }
            PAGE_data.setdefault("elements", []).insert(0, bg_element)
            logger.info(f"🎨 [PRINTABLE] Background image added (legacy): {bg_image_data['imageDescription'][:80]}")
        # No server-side fallback. If the LLM didn't emit background_image,
        # the page renders without one.
        
        # Fix numbered_step sequential numbering
        _fix_numbered_step_numbers(PAGE_data.get("elements", []))

        # Resolve _data_request placeholders against the user's structured files.
        if DATA_FILLER_AVAILABLE:
            try:
                fill_report = await fill_data_requests(
                    PAGE_data,
                    user_id=user_id,
                    folder_ids=getattr(request, "folder_ids", None),
                    log_prefix="PRINTABLE-LEGACY",
                )
                if fill_report.get("data_warnings"):
                    PAGE_data["_data_warnings"] = fill_report["data_warnings"]
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"📊 [PRINTABLE-LEGACY] data filler raised: {exc}")

        # Post-process: Fix overlapping elements (server-side safety net)
        # PAGE_data = fix_overlapping_elements(PAGE_data)  # DISABLED: testing LLM-based layout fixer
        
        # Layout refinement: second LLM pass to fix misplaced objects/text (DISABLED — saving credits/latency)
        # logger.info("🔧 [LAYOUT-FIX] Running layout refinement pass on legacy page...")
        # PAGE_data = await refine_PAGE_layout(PAGE_data, user_id)
        
        # Build response — include credit warning if layout fix hit insufficient credits.
        # critique_recommended is always True (see contract note in
        # generate_PAGE_with_template above).
        response = {"success": True, "PAGE": PAGE_data, "critique_recommended": True}
        if PAGE_data.pop("_credits_exhausted", False):
            response["credits_warning"] = {
                "error": "insufficient_credits",
                "message": PAGE_data.pop("_credits_message", "Insufficient credits"),
                "balance": PAGE_data.pop("_credits_balance", 0),
            }
            logger.warning(f"💰 [PRINTABLE] Including credits_warning in page response")
        else:
            PAGE_data.pop("_credits_message", None)
            PAGE_data.pop("_credits_balance", None)
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"🎬 [printable] PAGE generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# @router.post("/printable/generate-PAGES-batch")
# async def generate_PAGES_batch(request: BatchGeneratePAGESRequest):
#     """
#     Generate multiple PAGES in parallel batches (optimized speed).
#     PRE-FETCHES vault context once, then runs all AI calls in parallel.
#     """
#     logger.info(f"🎬 [printable] Batch generating {len(request.items)} PAGES...")
    
#     import asyncio
    
#     # UNIFIED PARALLEL CONTEXT + GENERATION
#     # Optimization: Run Fetch+Gen in a single parallel task stream
#     # Latency = max(Fetch + Gen) rather than max(Fetch) + max(Gen)
#     logger.info(f"🎬 [printable] Starting unified parallel generation for {len(request.items)} PAGES...")
    
#     # 1. Define unified worker function
#     async def process_PAGE_item(item):
#         """Fetch context and generate PAGE in one flow"""
#         vault_context = ""
        
#         # A. Fetch Context (if needed)
#         if item.folder_ids:
#             try:
#                 query = f"{item.printable_goal} - {item.PAGE_info.get('title', '')}: {item.PAGE_info.get('content_hint', '')}"
                
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
#                     logger.warning(f"⚠️ Vault fetch warning (PAGE {item.PAGE_index}): {e2}")
#                     vault_context = ""
        
#         # B. Generate PAGE (using fetched context)
#         return await generate_PAGE_with_context(item, vault_context)

#     # 2. Execute unified tasks in parallel
#     all_results = []
#     chunk_size = 5
    
#     try:
#         for i in range(0, len(request.items), chunk_size):
#             chunk = request.items[i:i + chunk_size]
#             logger.info(f"🎬 [printable] Processing batch {i//chunk_size + 1} ({len(chunk)} PAGES)")
            
#             # Create unified tasks
#             tasks = [process_PAGE_item(item) for item in chunk]
            
#             # Run parallel
#             results = await asyncio.gather(*tasks, return_exceptions=True)
            
#             # Process results
#             for idx, res in enumerate(results):
#                 if isinstance(res, Exception):
#                     logger.error(f"❌ Batch item {i+idx} failed: {res}")
#                     all_results.append({
#                         "success": False, 
#                         "error": str(res),
#                         "PAGE_index": chunk[idx].PAGE_index
#                     })
#                 else:
#                     all_results.append(res)

#     except Exception as e:
#         logger.error(f"🎬 [printable] Batch processing failed: {e}")
#         raise HTTPException(status_code=500, detail=str(e))
        
#     return {
#         "success": True,
#         "PAGES": [r.get("PAGE") for r in all_results if r.get("success")],
#         "total": len(request.items),
#         "results": all_results
#     }


# async def generate_PAGE_with_context(request: GeneratePAGERequest, vault_context: str = ""):
#     """
#     Generate a single PAGE using PRE-FETCHED vault context.
#     This is the parallel-optimized version - no vault retrieval inside.
#     """
#     logger.info(f"🎬 [printable] Generating PAGE {request.PAGE_index + 1}: {request.PAGE_info.get('title', 'Unknown')}")
    
#     # Build system prompt
#     # Build system prompt
#     style_info = ""
#     if request.style:
#         if request.style.get('id') == 'ai-auto':
#             style_info = """
# CRITICAL STYLE INSTRUCTION:
# The user has requested YOU (the AI) to decide the best color palette for this printable.
# - Analyze the content and topic (e.g., medical, business, creative, tech).
# - SELECT A COLOR PALETTE that enhances the mood and readability.
# - Use this selected palette consistently for this PAGE.
# - Ensure HIGH CONTRAST between text and background.
# - You are free to choose background colors, text colors, and accents.
# """
#         else:
#             style_info = f"""
# CRITICAL STYLE RULES (YOU MUST FOLLOW THESE):
# - Background: {request.style.get('PAGEBackground', '#ffffff')}
# - Primary Text: {request.style.get('textPrimary', request.style.get('textStyles', {}).get('title', {}).get('color', '#000000'))}
# - Body Text: {request.style.get('textSecondary', request.style.get('textStyles', {}).get('body', {}).get('color', '#333333'))}
# - Accent: {request.style.get('accentColor', '#3B82F6')}
# - Font: {request.style.get('fontFamily', 'Arial')}

# IMPORTANT: You MUST use the exact hex codes provided above for text 'fill' properties. Do NOT default to white or black unless specified above.
# """
    
#     system_prompt = f"""You are a WORLD-CLASS printable designer creating visually stunning, professional PAGES.

# DESIGN PHILOSOPHY:
# - Create BEAUTIFUL, visually-rich PAGES (not just text!)
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
# - MAXIMUM 1 content image per PAGE. The optional background_image is separate and does NOT count toward this limit.
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
#   "title": "PAGE title",
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
# - For comparison PAGES: Use 3 cards side-by-side
# - Group related text/icons into a "card" or "container" so they move together.
# - Use relative coordinates for children to ensure they stay inside the box even if the box moves.
# - For lists, create a container for each item containing the bullet and text.
# - For process PAGES: Use numbered_step elements
# - For feature lists: Use cards with icons
# - Ensure NO top-level elements overlap.
# - Output ONLY valid JSON with no markdown formatting."""

#     # Previous PAGES context for continuity
#     prev_context = ""
#     if request.previous_PAGES:
#         prev_summaries = [f"PAGE {i+1}: {s.get('title', 'Unknown')} - {s.get('content_summary', '')[:100]}" 
#                          for i, s in enumerate(request.previous_PAGES[-3:])]  # Last 3 PAGES
#         prev_context = f"\n\nPREVIOUS PAGES FOR CONTEXT:\n" + "\n".join(prev_summaries)

#     user_prompt = f"""Design PAGE {request.PAGE_index + 1} of {request.total_PAGES}.

# printable: {request.printable_goal}
# TYPE: {request.printable_type}

# PAGE INFO:
# - Title: {request.PAGE_info.get('title', 'Untitled')}
# - Content: {request.PAGE_info.get('content_hint', '')}
# - Suggested Layout: {request.PAGE_info.get('layout', 'title_content')}
# {prev_context}

# {f"CONTEXT FROM USER'S DOCUMENTS:{chr(10)}{vault_context}" if vault_context else ""}

# {f"SPECIAL INSTRUCTIONS FROM USER (MUST FOLLOW):{chr(10)}{rrequest.special_instructions}" if request.special_instructions else ""}

# Generate the JSON object for this PAGE."""

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
        
#         PAGE_data = json.loads(json_str)
        
#         # Ensure all elements have unique IDs
#         for i, element in enumerate(PAGE_data.get("elements", [])):
#             if not element.get("id"):
#                 element["id"] = f"el_{int(time.time() * 1000)}_{i}"
        
#         logger.info(f"🎬 [printable] Generated PAGE with {len(PAGE_data.get('elements', []))} elements")
#         logger.info(f"📄 [DEBUG] Context PAGE JSON: {json.dumps(PAGE_data)}")
        
#         # Post-process to fix any overlapping elements
#         # Post-process: Sanitize (colors/heights) THEN fix overlaps
#         # PAGE_data = sanitize_PAGE_data(PAGE_data)
#         # PAGE_data = fix_overlapping_elements(PAGE_data)
        
#         return {"success": True, "PAGE": PAGE_data}
        
#     except Exception as e:
#         logger.error(f"🎬 [printable] PAGE generation failed: {e}")
#         return {"success": False, "error": str(e), "PAGE_index": request.PAGE_index}





@router.post("/printable/enhance-PAGE")
async def enhance_PAGE(request: Request, body: EnhancePAGERequest):
    """Edit a single A4 page.

    Single routing axis: ``body.deck_profile``. Profile wins over any stale
    ``template_id``.
      - ``general``   → legacy enhancement (LLM redesigns elements freely).
      - ``corporate`` → template-based slot enhancement.
    """
    user_id = get_secure_user_id(request)
    _profile = (getattr(body, 'deck_profile', None) or 'corporate').lower()
    logger.info(f"✨ [printable] Enhancing PAGE: {body.instruction[:50]}... (profile={_profile}, skip_vault={body.skip_vault})")

    if _profile in ('general', 'general_with_images'):
        body.template_id = None
        logger.info("✨ [printable] deck_profile=general → legacy enhancement")
        return await enhance_PAGE_legacy(body, user_id)

    if body.template_id:
        return await enhance_PAGE_with_template(body, user_id)
    logger.warning("✨ [printable] corporate edit with no template_id — falling back to legacy")
    return await enhance_PAGE_legacy(body, user_id)


async def enhance_PAGE_with_template(request: EnhancePAGERequest, user_id: str):
    """
    Template-based PAGE enhancement.
    AI only modifies slot CONTENT (text, iconName, imageDescription).
    Positions remain fixed from template definition.
    """
    from .printable_templates import PAGE_TEMPLATES, build_elements_from_template, apply_style_to_template, get_slot_prompt_format, get_example_json_for_template
    
    template_id = request.template_id
    template = PAGE_TEMPLATES.get(template_id)
    
    if not template:
        logger.warning(f"✨ [printable] Template '{template_id}' not found, falling back to legacy")
        return await enhance_PAGE_legacy(request, user_id)
    
    # Vault chunks now fetched agentically by the LLM via personal_data_tool
    # inside run_Enterprise_or_Personal_tool below — no pre-fetch.
    # For Edit All (is_update_all=False): respect skip_vault — grammar/formatting edits don't need vault
    # For Update All (is_update_all=True): always enable the tool
    vault_context = ""
    _should_fetch_vault = (request.is_update_all or not request.skip_vault) and bool(request.folder_ids)
    _enhance_use_personal = bool(_should_fetch_vault)
    if not _enhance_use_personal and request.skip_vault and not request.is_update_all:
        logger.info(f"✨ [printable] Skipping vault tool (skip_vault={request.skip_vault}, is_update_all={request.is_update_all})")
    
    # Get structured data for charts (Excel, JSON, CSV, SaaS records)
    # Skip structured data for Edit All when vault is skipped (grammar/formatting edits)
    structured_data_context = ""
    if _should_fetch_vault:
        # Synthesize a page_info from the existing PAGE_content (template edit flow):
        # we don't have the original outline, but the title element + instruction
        # give the planner enough signal.
        edit_page_info = {
            "title": request.PAGE_content.get("title", "") if isinstance(request.PAGE_content, dict) else "",
            "content_hint": request.instruction,
        }
        structured_data_context = await _fetch_structured_schema_context(
            user_id, folder_ids=request.folder_ids, log_prefix="printable_template",
            page_info=edit_page_info,
            user_query=request.printable_goal or request.instruction,
        )
    
    # Extract current slot content from existing PAGE
    # Map element IDs to template slot names (e.g., "slot_title_123_0" -> "title")
    current_slots = {}
    original_id_by_slot = {}  # slot_name → original element ID (for ID preservation after rebuild)
    template_slot_names = list(template.get("slots", {}).keys())
    
    for element in request.PAGE_content.get("elements", []):
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
    
    # Get expected slots from template (fix: use template_id, not template object)
    slot_format = get_slot_prompt_format(template_id)
    example_json = get_example_json_for_template(template_id)
    
    # Build mode-aware rules based on is_update_all
    if request.is_update_all:
        # UPDATE ALL mode: vault-driven, compare-and-update
        mode_rules = """RULES (UPDATE ALL MODE — vault data refresh):
1. Return ALL slots with content - never omit any slot
2. COMPARE the current page content against the vault/context data provided below
3. Update ONLY the parts where the data has changed — keep everything else VERBATIM
4. If a slot's content is still accurate per the vault data, return it UNCHANGED
5. Update 'imageDescription' of image_placeholder elements ONLY if the content change makes the current image irrelevant
6. You may restructure content if the new data tells a significantly different story
7. Content should be appropriate for A4 document format
8. JSON only, no markdown"""
    else:
        # EDIT ALL mode: user-instruction-only, strict preservation
        mode_rules = """RULES (EDIT ALL MODE — follow user instruction strictly):
1. Return ALL slots with content - never omit any slot
2. ONLY modify what the instruction EXPLICITLY asks for (e.g. grammar fixes, translation, formatting)
3. For slots NOT affected by the instruction, return their content EXACTLY AS-IS — do NOT rephrase, rewrite, improve, or expand
4. Do NOT change imageDescription fields unless the instruction specifically asks to update images
5. Do NOT add new information, elaborate, or enrich content beyond what the instruction requests
6. Preserve the exact wording, tone, and length of unaffected content
7. Content should be appropriate for A4 document format
8. JSON only, no markdown"""
    
    # Storyboard slice — same document-wide design language used by initial
    # generation. Threading it into edits keeps the edited page visually
    # coherent with the rest of the document.
    from services.storyboard import render_for_prompt as _render_storyboard_for_prompt
    _page_idx_for_sb = request.PAGE_content.get("page_index") or request.PAGE_content.get("order", 1) - 1 if isinstance(request.PAGE_content, dict) else 0
    try:
        _page_idx_for_sb = int(_page_idx_for_sb)
    except (TypeError, ValueError):
        _page_idx_for_sb = 0
    _sb_block = _render_storyboard_for_prompt(getattr(request, "deck_plan", None), _page_idx_for_sb)
    _sb_section = (
        f"\n\nDOCUMENT STORYBOARD (LOCKED — every page shares this design):\n{_sb_block}\n"
        if _sb_block else ""
    )

    system_prompt = f"""Modify A4 document template slot content. Layout: {template.get('name')}.

IMPORTANT: This is an A4 DOCUMENT/REPORT page (794x1123 pixels), NOT a 16:9 presentation PAGE.
The template is optimized for A4 portrait format with print-quality layouts.
{_sb_section}
{slot_format}

OUTPUT FORMAT: {example_json}

{mode_rules}

BACKGROUND IMAGE: If the page has a background image, you will see "background_image" in current slots with its imageDescription.
To update it (e.g., when content changes significantly), include "background_image": {{"imageDescription": "new description matching updated content"}} in your response.
To keep it unchanged, simply omit "background_image" from your response."""

    # Build goal context section
    goal_section = ""
    if request.printable_goal:
        goal_section = f"""OVERALL DOCUMENT GOAL (for context only):
{request.printable_goal}

NOTE: The above is the overall document goal. Your current task is to edit THIS SPECIFIC PAGE only based on the instruction below.

"""

    # Build vault tool nudge based on mode (replaces the old vault_context block)
    vault_section = ""
    if _enhance_use_personal:
        if request.is_update_all:
            vault_section = (
                f"\n\nDATA TOOL: `personal_data_tool` is available "
                f"(scoped to {len(request.folder_ids)} folder(s)). Call it with a focused "
                f"query for THIS page's topic, fetch the LATEST data, then compare "
                f"against the current content and update ONLY parts that differ or are "
                f"outdated. Keep everything else verbatim. Cite vault facts with "
                f"[vault:<doc_id>]."
            )
        else:
            vault_section = (
                f"\n\nDATA TOOL: `personal_data_tool` is available "
                f"(scoped to {len(request.folder_ids)} folder(s)). Call it for relevant "
                f"facts to support the edit. Cite vault facts with [vault:<doc_id>]."
            )

    user_prompt = f"""{goal_section}PAGE TITLE: {request.PAGE_content.get('title', 'Untitled')}
TEMPLATE: {template_id} (A4 format)

CURRENT PAGE (all elements):
{json.dumps(request.PAGE_content, indent=2)}

INSTRUCTION: {request.instruction}
{vault_section}
{structured_data_context}

Return JSON with slot content updates only (not full elements):"""

    try:
        if _enhance_use_personal:
            from services.enterprise_tools import run_Enterprise_or_Personal_tool
            ai_response = await run_Enterprise_or_Personal_tool(
                prompt=user_prompt,
                system=system_prompt + "\n\n" + COMPUTE_FACT_ROUTING_RULE,
                user_id=user_id,
                tier="large",
                temperature=0.2,
                max_tokens=8000,
                filter_tools="auto",
                use_personal_data=True,
                selected_folder_ids=request.folder_ids,
                max_results_cap=3,  # enhance-PAGE: max 3 chunks per call
                expose_enterprise_tools=False,
                personal_tool_expand_subqueries=False,
                extra_tools=[build_compute_fact_tool_schema()],
                extra_tool_dispatch=make_compute_fact_dispatcher(
                    user_id=user_id, folder_ids=request.folder_ids,
                    log_prefix="PRINTABLE-ENHANCE-FACT",
                ),
            )
        else:
            ai_response = await asyncio.to_thread(
                llm_call,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                user_id=user_id,
                max_tokens=8000,
                temperature=0.2,
                top_p=0.95,
                tier="large",
            )
        
        logger.info(f"✨ [printable] Template AI response received: {repr(ai_response)}")
        
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
        
        # MERGE: Fill missing slots from existing page content so edits preserve unchanged elements
        # current_slots was extracted above from request.PAGE_content — use it as the baseline
        merged_slots = dict(current_slots)  # Start with existing content
        for slot_name, slot_value in updated_slots.items():
            if slot_value:  # Only override with non-empty AI content
                merged_slots[slot_name] = slot_value
        
        logger.info(f"✨ [printable] Slot merge: {len(current_slots)} existing + {len(updated_slots)} AI updates → {len(merged_slots)} merged")
        
        # Build final elements from template + merged content + style
        elements = build_elements_from_template(template, merged_slots, request.style or {})
        
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
        styled = apply_style_to_template(template, request.style or {})
        if ai_background_color:
            background_color = ai_background_color
            logger.info(f"✨ [printable] Using AI-specified backgroundColor: {ai_background_color}")
        else:
            background_color = styled.get("backgroundColor", request.style.get("PAGEBackground", "#ffffff") if request.style else "#ffffff")
        
        enhanced_PAGE = {
            "template": template_id,
            "title": request.PAGE_content.get("title", ""),
            "elements": elements,
            "backgroundColor": background_color,
            "speaker_notes": ai_speaker_notes if ai_speaker_notes is not None else request.PAGE_content.get("speaker_notes", "")
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
                    "width": 794,
                    "height": 1123,
                    "zIndex": 0,
                    "opacity": ai_background_image.get("opacity", 0.3),
                    "generationQuality": getattr(request, "generation_quality", "premium"),
                }
                enhanced_PAGE["elements"].insert(0, bg_element)
        else:
            # Preserve original background image from the page if AI didn't provide a new one
            # build_elements_from_template only rebuilds template slots, so bg images are lost
            for orig_el in request.PAGE_content.get("elements", []):
                if orig_el.get("type") == "image_placeholder" and orig_el.get("imageType") == "background":
                    enhanced_PAGE["elements"].insert(0, orig_el)
                    break
        
        logger.info(f"✨ [printable] Template PAGE enhanced with {len(elements)} elements")

        # Resolve _data_request placeholders against the user's structured files.
        if DATA_FILLER_AVAILABLE:
            try:
                fill_report = await fill_data_requests(
                    enhanced_PAGE,
                    user_id=user_id,
                    folder_ids=getattr(request, "folder_ids", None),
                    log_prefix="PRINTABLE-ENHANCE",
                )
                if fill_report.get("data_warnings"):
                    enhanced_PAGE["_data_warnings"] = fill_report["data_warnings"]
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"📊 [PRINTABLE-ENHANCE] data filler raised: {exc}")

        # AI-powered chart fix: detect malformed chartConfigs and ask AI to regenerate
        enhanced_PAGE = await _fix_malformed_charts_with_ai(enhanced_PAGE, user_id)
        
        # Fix numbered_step sequential numbering
        _fix_numbered_step_numbers(enhanced_PAGE.get("elements", []))

        # critique_recommended=True for every edit — see contract note in
        # generate_PAGE_with_template.
        return {"success": True, "enhanced_PAGE": enhanced_PAGE, "critique_recommended": True}
        
    except json.JSONDecodeError as e:
        logger.error(f"✨ [printable] JSON parse error in template enhancement: {e}")
        # Fall back to legacy enhancement
        return await enhance_PAGE_legacy(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"✨ [printable] Template enhancement failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def enhance_PAGE_legacy(request: EnhancePAGERequest, user_id: str):
    """Legacy A4 page enhancement — delegates to the unified orchestrator.

    Threads ``deck_plan`` so the edit stays coherent with the document's
    storyboard. ``critique_recommended`` is always True — vision critique
    runs after every edit (template + legacy) so post-edit defects are
    caught before the user sees them.
    """
    result = await _orchestrator_enhance_page_legacy(
        page_content=request.PAGE_content,
        instruction=request.instruction,
        user_id=user_id,
        canvas=PRINTABLE_CANVAS,
        style=request.style,
        folder_ids=request.folder_ids,
        skip_vault=request.skip_vault,
        goal=request.printable_goal,
        content_type=request.printable_type,
        icon_set=request.icon_set,
        deck_plan=getattr(request, "deck_plan", None),
    )
    if isinstance(result, dict) and result.get("success"):
        result.setdefault("critique_recommended", True)
    return result


# ==================== Legacy Classification (Fallback) ====================

async def _legacy_classify(request, user_id: str) -> tuple:
    """
    Fallback classification when parallel classifier is unavailable.
    Returns: (intent, ai_message, chart_type, chart_query, create_topic)
    
    Note: supplementary_sources selection has been removed. SaaS data is now
    pre-embedded in Milvus and retrieved via semantic search.
    """
    system_prompt = """You are an intent classifier for a printable editor AI assistant.
Classify the user's instruction into EXACTLY ONE category:
1. GREETING - Simple greetings, acknowledgments
2. HELP - Questions about capabilities
3. CREATE_NEW - Create a NEW PAGE
4. SIMPLE_EDIT - Layout/color/formatting changes (no vault needed)
5. DATA_ADDITION - Requires new information from vault
6. CHART_REQUEST - Visual data reprintable request
7. UPDATE_PAGE - Refresh/update existing content

Output format (JSON only):
{"intent": "...", "ai_message": "brief message", "create_topic": null, "chart_type": null, "chart_query": null}"""

    user_prompt = f"""Classify: "{request.instruction}"
PAGE elements: {[e.get('type', 'unknown') for e in request.PAGE_content.get('elements', [])]}"""

    try:
        ai_response = await asyncio.to_thread(
            llm_call,
            system_prompt=system_prompt, user_prompt=user_prompt,
            model=None, user_id=user_id, max_tokens=4096, temperature=0.2, top_p=0.95, json_mode=True,
            tier="large",
        )
        
        json_str = extract_json_from_response(ai_response)
        classification = json.loads(json_str)
        
        return (
            classification.get("intent", "simple_edit"),
            classification.get("ai_message", ""),
            classification.get("chart_type"),
            classification.get("chart_query") or request.instruction,
            classification.get("create_topic", "")
        )
    except Exception as e:
        logger.error(f"🎯 [LEGACY] Classification failed: {e}")
        return ("simple_edit", "", None, request.instruction, "")


# ==================== AI Orchestrator Endpoint ====================

@router.post("/printable/orchestrate")
async def orchestrate_request(request: Request, body: OrchestrateRequest):
    """AI Orchestrator (non-streaming). Profile-driven routing.

    general → legacy free-form generator + legacy enhance.
    corporate → template-matched generator + template-slot enhance.
    """
    user_id = get_secure_user_id(request)
    _profile = (getattr(body, 'deck_profile', None) or 'corporate').lower()
    _is_general = _profile in ('general', 'general_with_images')
    _effective_template_id = None if _is_general else (body.template_id or body.PAGE_content.get("template"))

    logger.info(f"🎯 [ORCHESTRATOR] Classifying: {body.instruction[:50]}... (profile={_profile})")

    async def _gen_page_fn(instruction, topic, goal, content_type, style, _user_id):
        if _is_general:
            PAGE_req = GeneratePAGERequest(
                PAGE_info={"title": topic or "New PAGE", "content_hint": instruction, "layout": "title_content"},
                PAGE_index=1, total_PAGES=10,
                printable_goal=goal or f"Create a page about {topic}",
                printable_type=content_type, style=style,
                template_id=None,
                deck_profile='general',
            )
            return await generate_PAGE_legacy(PAGE_req, _user_id)
        return await _generate_page_for_orchestrator(instruction, topic, goal, content_type, style, _user_id)

    return await orchestrate_edit(
        instruction=body.instruction,
        page_content=body.PAGE_content,
        user_id=user_id,
        canvas=PRINTABLE_CANVAS,
        page_id=body.PAGE_id,
        style=body.style,
        folder_ids=body.folder_ids,
        edit_mode=body.edit_mode,
        selected_elements=body.selected_elements,
        goal=body.printable_goal,
        content_type=body.printable_type,
        icon_set=body.icon_set,
        user_edit_scope=body.user_edit_scope,
        template_id=_effective_template_id,
        generate_page_fn=_gen_page_fn,
        enhance_page_with_template_fn=None if _is_general else _enhance_page_with_template_for_orchestrator,
        pages_summary=body.pages_summary,
        deck_plan=getattr(body, 'deck_plan', None),
    )


@router.post("/printable/orchestrate-stream")
async def orchestrate_stream(request: Request, body: OrchestrateRequest):
    """
    Streaming AI Orchestrator - Same as /orchestrate but streams results via SSE.
    Classification is instant, enhancement chunks stream progressively.
    """
    user_id = get_secure_user_id(request)

    # General profile bypasses the template path entirely.
    _profile = (getattr(body, 'deck_profile', None) or 'corporate').lower()
    _is_general = _profile in ('general', 'general_with_images')
    _effective_template_id = None if _is_general else (body.template_id or body.PAGE_content.get("template"))

    async def _gen_page_fn(instruction, topic, goal, content_type, style, _user_id):
        if _is_general:
            PAGE_req = GeneratePAGERequest(
                PAGE_info={"title": topic or "New PAGE", "content_hint": instruction, "layout": "title_content"},
                PAGE_index=1, total_PAGES=10,
                printable_goal=goal or f"Create a page about {topic}",
                printable_type=content_type, style=style,
                template_id=None,
                deck_profile='general',
            )
            return await generate_PAGE_legacy(PAGE_req, _user_id)
        return await _generate_page_for_orchestrator(instruction, topic, goal, content_type, style, _user_id)

    async def event_generator():
        async for event in orchestrate_edit_streaming(
            instruction=body.instruction,
            page_content=body.PAGE_content,
            user_id=user_id,
            canvas=PRINTABLE_CANVAS,
            page_id=body.PAGE_id,
            style=body.style,
            folder_ids=body.folder_ids,
            edit_mode=body.edit_mode,
            selected_elements=body.selected_elements,
            goal=body.printable_goal,
            content_type=body.printable_type,
            icon_set=body.icon_set,
            user_edit_scope=body.user_edit_scope,
            template_id=_effective_template_id,
            generate_page_fn=_gen_page_fn,
            enhance_page_with_template_fn=None if _is_general else _enhance_page_with_template_for_orchestrator,
            fast_path=body.fast_path,
            pages_summary=body.pages_summary,
            deck_plan=getattr(body, 'deck_plan', None),
        ):
            yield event

    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def _generate_page_for_orchestrator(instruction, topic, goal, content_type, style, user_id):
    """Bridge function to adapt orchestrator interface to printable page generation."""
    from .printable_templates import auto_match_template
    matched_template = auto_match_template(topic or "New PAGE", instruction, 1, 10)
    PAGE_req = GeneratePAGERequest(
        PAGE_info={"title": topic or "New PAGE", "content_hint": instruction, "layout": "title_content"},
        PAGE_index=1, total_PAGES=10,
        printable_goal=goal or f"Create a page about {topic}",
        printable_type=content_type,
        style=style,
        template_id=matched_template,
    )
    return await generate_PAGE_with_template(PAGE_req, user_id)


async def _enhance_page_with_template_for_orchestrator(
    page_content, instruction, user_id, canvas, style, folder_ids,
    skip_vault, goal, content_type, template_id, icon_set,
    is_update_all=False,
):
    """Bridge function to adapt orchestrator interface to template enhancement."""
    req = EnhancePAGERequest(
        PAGE_id="template_bridge",
        PAGE_content=page_content,
        instruction=instruction,
        style=style,
        folder_ids=folder_ids,
        skip_vault=skip_vault,
        template_id=template_id,
        printable_goal=goal,
        printable_type=content_type,
        icon_set=icon_set,
        is_update_all=is_update_all,
    )
    return await enhance_PAGE_with_template(req, user_id)


# ==================== Helper: Extract full text from page elements ====================

# _extract_page_full_text and _is_global_instruction moved to services/edit_orchestrator.py


# ==================== AI Orchestrate-All Endpoint (Smart Multi-Page) ====================

async def _generate_page_for_orchestrator_all(instruction, topic, goal, content_type, style, user_id):
    """Bridge: generate a new page for the all-pages orchestrator."""
    from .printable_templates import auto_match_template
    matched_template = auto_match_template(topic or "New PAGE", instruction, 1, 1)
    PAGE_req = GeneratePAGERequest(
        PAGE_info={"title": topic, "content_hint": instruction, "layout": "title_content"},
        PAGE_index=1, total_PAGES=1,
        printable_goal=goal or f"Create a page about {topic}",
        printable_type=content_type, style=style,
        template_id=matched_template,
    )
    return await generate_PAGE_with_template(PAGE_req, user_id)

@router.post("/printable/orchestrate-all")
async def orchestrate_all_pages(request: Request, body: OrchestrateAllRequest):
    """Smart All-Pages Orchestrator. Profile-driven (Edit-All / Update-All).

    general → every page goes through legacy free-form generator + legacy enhance.
    corporate → template-matched generator + template-slot enhance.
    """
    user_id = get_secure_user_id(request)

    _profile = (getattr(body, 'deck_profile', None) or 'corporate').lower()
    _is_general = _profile in ('general', 'general_with_images')
    if _is_general:
        for _p in (body.full_pages or []):
            if isinstance(_p, dict) and 'template' in _p:
                _p['template'] = None

    async def _gen_page_inner(instruction, topic, goal, content_type, style, _user_id):
        from .printable_templates import auto_match_template
        matched_template = None if _is_general else auto_match_template(
            topic or "New PAGE", instruction, 1, 1, deck_profile=_profile,
        )
        PAGE_req = GeneratePAGERequest(
            PAGE_info={"title": topic, "content_hint": instruction, "layout": "title_content"},
            PAGE_index=1, total_PAGES=1,
            printable_goal=goal or f"Create a page about {topic}",
            printable_type=content_type, style=style,
            template_id=matched_template,
            deck_profile=_profile,
        )
        if _is_general:
            return await generate_PAGE_legacy(PAGE_req, _user_id)
        return await generate_PAGE_with_template(PAGE_req, _user_id)

    return await orchestrate_all_edits(
        instruction=body.instruction,
        pages_summary=body.pages_summary,
        full_pages=body.full_pages,
        current_page_index=body.current_page_index,
        user_id=user_id,
        canvas=PRINTABLE_CANVAS,
        folder_ids=body.folder_ids,
        style=body.style,
        goal=body.printable_goal,
        content_type=body.printable_type or "informative",
        icon_set=body.icon_set or "lucide",
        generate_page_fn=_gen_page_inner,
        is_update_all=body.is_update_all,
        enhance_page_with_template_fn=None if _is_general else _enhance_page_with_template_for_orchestrator,
        deck_plan=getattr(body, 'deck_plan', None),
    )


@router.post("/printable/orchestrate-all-stream")
async def orchestrate_all_pages_stream(request: Request, body: OrchestrateAllRequest):
    """Streaming variant of orchestrate-all — yields per-page progress via SSE."""
    user_id = get_secure_user_id(request)

    from .printable_templates import auto_match_template as _page_auto_match

    _profile = (getattr(body, 'deck_profile', None) or 'corporate').lower()
    _is_general = _profile in ('general', 'general_with_images')
    if _is_general:
        # Strip stale template metadata so re-matching doesn't pull a
        # template into a general edit.
        for _p in (body.full_pages or []):
            if isinstance(_p, dict) and 'template' in _p:
                _p['template'] = None

    async def _gen_page_inner_stream(instruction, topic, goal, content_type, style, _user_id):
        matched_template = None if _is_general else _page_auto_match(topic or "New PAGE", instruction, 1, 1, deck_profile=_profile)
        PAGE_req = GeneratePAGERequest(
            PAGE_info={"title": topic, "content_hint": instruction, "layout": "title_content"},
            PAGE_index=1, total_PAGES=1,
            printable_goal=goal or f"Create a page about {topic}",
            printable_type=content_type, style=style,
            template_id=matched_template,
            deck_profile=_profile,
        )
        if _is_general:
            return await generate_PAGE_legacy(PAGE_req, _user_id)
        return await generate_PAGE_with_template(PAGE_req, _user_id)

    async def event_generator():
        async for event in orchestrate_all_edits_streaming(
            instruction=body.instruction,
            pages_summary=body.pages_summary,
            full_pages=body.full_pages,
            current_page_index=body.current_page_index,
            user_id=user_id,
            canvas=PRINTABLE_CANVAS,
            folder_ids=body.folder_ids,
            style=body.style,
            goal=body.printable_goal,
            content_type=body.printable_type or "informative",
            icon_set=body.icon_set or "lucide",
            generate_page_fn=_gen_page_inner_stream,
            is_update_all=body.is_update_all,
            enhance_page_with_template_fn=None if _is_general else _enhance_page_with_template_for_orchestrator,
            outline_changed=body.outline_changed,
            auto_match_template_fn=(None if _is_general else (_page_auto_match if body.outline_changed else None)),
            deck_plan=getattr(body, 'deck_plan', None),
        ):
            yield event

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ==================== Agentic Whole-Document Editor (Claude-on-PowerPoint) ====================

def _build_printable_deck_meta(body: "AgentEditRequest") -> Dict[str, Any]:
    return {
        "style": body.style or {},
        "header_footer": body.header_footer or {},
        "slide_numbers": body.slide_numbers or {},
        "goal": body.printable_goal or "",
        "presentation_type": body.printable_type,
    }


@router.post("/printable/agent-edit-stream")
async def printable_agent_edit_stream(request: Request, body: AgentEditRequest):
    """Agentic document edit (SSE). Sends the whole document + chat message; the
    LLM returns operations the frontend applies."""
    user_id = get_secure_user_id(request)
    user_email = getattr(request.state, "user_email", None)

    # OCR-first: pasted screenshots → text prepended to the instruction context.
    # Page media (image_placeholder markers) is untouched — this is a separate field.
    from services.ocr_context import prepend_ocr_to_instruction
    instruction = await prepend_ocr_to_instruction(
        body.instruction, body.image_attachments, user_id=user_id, user_email=user_email,
    )

    async def event_generator():
        async for event in agent_edit_deck_loop_streaming(
            instruction=instruction,
            slides=body.pages,
            user_id=user_id,
            canvas=PRINTABLE_CANVAS,
            current_index=body.current_page_index,
            deck_meta=_build_printable_deck_meta(body),
            chat_history=body.chat_history,
            folder_ids=body.folder_ids,
            selected_element_ids=body.selected_element_ids,
        ):
            yield event

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/printable/agent-edit")
async def printable_agent_edit(request: Request, body: AgentEditRequest):
    """Non-streaming agentic document edit. Returns {success, chat_message, operations}."""
    user_id = get_secure_user_id(request)
    return await agent_edit_deck(
        instruction=body.instruction,
        slides=body.pages,
        user_id=user_id,
        canvas=PRINTABLE_CANVAS,
        current_index=body.current_page_index,
        deck_meta=_build_printable_deck_meta(body),
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
    """Delegate to unified orchestrator for image element enhancement."""
    from services.edit_orchestrator import enhance_image_element as _orch_enhance_image
    return await _orch_enhance_image(
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
    page_content: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Delegate to unified orchestrator for single element enhancement (with page context)."""
    from services.edit_orchestrator import enhance_single_element as _orch_enhance_single
    return await _orch_enhance_single(
        element=element, instruction=instruction, user_id=user_id,
        canvas=PRINTABLE_CANVAS, style=style, folder_ids=folder_ids,
        skip_vault=skip_vault, page_content=page_content,
    )


async def enhance_multiple_elements(
    elements: List[Dict[str, Any]],
    instruction: str,
    user_id: str,
    style: Optional[Dict[str, Any]] = None,
    folder_ids: Optional[List[str]] = None,
    skip_vault: bool = True,
    page_content: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Delegate to unified orchestrator for multi-element enhancement (with page context)."""
    from services.edit_orchestrator import enhance_multiple_elements as _orch_enhance_multi
    return await _orch_enhance_multi(
        elements=elements, instruction=instruction, user_id=user_id,
        canvas=PRINTABLE_CANVAS, style=style, folder_ids=folder_ids,
        skip_vault=skip_vault, page_content=page_content,
    )


@router.post("/printable/generate-chart-data")
async def generate_chart_data_endpoint(request: Request, body: ChartDataRequest):
    """Generate Chart.js config — delegates to unified orchestrator."""
    user_id = get_secure_user_id(request)
    from services.edit_orchestrator import generate_chart_data as _orch_generate_chart
    return await _orch_generate_chart(
        chart_type=body.chart_type,
        query=body.query,
        user_id=user_id,
        folder_ids=body.folder_ids,
        page_context=body.page_context,
        source_context=body.source_context,
    )


# ==================== Persistence Endpoints ====================

@router.post("/printable/save")
async def save_printable(http_request: Request, body: SaveprintableRequest):
    """
    Save printable to MongoDB.
    
    SECURITY: Uses authenticated user_id from JWT token (via middleware).
    The user_id in the request body is ignored for security.
    
    Args:
        http_request: FastAPI request (contains JWT auth)
        body: Printable data to save
    """
    # SECURITY: Get authenticated user_id from JWT token (set by middleware)
    authenticated_user_id = get_secure_user_id(http_request)

    logger.info(f"💾 [printable] Saving printable: {body.title} | ID: {body.id if body.id else 'NEW'} for user: {authenticated_user_id}")

    # Personal-SA ownership stamp (see presentation_api.py for rationale).
    _personal_sa_id = getattr(http_request.state, "personal_sa_id", "") or ""
    _owner_org_id = getattr(http_request.state, "org_id", "") or ""
    if not _personal_sa_id:
        logger.warning(
            "[printable] reject: personal_sa_id missing for user=%s org=%s",
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
        logger.error("❌ [printable] Database connection unavailable during save")
        raise HTTPException(status_code=500, detail="Database not available")
    
    try:
        # Pydantic validation passed, now analyze payload
        PAGE_count = len(body.PAGES)
        total_elements = sum(len(s.get('elements', [])) for s in body.PAGES)
        
        logger.info(f"💾 [printable] Payload Analysis: {PAGE_count} PAGES, {total_elements} total elements")
        
        if PAGE_count == 0:
            logger.warning(f"⚠️ [printable] Saving printable '{body.title}' with 0 PAGES!")

        collection = db["printables"]
        
        # Prepare ID for S3 processing
        if body.id:
            printable_id = body.id
            is_new = False
        else:
            printable_id = f"pres_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
            is_new = True

        # Process thumbnail if provided (base64 -> S3) - Use authenticated user
        thumbnail_url = None
        if body.thumbnail:
            try:
                if body.thumbnail.startswith('data:image'):
                    thumbnail_url = image_processor.upload_base64_image(
                        body.thumbnail,
                        authenticated_user_id,  # SECURITY: Use authenticated user
                        "printables",
                        f"{printable_id}_thumbnail"
                    )
                    logger.info(f"🖼️ [printable] Thumbnail uploaded to S3: {thumbnail_url}")
                elif body.thumbnail.startswith('http'):
                    thumbnail_url = body.thumbnail
            except Exception as thumb_err:
                logger.warning(f"⚠️ [printable] Thumbnail processing failed: {thumb_err}")

        # Process images (Extract Base64 -> S3) - Use authenticated user
        updated_PAGES, active_keys = await image_processor.process_printable_PAGES(
            body.PAGES,
            authenticated_user_id,  # SECURITY: Use authenticated user
            printable_id
        )

        # Garbage Collect unused images - Use authenticated user
        image_processor.garbage_collect(authenticated_user_id, "printables", printable_id, active_keys)

        printable_data = {
            "title": body.title,
            "goal": body.goal,
            "style": body.style,
            "type": body.printable_type,
            "PAGES": updated_PAGES,
            "user_id": authenticated_user_id,  # SECURITY: Use authenticated user from JWT
            "team_id": body.team_id,
            "owner_type": "service_account",
            "owner_id": _personal_sa_id,
            "org_id": _owner_org_id or None,
            "thumbnail": thumbnail_url,
            "folder_id": body.folder_id,
            "updated_at": datetime.utcnow()
        }
        
        if not is_new:
            # Update existing - SECURITY: Ensure user owns the printable or has write access
            result = collection.update_one(
                {"_id": body.id, "user_id": authenticated_user_id},
                {"$set": printable_data}
            )
            if result.matched_count == 0:
                # Check if user has shared write access via centralized permissions
                try:
                    from services.authorization_service import get_authorization_service
                    auth_service = get_authorization_service()
                    access_result = await auth_service.check_access(
                        user_id=authenticated_user_id,
                        resource_id=body.id,
                        resource_type="printable",
                        required_permission="write"
                    )
                    if access_result.get("allowed"):
                        # User has write access - update without user_id filter but preserve original owner
                        existing = collection.find_one({"_id": body.id})
                        if existing:
                            printable_data["user_id"] = existing["user_id"]  # Preserve original owner
                            result = collection.update_one(
                                {"_id": body.id},
                                {"$set": printable_data}
                            )
                            if result.matched_count > 0:
                                logger.info(f"💾 [printable] Updated shared printable: {body.id} by collaborator {authenticated_user_id}")
                            else:
                                raise HTTPException(status_code=404, detail="Printable not found")
                        else:
                            raise HTTPException(status_code=404, detail="Printable not found")
                    else:
                        logger.warning(f"⚠️ [printable] Update failed: printable {body.id} not found for user {authenticated_user_id}")
                        raise HTTPException(status_code=404, detail="Printable not found or access denied")
                except HTTPException:
                    raise
                except Exception as auth_err:
                    logger.warning(f"⚠️ [printable] Auth check failed during save: {auth_err}")
                    raise HTTPException(status_code=404, detail="Printable not found or access denied")
            else:
                logger.info(f"💾 [printable] Updated existing printable: {body.id}")
        else:
            # Create new
            printable_data["created_at"] = datetime.utcnow()
            printable_data["_id"] = printable_id
            result = collection.insert_one(printable_data)
            logger.info(f"💾 [printable] Created new printable: {printable_id}")
        
        # Return pages with presigned URLs so frontend can update its local state
        # This prevents re-uploading all images/icons on subsequent saves
        response_pages = copy.deepcopy(updated_PAGES)
        response_pages = image_processor.inject_presigned_urls_printable(response_pages)
        
        return {"success": True, "id": printable_id, "pages": response_pages}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💾 [printable] Save failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/printable/load/{printable_id}")
async def load_printable(printable_id: str, request: Request, user_id: str = None):
    """
    Load printable from MongoDB.
    
    SECURITY: Validates that the authenticated user owns the printable or has shared access.
    
    Args:
        printable_id: printable ID
        request: FastAPI request (contains JWT auth)
        user_id: DEPRECATED - User ID (ignored, uses JWT instead for security)
        
    Returns:
        Printable data with sharing metadata for collaboration access control:
        - sharing.is_shared_for_collaboration: True if document has any collaboration shares
        - sharing.user_permission: 'owner' | 'write' | 'read' | null
        - sharing.is_owner: True if current user owns the printable
        
    Raises:
        HTTPException 403: If user doesn't own or have shared access to the printable
        HTTPException 404: If printable not found
    """
    # SECURITY: Get authenticated user_id from JWT token
    authenticated_user_id = get_secure_user_id(request)
    
    logger.info(f"📂 [printable] Loading: {printable_id} for authenticated user: {authenticated_user_id}")
    
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    
    try:
        collection = db["printables"]
        shared_collection = db["shared_with_me"]
        
        # First, find the printable
        printable = collection.find_one({"_id": printable_id})
        
        if not printable:
            logger.warning(f"⚠️ [printable] Load failed: printable {printable_id} not found")
            raise HTTPException(status_code=404, detail="printable not found")
        
        # SECURITY: Verify ownership or shared access
        printable_owner = printable.get("user_id")
        
        # Check if user owns the printable
        is_owner = (printable_owner == authenticated_user_id)
        
        # Check if printable is shared with user and get permission level
        is_shared = False
        user_permission = None
        shared_entry = None
        
        if not is_owner:
            # Check legacy shared_with_me collection
            shared_entry = shared_collection.find_one({
                "user_id": authenticated_user_id,
                "source_id": printable_id,
                "content_type": "printable"
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
                        resource_id=printable_id,
                        resource_type="printable",
                        required_permission="read"
                    )
                    if access_result.get("allowed"):
                        is_shared = True
                        user_permission = access_result.get("permission", "read")
                except Exception as auth_e:
                    logger.warning(f"⚠️ [printable] Auth service check failed: {auth_e}")
        
        if not is_owner and not is_shared:
            logger.warning(f"🔒 Access denied: User {authenticated_user_id} tried to access printable {printable_id} owned by {printable_owner}")
            raise HTTPException(
                status_code=403, 
                detail="Access denied. You don't have permission to view this printable."
            )
        
        # Convert ObjectId to string if needed
        printable["id"] = str(printable.pop("_id"))
        
        # Check if document has any collaboration shares (to determine if collaboration should be enabled)
        is_shared_for_collaboration = False
        if is_owner:
            # Check if owner has shared with anyone for collaboration
            try:
                from services.authorization_service import get_authorization_service
                auth_service = get_authorization_service()
                perm_record = await auth_service.db.resource_permissions.find_one({
                    "resource_id": printable_id,
                    "resource_type": "printable"
                })
                if perm_record:
                    shared_with = perm_record.get("shared_with", [])
                    shared_with_teams = perm_record.get("shared_with_teams", [])
                    is_shared_for_collaboration = len(shared_with) > 0 or len(shared_with_teams) > 0
            except Exception as e:
                logger.warning(f"⚠️ [printable] Could not check collaboration shares: {e}")
                # Also check legacy collection
                legacy_shares = list(shared_collection.find({
                    "source_id": printable_id,
                    "content_type": "printable"
                }).limit(1))
                is_shared_for_collaboration = len(legacy_shares) > 0
        else:
            # Non-owner accessing = document IS shared for collaboration
            is_shared_for_collaboration = True
        
        # Add sharing metadata for frontend collaboration access control
        printable["sharing"] = {
            "is_shared_for_collaboration": is_shared_for_collaboration,
            "user_permission": "owner" if is_owner else user_permission,
            "is_owner": is_owner
        }
        
        # Inject Presigned URLs for secure viewing
        PAGE_count = 0
        if "PAGES" in printable:
            PAGE_count = len(printable["PAGES"])
            printable["PAGES"] = image_processor.inject_presigned_urls_printable(printable["PAGES"])
        else:
            logger.warning(f"⚠️ [printable] Loaded printable {printable_id} has NO 'PAGES' key")

        logger.info(f"📂 [printable] Loaded successfully: {printable_id} ({PAGE_count} PAGES, collab={is_shared_for_collaboration}, perm={printable['sharing']['user_permission']})")
        return {"success": True, "printable": printable}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"📂 [printable] Load CRITICAL failure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/printable/list")
async def list_printables(request: Request, user_id: str = None, team_id: str = None, all_workspaces: bool = False, skip: int = 0, limit: int = 20):
    """
    List user's printables or team printables, including those shared with them.
    
    SECURITY: Uses authenticated user_id from JWT token, ignores user_id query param.
    
    Args:
        request: FastAPI request (contains JWT auth)
        user_id: DEPRECATED - User identifier (ignored, uses JWT instead)
        team_id: Optional team ID. If provided, lists team printables. If None, lists personal.
        all_workspaces: If true, return user's printables across all workspaces
        skip: Pagination offset
        limit: Max results to return
    """
    # SECURITY: Get authenticated user_id from JWT token (ignores query param)
    authenticated_user_id = get_secure_user_id(request)
    
    logger.info(f"📋 [printable] Listing printables for authenticated user: {authenticated_user_id}, team: {team_id}, all_workspaces: {all_workspaces}")
    
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    
    try:
        collection = db["printables"]
        shared_collection = db["shared_with_me"]
        
        # Build query based on team context
        if all_workspaces:
            # User-level: all printables across all workspaces
            match_query = {"user_id": authenticated_user_id}
        elif team_id:
            # Team workspace: show all team printables for authenticated user
            match_query = {"team_id": team_id, "user_id": authenticated_user_id}
        else:
            # Personal workspace: show user's personal printables (no team_id)
            match_query = {
                "user_id": authenticated_user_id,
                "$or": [
                    {"team_id": {"$exists": False}},
                    {"team_id": None}
                ]
            }
        
        # 1. Get User's Own printables (or team printables)
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
                "PAGE_count": {"$size": {"$ifNull": ["$PAGES", []]}}
            }}
        ]
        
        own_printables = list(collection.aggregate(pipeline))
        own_count = collection.count_documents(match_query)

        # 2. Get Shared printables (only for personal workspace)
        # Note: Pagination here is tricky if we want to mix them seamlessly.
        # For MVP, we append shared items to the start or end, or just fetch all shared (usually few).
        # Let's fetch all shared items for now.
        shared_printables = []
        if not team_id or all_workspaces:
            # SECURITY: Get shared printables for authenticated user
            # Method 1: Legacy shared_with_me collection
            shared_entries = list(shared_collection.find({
                "user_id": authenticated_user_id,
                "content_type": "printable"
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
                        "PAGES": 1 # To count
                    }
                ))
            
            # Map back to add shared metadata
            doc_map = {str(doc["_id"]): doc for doc in shared_docs}
            
            for entry in shared_entries:
                sid = entry["source_id"]
                if sid in doc_map:
                    doc = doc_map[sid]
                    PAGES = doc.get("PAGES", [])
                    
                    # Generate presigned URL for thumbnail
                    thumbnail_url = doc.get("thumbnail")
                    if thumbnail_url and thumbnail_url.startswith("s3://"):
                        try:
                            thumbnail_url = image_processor.generate_presigned_url(thumbnail_url)
                        except Exception:
                            thumbnail_url = None

                    shared_printables.append({
                        "id": str(doc["_id"]),
                        "title": doc.get("title", "Untitled"),
                        "goal": doc.get("goal"),
                        "style": doc.get("style"),
                        "PAGE_count": len(PAGES),
                        "created_at": doc.get("created_at"),
                        "updated_at": doc.get("updated_at"),
                        "thumbnail": thumbnail_url,
                        "isShared": True,
                        "sharedBy": entry.get("owner_id"),
                        "permission": entry.get("permission", "read")
                    })
            
            # Method 2: Also check authorization service for shared printables
            try:
                from services.authorization_service import get_authorization_service
                auth_service = get_authorization_service()
                
                accessible_result = await auth_service.get_accessible_resources(
                    user_id=authenticated_user_id,
                    resource_type="printable",
                    team_id=None
                )
                
                if accessible_result.get("success"):
                    # Get shared resource IDs (not owned by user, not already in shared_printables)
                    existing_shared_ids = {p["id"] for p in shared_printables}
                    auth_shared_ids = [
                        r["resource_id"] for r in accessible_result.get("shared_details", [])
                        if not r.get("is_owner", False) and r["resource_id"] not in existing_shared_ids
                    ]
                    
                    if auth_shared_ids:
                        # Fetch printable details for these
                        from bson import ObjectId
                        auth_shared_query = {"_id": {"$in": [ObjectId(sid) if ObjectId.is_valid(sid) else sid for sid in auth_shared_ids]}}
                        auth_shared_docs = list(collection.find(
                            auth_shared_query,
                            {"title": 1, "goal": 1, "style": 1, "created_at": 1, "updated_at": 1, "thumbnail": 1, "PAGES": 1, "user_id": 1}
                        ))
                        
                        for doc in auth_shared_docs:
                            PAGES = doc.get("PAGES", [])
                            thumbnail_url = doc.get("thumbnail")
                            if thumbnail_url and thumbnail_url.startswith("s3://"):
                                try:
                                    thumbnail_url = image_processor.generate_presigned_url(thumbnail_url)
                                except Exception:
                                    thumbnail_url = None
                            
                            shared_printables.append({
                                "id": str(doc["_id"]),
                                "title": doc.get("title", "Untitled"),
                                "goal": doc.get("goal"),
                                "style": doc.get("style"),
                                "PAGE_count": len(PAGES),
                                "created_at": doc.get("created_at"),
                                "updated_at": doc.get("updated_at"),
                                "thumbnail": thumbnail_url,
                                "isShared": True,
                                "sharedBy": doc.get("user_id"),
                                "permission": "read"
                            })
                        
                        logger.info(f"📤 [printable] Found {len(auth_shared_ids)} additional shared printables via auth service")
            except Exception as auth_e:
                logger.warning(f"⚠️ [printable] Could not check auth service for shared printables: {auth_e}")

        # Format Own printables
        result = []
        for pres in own_printables:
            thumbnail_url = pres.get("thumbnail")
            if thumbnail_url and thumbnail_url.startswith("s3://"):
                try:
                    thumbnail_url = image_processor.generate_presigned_url(thumbnail_url)
                except Exception as url_err:
                    logger.warning(f"⚠️ [printable] Failed to generate thumbnail URL: {url_err}")
                    thumbnail_url = None
            
            result.append({
                "id": str(pres.get("_id")),
                "title": pres.get("title", "Untitled"),
                "goal": pres.get("goal"),
                "style": pres.get("style"),
                "PAGE_count": pres.get("PAGE_count", 0),
                "created_at": pres.get("created_at"),
                "updated_at": pres.get("updated_at"),
                "thumbnail": thumbnail_url,
                "isShared": False
            })
        
        # Combine (Shared first, then Own)
        final_list = shared_printables + result
        
        return {
            "success": True,
            "printables": final_list,
            "total": own_count + len(shared_printables),
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"📋 [printable] List failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/printable/{printable_id}")
async def delete_printable(printable_id: str, request: Request, user_id: str = None):
    """
    Delete a printable.
    
    SECURITY: Only the owner can delete their printable.
    
    Args:
        printable_id: printable ID to delete
        request: FastAPI request (contains JWT auth)
        user_id: DEPRECATED - User ID (ignored, uses JWT instead)
        
    Raises:
        HTTPException 403: If user is not the printable owner
        HTTPException 404: If printable not found
    """
    # SECURITY: Get authenticated user_id from JWT token
    authenticated_user_id = get_secure_user_id(request)
    
    logger.info(f"🗑️ [printable] Deleting: {printable_id} by authenticated user: {authenticated_user_id}")
    
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    
    try:
        collection = db["printables"]
        
        # Delete S3 folder first using authenticated user
        image_processor.delete_document_folder(authenticated_user_id, "printables", printable_id)

        # SECURITY: Only delete if user owns the printable
        result = collection.delete_one({
            "_id": printable_id,
            "user_id": authenticated_user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="printable not found or access denied")
        
        logger.info(f"✅ [printable] Deleted: {printable_id} by {authenticated_user_id}")
        return {"success": True, "message": "printable deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"🗑️ [printable] Delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
