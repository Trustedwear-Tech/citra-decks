# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Unified Edit Orchestrator — Shared AI editing logic for Presentations & Printables.

Extracted from the duplicated ~4100-line presentation_api.py and printable_api.py.
Both API modules now delegate all edit operations to this shared module,
differing only in canvas dimensions and prompt phrasing.

Features:
- LLM native JSON mode for all AI calls
- Streaming support via SSE
- Page context injection for element editing
- Programmatic position validation
- Cross-page consistency enforcement in all-page mode
- Element type transformation support
- No layout/element restrictions — users can change anything
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
import logging
import os
import json
import asyncio
import re

from llm_oss import llm_call as _llm_call_base, llm_call_streaming as _llm_call_streaming_base

logger = logging.getLogger(__name__)

# This orchestrator is the shared edit engine for BOTH presentations and
# printables, which stay on GLM-5.1 even though the platform large tier now
# defaults to deepseek-v4-pro. Pin the large-tier model here (env-overridable
# via PRESENTATION_LLM_MODEL / PRINTABLE_LLM_MODEL); base_url/api_key still come
# from LLM_LARGE_*. All large-tier calls in this file go through these wrappers.
_SURFACE_LLM_MODEL = (
    os.getenv("PRESENTATION_LLM_MODEL", "").strip()
    or os.getenv("PRINTABLE_LLM_MODEL", "").strip()
    or "z-ai/glm-5.1"
)


def llm_call(*args, model=None, tier="large", **kwargs):
    if model is None and tier == "large":
        model = _SURFACE_LLM_MODEL or None
    return _llm_call_base(*args, model=model, tier=tier, **kwargs)


def llm_call_streaming(*args, model=None, tier="large", **kwargs):
    if model is None and tier == "large":
        model = _SURFACE_LLM_MODEL or None
    return _llm_call_streaming_base(*args, model=model, tier=tier, **kwargs)

# Structured data pipeline (schema preview + sandbox execution).
try:
    from services.structured_file_listing import list_structured_files, format_schema_preview_for_prompt
    from services.structured_sandbox import run_structured_sandbox
    STRUCTURED_DATA_AVAILABLE = True
except ImportError:
    STRUCTURED_DATA_AVAILABLE = False

try:
    from services.structured_prompt_builder import StructuredPromptBuilder
except ImportError:
    StructuredPromptBuilder = None


# ═══════════════════════════════════════════════════════════════════════════
# Canvas Configuration
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class CanvasConfig:
    """Canvas dimensions and format type for presentation vs printable."""
    width: int
    height: int
    format_label: str          # e.g. "A4 portrait" or "16:9 landscape"
    content_type: str          # "printable" or "presentation"
    safe_bottom: int = 0       # Max Y for element placement
    bg_key: str = ""           # Style key for background color
    goal_key: str = ""         # Request field for overall goal
    content_key: str = ""      # Request field for page content ("PAGE_content" or "slide_content")
    enhanced_key: str = ""     # Response key ("enhanced_PAGE" or "enhanced_slide")

    def __post_init__(self):
        if not self.safe_bottom:
            self.safe_bottom = self.height - 43


PRINTABLE_CANVAS = CanvasConfig(
    width=794, height=1123,
    format_label="A4 portrait",
    content_type="printable",
    bg_key="PAGEBackground",
    goal_key="printable_goal",
    content_key="PAGE_content",
    enhanced_key="enhanced_PAGE",
)

PRESENTATION_CANVAS = CanvasConfig(
    width=960, height=540,
    format_label="16:9 landscape",
    content_type="presentation",
    bg_key="slideBackground",
    goal_key="presentation_goal",
    content_key="slide_content",
    enhanced_key="enhanced_slide",
)


# ═══════════════════════════════════════════════════════════════════════════
# JSON Parsing Helpers (simplified with native JSON mode)
# ═══════════════════════════════════════════════════════════════════════════

def extract_json_from_response(text: str) -> str:
    """Extract JSON string from AI response. With json_mode=True this is usually
    a straight parse, but we keep a lightweight fallback for safety."""
    text = text.strip()

    # Fast path: already valid JSON
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{") or part.startswith("["):
                try:
                    json.loads(part)
                    return part
                except json.JSONDecodeError:
                    pass

    # Brace-balanced extraction
    start = text.find('{')
    if start == -1:
        start = text.find('[')
    if start != -1:
        open_char = text[start]
        close_char = '}' if open_char == '{' else ']'
        depth = 0
        for i in range(start, len(text)):
            if text[i] == open_char:
                depth += 1
            elif text[i] == close_char:
                depth -= 1
                if depth == 0:
                    candidate = text[start:i+1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        break

    # LAST RESORT: nothing parsed cleanly, but STILL strip decoration and return
    # the best JSON-looking slice (first '{'/'[' to the last '}'/']'). Returning
    # the raw fenced text made the downstream error "Expecting value: char 0"
    # (pointing at ```json) — useless for the parse-retry's self-correction.
    # Returning the stripped slice surfaces the REAL inner error (e.g. an
    # unescaped quote at char 612), which the retry feedback can actually fix.
    # Observed live: 2 of 3 parse attempts wasted on the fence, turn died.
    if start != -1:
        end = max(text.rfind('}'), text.rfind(']'))
        if end > start:
            return text[start:end + 1]

    return text


def _fix_numbered_step_numbers(elements: list):
    """Auto-assign sequential numbers to numbered_step elements."""
    step_counter = 0
    for elem in elements:
        etype = elem.get("type", "").lower() if isinstance(elem.get("type"), str) else ""
        if etype == "numbered_step":
            step_counter += 1
            if "index" in elem and "number" not in elem:
                elem["number"] = elem.pop("index")
            if "number" not in elem:
                elem["number"] = step_counter
        if isinstance(elem.get("children"), list):
            _fix_numbered_step_numbers(elem["children"])


# ═══════════════════════════════════════════════════════════════════════════
# Position Validation
# ═══════════════════════════════════════════════════════════════════════════

def validate_element_positions(
    elements: list,
    canvas: CanvasConfig,
    original_elements: Optional[list] = None,
    is_layout_change: bool = False
):
    """
    Programmatic position validation — clamp out-of-bounds elements,
    fix invalid dimensions, prevent unexpected relocation.
    Modifies elements in-place.
    """
    if not elements:
        return

    original_map = {}
    if original_elements:
        for el in original_elements:
            eid = el.get("id")
            if eid:
                original_map[eid] = el

    for elem in elements:
        eid = elem.get("id", "")

        # --- Clamp dimensions ---
        w = elem.get("width")
        h = elem.get("height")
        if w is not None and (not isinstance(w, (int, float)) or w <= 0):
            elem["width"] = 200
            logger.warning(f"🔧 [POS] Element '{eid}' invalid width={w}, reset to 200")
        if h is not None and (not isinstance(h, (int, float)) or h <= 0):
            elem["height"] = 100
            logger.warning(f"🔧 [POS] Element '{eid}' invalid height={h}, reset to 100")

        # --- Clamp position to canvas bounds ---
        x = elem.get("x")
        y = elem.get("y")
        if x is not None:
            if not isinstance(x, (int, float)):
                elem["x"] = 10
            elif x < -50:
                elem["x"] = 10
                logger.warning(f"🔧 [POS] Element '{eid}' x={x} out of bounds, clamped to 10")
            elif x > canvas.width:
                elem["x"] = canvas.width - 50
                logger.warning(f"🔧 [POS] Element '{eid}' x={x} exceeds canvas, clamped")
        if y is not None:
            if not isinstance(y, (int, float)):
                elem["y"] = 10
            elif y < -50:
                elem["y"] = 10
                logger.warning(f"🔧 [POS] Element '{eid}' y={y} out of bounds, clamped to 10")
            elif y > canvas.height + 50:
                elem["y"] = canvas.safe_bottom
                logger.warning(f"🔧 [POS] Element '{eid}' y={y} exceeds canvas, clamped")

        # --- Clamp element bottom edge to stay within canvas ---
        ex = elem.get("x", 0)
        ey = elem.get("y", 0)
        ew = elem.get("width")
        eh = elem.get("height")
        margin = 20
        
        # Skip margin clamping for background images — they should span the full canvas
        is_background = elem.get("imageType") == "background"
        
        if eh is not None and isinstance(ey, (int, float)) and isinstance(eh, (int, float)):
            if is_background:
                # Background images: allow full canvas coverage (0,0 to width,height)
                if ey + eh > canvas.height:
                    elem["y"] = 0
                    elem["height"] = round(canvas.height)
                if ey < 0:
                    elem["y"] = 0
            elif ey + eh > canvas.height - margin:
                # First try repositioning upward
                new_y = canvas.height - margin - eh
                if new_y >= margin:
                    elem["y"] = round(new_y)
                    logger.warning(f"🔧 [POS] Element '{eid}' bottom {ey+eh} exceeds canvas {canvas.height}, moved y to {new_y}")
                else:
                    # Element is too tall — shrink height to fit
                    elem["y"] = margin
                    elem["height"] = round(canvas.height - 2 * margin)
                    logger.warning(f"🔧 [POS] Element '{eid}' too tall ({eh}), shrunk to fit canvas")
        if ew is not None and isinstance(ex, (int, float)) and isinstance(ew, (int, float)):
            if is_background:
                # Background images: allow full canvas width
                if ex + ew > canvas.width:
                    elem["x"] = 0
                    elem["width"] = round(canvas.width)
                if ex < 0:
                    elem["x"] = 0
            elif ex + ew > canvas.width - margin:
                new_x = canvas.width - margin - ew
                if new_x >= margin:
                    elem["x"] = round(new_x)
                    logger.warning(f"🔧 [POS] Element '{eid}' right edge {ex+ew} exceeds canvas {canvas.width}, moved x to {new_x}")
                else:
                    elem["x"] = margin
                    elem["width"] = round(canvas.width - 2 * margin)
                    logger.warning(f"🔧 [POS] Element '{eid}' too wide ({ew}), shrunk to fit canvas")

        # --- Prevent unexpected relocation (only for existing elements, not layout changes) ---
        if not is_layout_change and eid in original_map:
            orig = original_map[eid]
            ox, oy = orig.get("x", 0), orig.get("y", 0)
            cx, cy = elem.get("x", ox), elem.get("y", oy)
            threshold = canvas.width * 0.5
            if abs(cx - ox) > threshold or abs(cy - oy) > threshold:
                elem["x"] = ox
                elem["y"] = oy
                logger.warning(f"🔧 [POS] Element '{eid}' relocated too far ({ox},{oy})→({cx},{cy}), restored original position")

        # Recurse children
        if isinstance(elem.get("children"), list):
            # Children use relative coords — skip canvas-level validation for them
            pass


# ═══════════════════════════════════════════════════════════════════════════
# Page Context Builder (for element editing)
# ═══════════════════════════════════════════════════════════════════════════

def build_page_context_summary(page_content: Dict[str, Any], exclude_ids: Optional[List[str]] = None, max_chars: int = 500) -> str:
    """Build a compressed summary of all elements on the page for context injection."""
    elements = page_content.get("elements", [])
    if not elements:
        return ""

    exclude = set(exclude_ids or [])
    parts = []
    for el in elements:
        eid = el.get("id", "")
        if eid in exclude:
            continue
        etype = el.get("type", "unknown")
        x, y = el.get("x", 0), el.get("y", 0)
        w, h = el.get("width", 0), el.get("height", 0)
        brief = ""
        if etype == "text":
            brief = (el.get("content", "") or "")[:40]
            fs = el.get("fontSize", "")
            brief = f'"{brief}" [fs={fs}]' if fs else f'"{brief}"'
        elif etype in ("image", "image_placeholder"):
            brief = el.get("imageDescription", "image")[:30]
        elif etype == "card":
            brief = el.get("title", "card")[:30]
        elif etype == "chart":
            cfg = el.get("chartConfig", {})
            brief = cfg.get("type", "chart")
        elif etype == "icon":
            brief = el.get("iconName", "icon")
        elif etype == "shape":
            brief = el.get("shapeType", "shape")
        parts.append(f"- {etype} at ({x},{y},{w}x{h}): {brief}")

    result = "\n".join(parts)
    return result[:max_chars] if len(result) > max_chars else result


# ═══════════════════════════════════════════════════════════════════════════
# Vault Context Retrieval
# ═══════════════════════════════════════════════════════════════════════════

async def retrieve_vault_context(user_id: str, query: str, folder_ids: list = None, top_k: int = 2) -> str:
    """Retrieve relevant context from user's vault (personal docs only, no SaaS)."""
    try:
        from composer_query import retrieve_vault_context as shared_retrieve
        return await shared_retrieve(user_id=user_id, query=query, folder_ids=folder_ids, top_k=top_k, use_saas=False)
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"🔍 [VAULT] Shared vault retrieval failed: {e}")
        return ""

    try:
        from llamaindex_query_engine import UnifiedQueryEngine
        engine = UnifiedQueryEngine()
        contexts = await engine.retrieve_personal_context(
            query=query, user_id=user_id,
            selected_folder_ids=folder_ids,
            folder_search_enabled=bool(folder_ids),
            top_k=top_k
        )
        if not contexts:
            return ""
        return _format_contexts(contexts)
    except Exception as e:
        logger.warning(f"🔍 [VAULT] Vault retrieval failed: {e}")
        return ""


def _format_contexts(contexts: list) -> str:
    """Flatten and group context chunks by source document."""
    grouped = {}
    for ctx in contexts:
        if isinstance(ctx, dict):
            text = ctx.get('text', ctx.get('content', '')).strip()
            source = ctx.get('topic', ctx.get('filename', 'Document'))
        else:
            text = str(ctx).strip()
            source = "Document"
        if not text:
            continue
        grouped.setdefault(source, []).append(text)

    parts = []
    for source, texts in grouped.items():
        parts.append(f"[Document: {source}]\n" + "\n(...)\n".join(texts))
    return "\n\n---\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Structured Data Retrieval (for charts)
# ═══════════════════════════════════════════════════════════════════════════

async def get_structured_data_context(user_id: str, instruction: str, page_title: str, folder_ids: list) -> str:
    """Return a schema-preview snippet for chart-oriented edits.

    Per-row data is no longer fetched at this stage — the LLM is shown
    column metadata + sample values, and any row-level computation is
    expected to flow through the sandbox path (``run_structured_sandbox``).
    """
    if not STRUCTURED_DATA_AVAILABLE or not folder_ids:
        return ""
    try:
        listing = await list_structured_files(user_id, folder_ids=folder_ids)
        entries = listing.get("entries", [])
        if not entries:
            return ""
        preview = format_schema_preview_for_prompt(entries, truncated_files=listing.get("truncated_files"))
        return (
            "\n\nSTRUCTURED DATA AVAILABLE FOR CHARTS (schema only — "
            "compute exact numbers via the sandbox/composer endpoints):\n"
            f"{preview}"
        )
    except Exception as e:
        logger.warning(f"📊 [STRUCT] Structured data preview failed: {e}")
    return ""


# ═══════════════════════════════════════════════════════════════════════════
# Build Vault Query from Page Content
# ═══════════════════════════════════════════════════════════════════════════

def build_vault_query(instruction: str, page_content: Dict[str, Any]) -> str:
    """Build optimized vault query combining instruction + page context."""
    parts = []
    title = page_content.get('title', '')
    if title:
        parts.append(f"Page: {title}")

    elements = page_content.get('elements', [])

    # Chart titles
    for el in elements:
        if el.get('type') == 'chart':
            chart_title = el.get('chartConfig', {}).get('options', {}).get('plugins', {}).get('title', {}).get('text')
            if chart_title:
                if isinstance(chart_title, list):
                    chart_title = " ".join(chart_title)
                parts.append(f"Chart: {chart_title}")

    # Top text elements by font size
    text_els = [el for el in elements if el.get('type') == 'text' and el.get('content')]
    text_els.sort(key=lambda x: x.get('fontSize', 0), reverse=True)
    for el in text_els[:4]:
        parts.append(el.get('content')[:150])

    context = ". ".join(parts)[:800]
    return f"{instruction}. Current page content: {context}" if context else instruction


# ═══════════════════════════════════════════════════════════════════════════
# Extract Full Text from Page
# ═══════════════════════════════════════════════════════════════════════════

def extract_page_full_text(page: Dict[str, Any], max_len: int = 1200) -> str:
    """Extract ALL searchable text from a page for relevance matching."""
    parts = []
    for key in ('title', 'subtitle', 'outline', 'notes'):
        if page.get(key):
            parts.append(str(page[key]))
    for el in page.get('elements', []):
        for key in ('text', 'content', 'label', 'caption', 'heading', 'subheading'):
            if el.get(key):
                parts.append(str(el[key]))
        for item in el.get('items', []):
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                for k in ('text', 'title'):
                    if item.get(k):
                        parts.append(item[k])
        for card in el.get('cards', []):
            for k in ('title', 'description'):
                if card.get(k):
                    parts.append(card[k])
    text = ' '.join(parts)
    return text[:max_len] if len(text) > max_len else text


# ═══════════════════════════════════════════════════════════════════════════
# System Prompts
# ═══════════════════════════════════════════════════════════════════════════

def build_enhance_system_prompt(canvas: CanvasConfig, is_update_all: bool = False) -> str:
    """Build the system prompt for legacy page enhancement.
    No layout/element restrictions — users can change anything.
    When is_update_all=True, includes aggressive image description refresh instructions."""

    preamble = ""
    if canvas.content_type == "printable":
        preamble = f"""A4 Document Editor. Canvas: {canvas.width}x{canvas.height} pixels ({canvas.format_label}). No overlaps.

IMPORTANT: This is an A4 DOCUMENT/REPORT page, NOT a 16:9 presentation.
Design for vertical reading and print-quality layouts.
BOUNDS (MANDATORY): x ≥ 20, y ≥ 20, x+width ≤ {canvas.width - 40}, y+height ≤ {canvas.height - 40}. NOTHING may exceed these limits.
OVERLAP RULE: Every element (including images, cards, text, shapes) has a bounding box (x,y,width,height). No two bounding boxes may intersect. Maintain at least 10px gap between all elements. Do NOT layer text or cards on top of images.
PRIORITY: bounds compliance > no overlaps > readability > content preservation. If content cannot fit, reduce font sizes (min 12px), condense text, or remove least-important elements.
TEXT HEIGHT: Before positioning, compute rendered height = ceil(char_count / floor(width / (fontSize*0.55))) × fontSize × lineHeight. Place next element at y + rendered_height + gap."""
    else:
        preamble = f"""Presentation editor. Canvas: {canvas.width}x{canvas.height} ({canvas.format_label}). No overlaps.
BOUNDS (MANDATORY): x ≥ 20, y ≥ 20, x+width ≤ {canvas.width - 40}, y+height ≤ {canvas.height - 20}. NOTHING may exceed these limits.
OVERLAP RULE: Every element (including images, cards, text, shapes) has a bounding box (x,y,width,height). No two bounding boxes may intersect. Maintain at least 8px gap between all elements. Do NOT layer text or cards on top of images.
PRIORITY: bounds compliance > no overlaps > readability > content preservation. If content cannot fit, reduce font sizes (min 12px), condense text, or remove least-important elements.
TEXT HEIGHT: Before positioning, compute rendered height = ceil(char_count / floor(width / (fontSize*0.55))) × fontSize × lineHeight. Place next element at y + rendered_height + gap."""

    # VAULT-CONTEXT UPDATE MODE — only for Update All flow
    if is_update_all:
        data_freshness_section = """VAULT-CONTEXT UPDATE MODE (when vault/reference data is provided):
- The user has uploaded files in their vault. Your job is to COMPARE the current page content against the vault data and make PRECISE changes.
- PRECISION PRINCIPLE: Change exactly what the data demands — no more, no less.
  • If only numbers/statistics changed → update those numbers, keep everything else intact.
  • If the narrative or key message shifted → rewrite the affected sections to reflect the new story, but keep unaffected sections stable.
  • If the data tells a completely different story that makes the entire page obsolete → fully rewrite the page around the new data.
- COMPARE CAREFULLY: Read the existing page content, then read the vault data. Identify WHAT specifically changed and edit ONLY those parts unless a broader rewrite is warranted by the scope of changes.
- KEEP STABLE: Layout, structure, formatting, and visual design should remain unchanged UNLESS the content changes are so significant that the existing structure no longer serves the data.
- IMAGE DESCRIPTIONS: Update 'imageDescription' of image_placeholder elements ONLY if the content change makes the current image irrelevant. If the image still fits the updated content, keep it.
- The only things to preserve unconditionally: user-uploaded media (isUserMedia: true) and video elements. These are ALWAYS immutable.

"""
        chart_preserve_line = "- When vault data contains newer numbers/statistics, update chart data accordingly. You can also change chart type if the new data is better suited to a different visualization."
    else:
        data_freshness_section = ""
        chart_preserve_line = "- PRESERVE chart type/options/colors if possible."

    return f"""{preamble}

RULES:
1. LAYOUT FLEXIBILITY: You CAN freely change layout, rearrange elements, add/remove elements, and restructure the page when the user requests it. Create entirely new layouts when asked. You CAN change element types (e.g., text → cards, bullet list → timeline, table → chart). Preserve layout only if the user's instruction is about content/text changes, not structural.
2. Never use placeholder text like "Title", "Lorem ipsum", or generic filler. When changing content, use real, specific, meaningful text. When the instruction does not ask to change content, keep the existing text.
3. Keep element IDs for existing elements that are being preserved. New elements get new IDs.
4. USE STYLE COLORS for new elements (titleColor, bodyColor, primary, accent, {canvas.bg_key}).
5. Return COMPLETE page with ALL elements and properties.
6. PRESERVE existing 'video' elements EXACTLY AS THEY ARE (id, type, src, position, size) unless explicitly asked to modify them.
7. VIDEO LIMITATION: You CANNOT generate or edit video content. Treat videos as fixed layout elements only.
8. NUMBERED STEPS: When using numbered_step elements, ALWAYS include a "number" field with sequential integers (1, 2, 3...).
9. DATA ACCURACY (CRITICAL): Do NOT hallucinate, fabricate, or invent any numbers, statistics, projections, dates, company names, or factual claims. Use ONLY verifiable facts from the provided context/vault data. If no data is available for a point, state that or omit it — never fabricate. These documents reflect real business information where data accuracy is paramount.

ELEMENT TYPE TRANSFORMATION:
- You CAN convert between element types when requested:
  - text → card (wrap content in card with icon)
  - bullet list → numbered_step elements
  - text → image_placeholder (if user wants to replace text with image)
  - card → text (unwrap card content)
  - Any other logical transformation
- When transforming, preserve the content/data but restructure into the target format.

IMAGE HANDLING:
- Images are sent as "image_placeholder" elements with an "imageDescription" field describing what the image shows.
- You can FREELY decide what to do with each image based on the user's request:
  - KEEP: If the image is fine for the context, keep its "imageDescription" EXACTLY unchanged (same text).
  - MODIFY: If the user's request calls for a different image, update the "imageDescription" to describe the new desired image. A new image will be generated from your description.
  - REMOVE: You can remove image_placeholder elements if the user asks.
  - ADD: You can add new "image_placeholder" elements with "imageDescription" and "imageType".
- IMAGE TYPES: "photo" (realistic), "infographic" (diagrams), "photo_with_text" (text overlays), "background" (full-page background images).
- BACKGROUND IMAGES: Elements with 'imageType': 'background' are full-page background images. ALWAYS preserve them in your output. You may update their 'imageDescription' if the content change makes the current background irrelevant, but NEVER remove them unless explicitly asked.
- USER MEDIA: Elements with 'isUserMedia': true are user-uploaded images. Their src values start with '{{UserMedia_'. NEVER modify, remove, replace, or reposition them under ANY circumstances — even if the user asks. Return them EXACTLY as received (same id, type, src, position, size, all properties unchanged). User uploads are immutable. You MUST include ALL such elements in your output exactly as they appear in the input — dropping them is a critical error.
- VIDEOS: NEVER change video elements or their src.

{data_freshness_section}CHART HANDLING:
- DETECT elements with 'type': 'chart'.
- UPDATE 'chartConfig' data when user instruction implies data changes.
{chart_preserve_line}
- Ensure 'chartConfig' is valid Chart.js JSON.

SVG DIAGRAM HANDLING:
- Elements with 'type': 'svg_diagram' render an inline SVG (org charts, process flows, cycles, venn, funnel, anatomy).
  Fields: `svgContent` (raw SVG string), `fillColor`, `diagramKind`, `diagramTitle`.
- PRESERVE svgContent / fillColor / diagramKind / diagramTitle byte-for-byte UNLESS the user's instruction explicitly mentions diagrams, charts, or visuals.
- If asked to ADD a diagram for new content, emit a new `svg_diagram` element with valid `svgContent` (use viewBox="0 0 800 500" for slides, "0 0 700 900" for A4 pages; keep it within the element's width/height).
- If asked to REMOVE a diagram, drop the element. If asked to CHANGE diagram content, rewrite `svgContent` and update `diagramTitle` accordingly.

OUTPUT FORMAT:
- Cards MUST use flat properties: "title", "description", "iconName" directly on the card object.
- Do NOT put card content as separate sibling text/icon elements outside the card.
- MANDATORY: Include an "outline" field — a fresh 1-line summary (max 150 chars) describing what this page covers AFTER your edits. Derive it from the ACTUAL content you produced, NOT from any old outline metadata.
{{"title":"...","outline":"Fresh 1-line summary of page content after edits","elements":[
    {{"id":"card1","type":"card","x":10,"y":10,"width":280,"height":200,"backgroundColor":"#1f2937","title":"Card Title","description":"Card body text","iconName":"lightbulb"}}
]}}

Compact JSON only, no markdown."""


def build_element_system_prompt(element_type: str, element_id: str, style_info: str, page_context: str = "") -> str:
    """Build system prompt for single element editing with page context."""
    type_guidance = {
        'text': "Text element. You can modify content, fontSize, fontWeight, fill (color), textAlign, opacity (0-1). You can also change the element type if the user requests transformation (e.g., to card, numbered_step).",
        'shape': "Shape element. You can modify fill, stroke, strokeWidth, shapeType, opacity.",
        'icon': "Icon element. You can modify iconName (use Lucide kebab-case names), fill, size, opacity (0-1).",
        'card': "Card element with icon, title, description. You can modify content, colors, opacity (0-1), or transform to other types if requested.",
        'image_placeholder': "Image placeholder. Modify imageDescription for what to generate. Set imageType: photo/infographic/photo_with_text. You can set opacity (0-1).",
        'numbered_step': "Numbered step element. You can modify label, number, colors, opacity (0-1). Include 'number' field.",
    }

    context_section = ""
    if page_context:
        context_section = f"""
PAGE CONTEXT (other elements on this page — use for spatial awareness):
{page_context}
"""

    return f"""Edit a single {element_type} element based on user instruction.

{type_guidance.get(element_type, "Modify the element as requested. You can also change its type if the user requests a transformation.")}

{style_info}
{context_section}
RULES:
1. PRESERVE the element ID exactly: "{element_id}"
2. You MAY adjust position, size (x, y, width, height, zIndex) when the user's intent implies it — focus on fulfilling the request
3. You CAN change the element type if the user requests transformation (e.g., "turn this into a card")
4. Return ONLY the complete modified element as a JSON object
5. FOCUS ON USER INTENT — interpret the request generously and make the changes that best serve what the user is asking for
6. DATA ACCURACY (CRITICAL): Do NOT hallucinate or fabricate numbers, statistics, projections, dates, or factual claims. Use ONLY verifiable facts from provided context. If data is unavailable, omit rather than invent."""


def build_multi_element_system_prompt(element_count: int, element_ids: List[str], style_info: str, page_context: str = "") -> str:
    """Build system prompt for multi-element editing with page context."""
    ids_str = ", ".join([f'"{eid}"' for eid in element_ids])

    context_section = ""
    if page_context:
        context_section = f"""
PAGE CONTEXT (other elements on this page — use for spatial awareness):
{page_context}
"""

    return f"""Edit {element_count} elements based on user instruction.

{style_info}
{context_section}
RULES:
1. PRESERVE all element IDs exactly: [{ids_str}]
2. You MAY adjust position, size (x, y, width, height, zIndex) when the user's intent implies it — focus on fulfilling the request
3. You CAN change element types if the user requests transformation
4. Return ALL {element_count} elements as a JSON array
5. FOCUS ON USER INTENT — interpret the request generously and make the changes that best serve what the user is asking for
6. DATA ACCURACY (CRITICAL): Do NOT hallucinate or fabricate numbers, statistics, projections, dates, or factual claims. Use ONLY verifiable facts from provided context. If data is unavailable, omit rather than invent.

IMAGE TYPE (for image_placeholder elements):
- "photo": realistic photographs
- "infographic": diagrams, flowcharts, data visualizations
- "photo_with_text": images with text overlays, labels, annotations
- ALWAYS include "imageType" when modifying image_placeholder elements

OUTPUT FORMAT:
[
  {{ "id": "...", "type": "...", ... }},
  {{ "id": "...", "type": "...", ... }}
]"""


# ═══════════════════════════════════════════════════════════════════════════
# Core Enhancement Functions
# ═══════════════════════════════════════════════════════════════════════════

def build_document_outline(pages_summary: Optional[List[Dict[str, Any]]], current_page_id: Optional[str] = None) -> Optional[str]:
    """Build a compact document outline string from pages_summary for LLM context.
    Prefers text_summary (derived from actual content) over stale outline metadata."""
    if not pages_summary:
        return None
    parts = []
    for s in pages_summary:
        idx = s.get('slide_index', s.get('page_index', '?'))
        title = s.get('title', 'Untitled')
        # Prefer text_summary (live content) over potentially stale outline/sectionTopic
        outline = s.get('text_summary', '') or s.get('outline', '') or s.get('sectionTopic', '')
        marker = " ← (THIS PAGE)" if current_page_id and s.get('slide_id', s.get('page_id', '')) == current_page_id else ""
        parts.append(f"  {int(idx)+1}. {title}: {outline[:120]}{marker}")
    return "\n".join(parts)

async def enhance_page_legacy(
    page_content: Dict[str, Any],
    instruction: str,
    user_id: str,
    canvas: CanvasConfig,
    style: Optional[Dict[str, Any]] = None,
    folder_ids: Optional[List[str]] = None,
    skip_vault: bool = False,
    goal: Optional[str] = None,
    content_type: str = "informative",
    icon_set: str = "lucide",
    is_structural: bool = False,
    is_update_all: bool = False,
    document_outline: Optional[str] = None,
    prefetched_structured_data: Optional[str] = None,
    deck_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Legacy page enhancement with full element control.
    AI can modify positions, sizes, content, layout, and element types.
    Uses LLM native JSON mode for reliable parsing (or agentic tool-loop
    with personal_data_tool when folders are present).
    """
    # Vault chunks now fetched agentically by the LLM via personal_data_tool
    # inside run_Enterprise_or_Personal_tool below. Structured-data schema preview
    # stays pre-fetched (small, helps the LLM decide whether to call
    # execute_code on the file).
    vault_context = ""
    structured_data_context = prefetched_structured_data or ""
    _legacy_use_personal = bool(folder_ids) and not skip_vault
    if _legacy_use_personal and not prefetched_structured_data:
        page_title = page_content.get('title', '')
        try:
            structured_data_context = await get_structured_data_context(
                user_id, instruction, page_title, folder_ids
            ) or ""
        except Exception as exc:
            logger.warning(
                "✨ [%s] structured_data_context fetch failed (non-fatal): %s",
                canvas.content_type, exc,
            )

    system_prompt = build_enhance_system_prompt(canvas, is_update_all=is_update_all)

    # Deck/document storyboard — keeps edits coherent with the rest of the
    # artefact (palette/typography/motif/intent). Same render_for_prompt
    # the initial-generation path uses, so the edit speaks the same design
    # vocabulary. Always-empty when no deck_plan was supplied (older slides
    # generated before the storyboard pass landed).
    storyboard_section = ""
    if deck_plan:
        try:
            from services.storyboard import render_for_prompt as _render_storyboard_for_prompt
            _idx = page_content.get("slide_index") or page_content.get("page_index") or 0
            _sb_slice = _render_storyboard_for_prompt(deck_plan, int(_idx) if isinstance(_idx, (int, str)) and str(_idx).isdigit() else 0)
            if _sb_slice:
                storyboard_section = (
                    f"\nDECK STORYBOARD (deck-wide design language — apply consistently):\n{_sb_slice}\n"
                )
        except Exception as _sb_exc:
            logger.warning("✨ enhance_page_legacy: storyboard render failed (non-fatal): %s", _sb_exc)

    # Style section
    style_section = ""
    if style and style.get('id') != 'ai-auto':
        s = style
        style_section = f"STYLE: title={s.get('preview', {}).get('titleColor', s.get('textPrimary', '#000'))}, body={s.get('preview', {}).get('bodyColor', s.get('textSecondary', '#333'))}, accent={s.get('accentColor', '#3B82F6')}, bg={s.get(canvas.bg_key, '#fff')}"
    else:
        style_section = f"STYLE: auto ({canvas.format_label} format)"

    # Goal section
    goal_section = ""
    if goal:
        goal_section = f"""OVERALL GOAL (for context only):
{goal}

NOTE: Edit THIS SPECIFIC PAGE only based on the user's instruction below."""

    # Document outline section — gives LLM awareness of the full document structure
    outline_section = ""
    if document_outline:
        outline_section = f"""DOCUMENT OUTLINE (for context — do NOT edit other pages, only use this to understand where this page fits):
{document_outline}

NOTE: If the DOCUMENT OUTLINE above conflicts with the actual PAGE CONTENT below, treat the PAGE CONTENT as the authoritative source of truth. The outline may be outdated from initial generation or stale after manual edits by the user."""

    # Tool nudge replaces the old pre-fetched vault block. The LLM calls
    # personal_data_tool inside run_Enterprise_or_Personal_tool below to get
    # vault chunks on demand.
    vault_section = ""
    if _legacy_use_personal:
        if is_update_all:
            vault_section = (
                f"\n\nDATA TOOL: `personal_data_tool` is available "
                f"(scoped to {len(folder_ids)} folder(s)). Call it for the "
                f"LATEST vault data on this page's topic, compare against the "
                f"current content, then make PRECISE updates:\n"
                f"- Update only the parts affected by changed data.\n"
                f"- If the new data makes the existing page structure inadequate, restructure.\n"
                f"- Do NOT change content still accurate and aligned with the vault data.\n"
                f"- Update 'imageDescription' ONLY if content change makes the existing image irrelevant.\n"
                f"- Cite each fact with [vault:<doc_id>]."
            )
        else:
            vault_section = (
                f"\n\nDATA TOOL: `personal_data_tool` is available "
                f"(scoped to {len(folder_ids)} folder(s)). Call it for relevant "
                f"vault data to enhance the page content as requested. "
                f"Cite each fact with [vault:<doc_id>]."
            )

    user_prompt = f"""Enhance {canvas.content_type} page.

GOAL: {goal or 'N/A'}
TYPE (CRITICAL - STRICTLY FOLLOW): {content_type}

{goal_section}
{outline_section}
{storyboard_section}
{style_section}

PAGE ({canvas.format_label} - {canvas.width}x{canvas.height} pixels):
{json.dumps(page_content)}

INSTRUCTION: {instruction}
{vault_section}
{structured_data_context}

Return COMPLETE page with ALL elements. Compact JSON. Ensure layout is proper with no overlapping elements."""

    # Retry with self-correction: a truncated/blank edit response must NOT
    # silently wipe the page. Re-prompt with the specific failure (unparseable
    # JSON / wrong shape / zero elements) so the model self-corrects, then fail
    # loud if every attempt is unusable. Mirrors the generation flow's guard.
    max_attempts = 3
    retry_feedback = ""
    enhanced: Optional[Dict[str, Any]] = None
    last_err: Optional[str] = None
    orig_element_count = len(page_content.get("elements", []) or [])

    try:
        for attempt in range(max_attempts):
            try:
                if _legacy_use_personal:
                    from services.enterprise_tools import run_Enterprise_or_Personal_tool
                    ai_response = await run_Enterprise_or_Personal_tool(
                        prompt=user_prompt + retry_feedback,
                        system=system_prompt,
                        user_id=user_id,
                        tier="large",
                        temperature=0.2,
                        max_tokens=8000,
                        filter_tools="auto",
                        use_personal_data=True,
                        selected_folder_ids=folder_ids,
                        max_results_cap=3,  # legacy page enhancement: max 3 chunks per call
                        expose_enterprise_tools=False,
                        personal_tool_expand_subqueries=False,
                    )
                else:
                    ai_response = await asyncio.to_thread(llm_call,
                        system_prompt,
                        user_prompt + retry_feedback,
                        user_id=user_id,
                        max_tokens=8000,
                        json_mode=True,
                        reasoning_effort="low",
                    )

                logger.info(f"✨ [{canvas.content_type}] AI response received (attempt {attempt+1}/{max_attempts})")

                # With json_mode=True, response should be valid JSON
                json_str = extract_json_from_response(ai_response)
                candidate = json.loads(json_str)

                # SAFETY: AI may return a JSON array instead of single page dict
                if isinstance(candidate, list):
                    logger.warning(f"⚠️ [{canvas.content_type}] AI returned array ({len(candidate)} items) instead of single page — extracting best match")
                    current_title = page_content.get("title", "")
                    current_id = page_content.get("id", "")
                    matched = None
                    for item in candidate:
                        if isinstance(item, dict):
                            if item.get("id") == current_id or item.get("title") == current_title:
                                matched = item
                                break
                    candidate = matched if matched else (candidate[0] if candidate and isinstance(candidate[0], dict) else {"elements": []})

                # Type guard — candidate must be a dict. Don't silently fall
                # back to the original here; re-prompt so the edit is actually applied.
                if not isinstance(candidate, dict):
                    logger.warning(f"⚠️ [{canvas.content_type}] AI returned invalid type: {type(candidate).__name__} (attempt {attempt+1}/{max_attempts})")
                    retry_feedback = (
                        "\n\nYOUR PREVIOUS RESPONSE WAS NOT A SINGLE JSON PAGE OBJECT. "
                        "Return ONE complete, valid JSON object for THIS page with ALL its "
                        "elements — no arrays, no commentary, no markdown fences."
                    )
                    continue

                # Unwrap nested structures
                for wrapper_key in ("PAGE", "slide", "page"):
                    if wrapper_key in candidate and isinstance(candidate[wrapper_key], dict):
                        candidate = candidate[wrapper_key]
                        break

                # Fix: AI returned single element instead of page
                if candidate.get("type") and not candidate.get("elements"):
                    logger.warning(f"⚠️ [{canvas.content_type}] AI returned single element, wrapping")
                    single = candidate
                    orig_elements = page_content.get("elements", [])
                    idx = next((i for i, el in enumerate(orig_elements) if el.get("id") == single.get("id")), -1)
                    if idx >= 0:
                        updated = [el.copy() for el in orig_elements]
                        updated[idx] = {**updated[idx], **single}
                    else:
                        updated = orig_elements + [single]
                    candidate = {
                        "title": page_content.get("title", ""),
                        "elements": updated,
                        "backgroundColor": page_content.get("backgroundColor", "#ffffff"),
                    }

                # GUARD: a non-empty page must not be edited down to zero
                # elements — that's a truncated/failed edit, not a valid wipe.
                # Re-prompt instead of shipping a blank page.
                cand_n = len(candidate.get("elements", []) or [])
                if orig_element_count > 0 and cand_n == 0:
                    logger.warning(
                        f"⚠️ [{canvas.content_type}] Edit produced 0 elements from a "
                        f"{orig_element_count}-element page (attempt {attempt+1}/{max_attempts}) "
                        f"— likely truncated/malformed. Retrying with corrective feedback…"
                    )
                    retry_feedback = (
                        "\n\nYOUR PREVIOUS EDIT RETURNED ZERO ELEMENTS, which would BLANK the "
                        "page. Return the COMPLETE page with ALL of its elements (modified per "
                        "the instruction), as ONE valid, fully-closed JSON object. Do NOT drop elements."
                    )
                    continue

                enhanced = candidate
                if attempt > 0:
                    logger.info(f"✅ [{canvas.content_type}] Edit succeeded on attempt {attempt+1}")
                break

            except HTTPException:
                raise  # credit / HTTP errors propagate — not a content retry
            except Exception as parse_err:
                last_err = str(parse_err)
                logger.warning(f"⚠️ [{canvas.content_type}] Edit parse failed (attempt {attempt+1}/{max_attempts}): {parse_err}. Retrying…")
                retry_feedback = (
                    "\n\nYOUR PREVIOUS RESPONSE COULD NOT BE PARSED AS JSON. Return ONE complete, "
                    "valid, fully-closed JSON page object with ALL elements — no markdown fences, no commentary."
                )
                continue

        # Fail loud: do NOT ship a blank/unchanged page silently.
        if enhanced is None:
            raise HTTPException(
                status_code=502,
                detail=f"AI edit returned no usable page after {max_attempts} attempts (last_error={last_err})",
            )

        # ── USER MEDIA SAFETY NET ──
        # Ensure user-uploaded media elements survive AI processing.
        # If AI dropped or corrupted a user media element, force-restore it from the original input.
        orig_elements = page_content.get("elements", [])
        user_media_by_id = {}
        for oel in orig_elements:
            if oel.get("isUserMedia") or (isinstance(oel.get("src", ""), str) and oel.get("src", "").startswith("{{UserMedia_")):
                user_media_by_id[oel.get("id")] = oel

        if user_media_by_id:
            enhanced_ids = {el.get("id") for el in enhanced.get("elements", [])}
            # Restore dropped user media elements
            for um_id, um_el in user_media_by_id.items():
                if um_id not in enhanced_ids:
                    logger.warning(f"⚠️ [{canvas.content_type}] User media '{um_id}' dropped by AI — re-injecting")
                    enhanced["elements"].append(um_el)
            # Fix corrupted user media (flag dropped or src changed)
            for el in enhanced.get("elements", []):
                if el.get("id") in user_media_by_id:
                    orig = user_media_by_id[el["id"]]
                    if not el.get("isUserMedia") and orig.get("isUserMedia"):
                        logger.warning(f"⚠️ [{canvas.content_type}] User media '{el['id']}' lost isUserMedia flag — restoring")
                        el["isUserMedia"] = True
                    orig_src = orig.get("src", "")
                    if isinstance(orig_src, str) and orig_src.startswith("{{UserMedia_") and el.get("src") != orig_src:
                        logger.warning(f"⚠️ [{canvas.content_type}] User media '{el['id']}' src corrupted — restoring")
                        el["src"] = orig_src
                        el["type"] = orig.get("type", "image")

        # ── BACKGROUND IMAGE SAFETY NET ──
        # Ensure background images survive AI processing.
        # If AI dropped a background image element, force-restore it from the original input.
        enhanced_ids = {el.get("id") for el in enhanced.get("elements", [])}
        for oel in orig_elements:
            if oel.get("imageType") == "background" and oel.get("id") not in enhanced_ids:
                logger.warning(f"⚠️ [{canvas.content_type}] Background image '{oel.get('id')}' dropped by AI — re-injecting")
                enhanced["elements"].insert(0, oel)

        # Sanitize icon elements
        for el in enhanced.get("elements", []):
            if el.get("type") == "icon":
                el.pop("svgSrc", None)
                el.pop("svgPath", None)
                el.pop("resolvedIconName", None)

        # Fix numbered steps
        _fix_numbered_step_numbers(enhanced.get("elements", []))

        # Clear template if layout changed (frees page from template constraints)
        if is_structural:
            enhanced.pop("template", None)

        return {"success": True, canvas.enhanced_key: enhanced}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"✨ [{canvas.content_type}] Enhancement failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def enhance_page_legacy_streaming(
    page_content: Dict[str, Any],
    instruction: str,
    user_id: str,
    canvas: CanvasConfig,
    style: Optional[Dict[str, Any]] = None,
    folder_ids: Optional[List[str]] = None,
    skip_vault: bool = False,
    goal: Optional[str] = None,
    content_type: str = "informative",
    icon_set: str = "lucide",
    is_structural: bool = False,
    is_update_all: bool = False,
    document_outline: Optional[str] = None,
    prefetched_structured_data: Optional[str] = None,
    deck_plan: Optional[Dict[str, Any]] = None,
):
    """
    Streaming version of enhance_page_legacy.
    Yields SSE events: classification, chunk, result, error.

    Note: when personal-vault is enabled (folder_ids + not skip_vault), the
    underlying LLM call is replaced with the agentic tool-loop helper, which
    is non-streaming. The result is yielded as a single chunk in that case.
    True streaming only happens on the no-folder path.
    """
    # Vault chunks now fetched agentically by the LLM via personal_data_tool.
    vault_context = ""
    structured_data_context = prefetched_structured_data or ""
    _legacy_use_personal = bool(folder_ids) and not skip_vault
    if _legacy_use_personal and not prefetched_structured_data:
        page_title = page_content.get('title', '')
        try:
            structured_data_context = await get_structured_data_context(
                user_id, instruction, page_title, folder_ids
            ) or ""
        except Exception as exc:
            logger.warning(
                "✨ [%s] structured_data_context fetch failed (non-fatal): %s",
                canvas.content_type, exc,
            )

    system_prompt = build_enhance_system_prompt(canvas, is_update_all=is_update_all)

    # Storyboard slice (deck-wide design language) for the streaming edit.
    storyboard_section = ""
    if deck_plan:
        try:
            from services.storyboard import render_for_prompt as _render_storyboard_for_prompt
            _idx = page_content.get("slide_index") or page_content.get("page_index") or 0
            _sb_slice = _render_storyboard_for_prompt(deck_plan, int(_idx) if isinstance(_idx, (int, str)) and str(_idx).isdigit() else 0)
            if _sb_slice:
                storyboard_section = f"\nDECK STORYBOARD (apply consistently):\n{_sb_slice}\n"
        except Exception as _sb_exc:
            logger.warning("✨ enhance_page_legacy_streaming: storyboard render failed (non-fatal): %s", _sb_exc)

    style_section = ""
    if style and style.get('id') != 'ai-auto':
        s = style
        style_section = f"STYLE: title={s.get('preview', {}).get('titleColor', s.get('textPrimary', '#000'))}, body={s.get('preview', {}).get('bodyColor', s.get('textSecondary', '#333'))}, accent={s.get('accentColor', '#3B82F6')}, bg={s.get(canvas.bg_key, '#fff')}"
    else:
        style_section = f"STYLE: auto ({canvas.format_label} format)"

    goal_section = ""
    if goal:
        goal_section = f"OVERALL GOAL: {goal}\nNOTE: Edit THIS SPECIFIC PAGE only."

    outline_section = ""
    if document_outline:
        outline_section = f"\nDOCUMENT OUTLINE (context only — edit THIS page only):\n{document_outline}\n\nNOTE: If the DOCUMENT OUTLINE conflicts with actual PAGE CONTENT below, trust the PAGE CONTENT — the outline may be stale."

    vault_section = ""
    if _legacy_use_personal:
        if is_update_all:
            vault_section = (
                f"\n\nDATA TOOL: `personal_data_tool` is available "
                f"(scoped to {len(folder_ids)} folder(s)). Call it for the LATEST "
                f"vault data, compare against the current page, then make PRECISE "
                f"updates: change only what the new data demands; do NOT change "
                f"content that is still accurate; update imageDescriptions ONLY if "
                f"existing images no longer match. Cite each fact with [vault:<doc_id>]."
            )
        else:
            vault_section = (
                f"\n\nDATA TOOL: `personal_data_tool` is available "
                f"(scoped to {len(folder_ids)} folder(s)). Call it for relevant vault "
                f"data to enhance content. Cite each fact with [vault:<doc_id>]."
            )

    user_prompt = f"""Enhance {canvas.content_type} page.

GOAL: {goal or 'N/A'}
TYPE: {content_type}
{goal_section}
{outline_section}
{storyboard_section}
{style_section}

PAGE ({canvas.format_label} - {canvas.width}x{canvas.height} pixels):
{json.dumps(page_content)}

INSTRUCTION: {instruction}
{vault_section}
{structured_data_context}

Return COMPLETE page with ALL elements. Compact JSON."""

    try:
        full_text = ""
        if _legacy_use_personal:
            # Agentic path is non-streaming (LLM tool-loop). Yield one
            # chunk with the full result so the SSE consumer still gets data.
            from services.enterprise_tools import run_Enterprise_or_Personal_tool
            full_text = await run_Enterprise_or_Personal_tool(
                prompt=user_prompt,
                system=system_prompt,
                user_id=user_id,
                tier="large",
                temperature=0.2,
                max_tokens=8000,
                filter_tools="auto",
                use_personal_data=True,
                selected_folder_ids=folder_ids,
                max_results_cap=3,  # legacy page enhancement (streaming): max 3 chunks per call
                expose_enterprise_tools=False,
                personal_tool_expand_subqueries=False,
            )
            yield f"data: {json.dumps({'type': 'chunk', 'text': full_text})}\n\n"
        else:
            for chunk in llm_call_streaming(
                system_prompt, user_prompt,
                user_id=user_id, max_tokens=8000, json_mode=True,
            ):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"

        # Parse + validate the streamed result. The first attempt is the
        # streamed text; if it's unparseable or would BLANK the page, run
        # buffered (non-streamed) corrective retries so a truncated edit neither
        # 500s nor silently wipes the page. Mirrors enhance_page_legacy.
        orig_element_count = len(page_content.get("elements", []) or [])
        enhanced = None
        retry_feedback = ""
        last_err = None

        for attempt in range(3):
            if attempt == 0:
                raw_text = full_text
            else:
                raw_text = await asyncio.to_thread(llm_call,
                    system_prompt,
                    user_prompt + retry_feedback,
                    user_id=user_id,
                    max_tokens=8000,
                    json_mode=True,
                    reasoning_effort="low",
                )

            try:
                candidate = json.loads(extract_json_from_response(raw_text))
            except Exception as parse_err:
                last_err = str(parse_err)
                logger.warning(f"⚠️ [{canvas.content_type}] Streaming edit parse failed (attempt {attempt+1}/3): {parse_err}. Retrying…")
                retry_feedback = (
                    "\n\nYOUR PREVIOUS RESPONSE COULD NOT BE PARSED AS JSON. Return ONE complete, "
                    "valid, fully-closed JSON page object with ALL elements — no markdown fences, no commentary."
                )
                continue

            # SAFETY: AI may return a JSON array (e.g. [existing_slide, new_slide]) when it
            # misinterprets a "create new" instruction as an edit. Extract the single page
            # that matches the current page title/id rather than crashing on list.get().
            if isinstance(candidate, list):
                logger.warning(f"⚠️ [{canvas.content_type}] AI returned array ({len(candidate)} items) instead of single page — extracting best match")
                current_title = page_content.get("title", "")
                current_id = page_content.get("id", "")
                matched = None
                for item in candidate:
                    if isinstance(item, dict):
                        if item.get("id") == current_id or item.get("title") == current_title:
                            matched = item
                            break
                candidate = matched if matched else (candidate[0] if candidate and isinstance(candidate[0], dict) else None)

            # Type guard — re-prompt rather than silently keeping the original.
            if not isinstance(candidate, dict):
                logger.warning(f"⚠️ [{canvas.content_type}] AI returned invalid type (attempt {attempt+1}/3)")
                retry_feedback = (
                    "\n\nYOUR PREVIOUS RESPONSE WAS NOT A SINGLE JSON PAGE OBJECT. "
                    "Return ONE complete, valid JSON object for THIS page with ALL its elements."
                )
                continue

            for wrapper_key in ("PAGE", "slide", "page"):
                if wrapper_key in candidate and isinstance(candidate[wrapper_key], dict):
                    candidate = candidate[wrapper_key]
                    break

            if candidate.get("type") and not candidate.get("elements"):
                single = candidate
                orig = page_content.get("elements", [])
                idx = next((i for i, el in enumerate(orig) if el.get("id") == single.get("id")), -1)
                if idx >= 0:
                    updated = [el.copy() for el in orig]
                    updated[idx] = {**updated[idx], **single}
                else:
                    updated = orig + [single]
                candidate = {"title": page_content.get("title", ""), "elements": updated, "backgroundColor": page_content.get("backgroundColor", "#ffffff")}

            # GUARD: don't let an edit blank a non-empty page.
            if orig_element_count > 0 and len(candidate.get("elements", []) or []) == 0:
                logger.warning(f"⚠️ [{canvas.content_type}] Streaming edit produced 0 elements from a {orig_element_count}-element page (attempt {attempt+1}/3) — retrying")
                retry_feedback = (
                    "\n\nYOUR PREVIOUS EDIT RETURNED ZERO ELEMENTS, which would BLANK the page. "
                    "Return the COMPLETE page with ALL of its elements (modified per the instruction), "
                    "as ONE valid, fully-closed JSON object. Do NOT drop elements."
                )
                continue

            enhanced = candidate
            if attempt > 0:
                logger.info(f"✅ [{canvas.content_type}] Streaming edit recovered on attempt {attempt+1}")
            break

        # Fail loud rather than yielding a blank/garbage page.
        if enhanced is None:
            raise HTTPException(
                status_code=502,
                detail=f"AI edit returned no usable page after retries (last_error={last_err})",
            )

        # ── BACKGROUND IMAGE SAFETY NET ──
        orig_elements = page_content.get("elements", [])
        enhanced_ids = {el.get("id") for el in enhanced.get("elements", [])}
        for oel in orig_elements:
            if oel.get("imageType") == "background" and oel.get("id") not in enhanced_ids:
                logger.warning(f"⚠️ [{canvas.content_type}] Background image '{oel.get('id')}' dropped by AI — re-injecting")
                enhanced["elements"].insert(0, oel)

        for el in enhanced.get("elements", []):
            if el.get("type") == "icon":
                el.pop("svgSrc", None)
                el.pop("svgPath", None)
                el.pop("resolvedIconName", None)

        _fix_numbered_step_numbers(enhanced.get("elements", []))

        if is_structural:
            enhanced.pop("template", None)

        yield f"data: {json.dumps({'type': 'result', 'data': {canvas.enhanced_key: enhanced, 'success': True, 'ai_message': 'Applied changes.'}})}\n\n"

    except HTTPException as he:
        yield f"data: {json.dumps({'type': 'error', 'message': str(he.detail), 'status_code': he.status_code})}\n\n"
    except Exception as e:
        logger.error(f"✨ [{canvas.content_type}] Streaming enhancement failed: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


# ═══════════════════════════════════════════════════════════════════════════
# Image Element Enhancement
# ═══════════════════════════════════════════════════════════════════════════

async def enhance_image_element(
    element: Dict[str, Any],
    instruction: str,
    user_id: str,
    style: Optional[Dict[str, Any]] = None,
    vault_context: str = "",
    generation_quality: str = "premium",
) -> Dict[str, Any]:
    """AI-enhance an image element by updating its description."""
    element_id = element.get('id', 'unknown')
    existing_desc = element.get('imageDescription', element.get('description', ''))
    original_image_type = element.get('imageType', 'photo')

    system_prompt = """Generate an updated image description based on user instruction.

RULES:
1. Create a clear, detailed image description (1-3 sentences)
2. Incorporate the user's modification request
3. Keep relevant aspects from the original description if applicable
4. DATA ACCURACY: Do NOT fabricate specific facts, numbers, or claims in the image description. Base descriptions on actual provided context.

IMAGE TYPE CLASSIFICATION:
- "photo": realistic photographs, nature, people, objects
- "infographic": diagrams, flowcharts, data visualizations
- "photo_with_text": images with text overlay, labels, captions
- "generationQuality": "{generation_quality}"

Return JSON: { "description": "...", "image_type": "photo|infographic|photo_with_text", "generationQuality": "..." }
(Note: Set generationQuality to exactly: "{generation_quality}")"""

    user_prompt = f"""ORIGINAL DESCRIPTION: {existing_desc or "No existing description"}
CURRENT IMAGE TYPE: {original_image_type}
USER INSTRUCTION: {instruction}
{f"CONTEXT:{chr(10)}{vault_context}" if vault_context else ""}

Generate new image description with type (preserve current image type unless the instruction clearly changes it):"""

    try:
        response = await asyncio.to_thread(llm_call,
            system_prompt, user_prompt,
            user_id=user_id, max_tokens=4096, json_mode=True,
            reasoning_effort="low",
        )

        new_desc = response
        image_type = "photo"
        try:
            parsed = json.loads(response)
            new_desc = parsed.get("description", response)
            image_type = parsed.get("image_type", "photo")
            # Enforce the quality that was selected
            generation_quality_out = parsed.get("generationQuality", generation_quality)
        except json.JSONDecodeError:
            new_desc = response.strip().strip('"').strip("'")
            generation_quality_out = generation_quality

        updated = element.copy()
        updated['type'] = 'image_placeholder'
        updated['imageDescription'] = new_desc
        updated['imageType'] = image_type
        updated['generationQuality'] = generation_quality_out
        updated['id'] = element_id
        # Remove src so frontend regenerates
        updated.pop('src', None)

        return {"success": True, "enhanced_element": updated}

    except Exception as e:
        logger.error(f"❌ [IMAGE] Description generation failed: {e}")
        updated = element.copy()
        updated['type'] = 'image_placeholder'
        updated['imageDescription'] = f"{existing_desc}. {instruction}" if existing_desc else instruction
        updated['imageType'] = element.get('imageType', 'photo')
        updated['generationQuality'] = generation_quality
        return {"success": True, "enhanced_element": updated}


# ═══════════════════════════════════════════════════════════════════════════
# Single Element Enhancement (with page context)
# ═══════════════════════════════════════════════════════════════════════════

async def enhance_single_element(
    element: Dict[str, Any],
    instruction: str,
    user_id: str,
    canvas: CanvasConfig,
    page_content: Optional[Dict[str, Any]] = None,
    style: Optional[Dict[str, Any]] = None,
    folder_ids: Optional[List[str]] = None,
    skip_vault: bool = True,
    generation_quality: str = "premium",
) -> Dict[str, Any]:
    """AI-enhance a single element with page context injection."""
    element_type = element.get('type', 'unknown')
    element_id = element.get('id', 'unknown')

    logger.info(f"✏️ [ELEMENT] Enhancing {element_type}: {element_id}")

    # Vault chunks now fetched agentically by the LLM via personal_data_tool
    # inside run_Enterprise_or_Personal_tool below (cap=3 for single element).
    vault_context = ""  # kept empty; used only by the image-element passthrough below
    _elem_use_personal = bool(folder_ids) and not skip_vault

    # Route video → error
    if element_type == 'video' or (element.get('isUserMedia') and element_type == 'video'):
        return {
            "success": False,
            "error": "AI cannot edit video elements at this time.",
            "ai_message": "I can't edit video elements directly, but you can manually adjust them on the canvas!"
        }

    # Route image → description enhancement (uses vault_context as a string;
    # leave empty since enhance_image_element handles its own context if needed)
    if element_type in ['image', 'image_placeholder']:
        return await enhance_image_element(
            element=element, instruction=instruction,
            user_id=user_id, style=style, vault_context=vault_context,
            generation_quality=generation_quality,
        )

    # Build style reference
    style_info = ""
    if style and style.get('id') != 'ai-auto':
        style_info = f"""STYLE COLORS:
- Title: {style.get('textPrimary', style.get('preview', {}).get('titleColor', '#000'))}
- Body: {style.get('textSecondary', style.get('preview', {}).get('bodyColor', '#333'))}
- Accent: {style.get('accentColor', '#3B82F6')}"""

    # Page context injection
    page_ctx = ""
    if page_content:
        page_ctx = build_page_context_summary(page_content, exclude_ids=[element_id])

    system_prompt = build_element_system_prompt(element_type, element_id, style_info, page_ctx)

    _tool_nudge = (
        f"\n\nDATA TOOL: `personal_data_tool` is available "
        f"(scoped to {len(folder_ids)} folder(s)). Call it with a focused query for "
        f"the topic of this element if you need vault facts. Cite each fact with "
        f"[vault:<doc_id>]."
        if _elem_use_personal else ""
    )
    user_prompt = f"""CURRENT ELEMENT:
{json.dumps(element, indent=2)}

INSTRUCTION: {instruction}
{_tool_nudge}

Return the modified element JSON:"""

    try:
        if _elem_use_personal:
            from services.enterprise_tools import run_Enterprise_or_Personal_tool
            ai_response = await run_Enterprise_or_Personal_tool(
                prompt=user_prompt,
                system=system_prompt,
                user_id=user_id,
                tier="large",
                temperature=0.2,
                max_tokens=4096,
                filter_tools="auto",
                use_personal_data=True,
                selected_folder_ids=folder_ids,
                max_results_cap=3,  # single element edit: max 3 chunks per call
                expose_enterprise_tools=False,
                personal_tool_expand_subqueries=False,
            )
        else:
            ai_response = await asyncio.to_thread(llm_call,
                system_prompt, user_prompt,
                user_id=user_id, max_tokens=4096, json_mode=True,
                reasoning_effort="low",
            )

        enhanced = json.loads(extract_json_from_response(ai_response))
        enhanced['id'] = element_id

        if enhanced.get('type') == 'icon':
            enhanced.pop('svgSrc', None)
            enhanced.pop('svgPath', None)
            enhanced.pop('resolvedIconName', None)

        # Position validation for single element
        # DISABLED: testing LLM-based layout fixer
        # validate_element_positions([enhanced], canvas, [element], is_layout_change=False)

        return {"success": True, "enhanced_element": enhanced}

    except json.JSONDecodeError as e:
        logger.error(f"✏️ [ELEMENT] JSON parse error: {e}")
        return {"success": False, "error": f"Failed to parse AI response: {e}"}
    except Exception as e:
        logger.error(f"✏️ [ELEMENT] Enhancement failed: {e}")
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# Multi-Element Enhancement (with page context)
# ═══════════════════════════════════════════════════════════════════════════

async def enhance_multiple_elements(
    elements: List[Dict[str, Any]],
    instruction: str,
    user_id: str,
    canvas: CanvasConfig,
    page_content: Optional[Dict[str, Any]] = None,
    style: Optional[Dict[str, Any]] = None,
    folder_ids: Optional[List[str]] = None,
    skip_vault: bool = True,
    generation_quality: str = "premium",
) -> Dict[str, Any]:
    """AI-enhance multiple elements at once with page context."""
    element_count = len(elements)
    element_ids = [el.get('id', 'unknown') for el in elements]

    logger.info(f"✏️ [MULTI] Enhancing {element_count} elements")

    # Vault chunks now fetched agentically via personal_data_tool below.
    _multi_use_personal = bool(folder_ids) and not skip_vault

    style_info = ""
    if style and style.get('id') != 'ai-auto':
        style_info = f"""STYLE COLORS:
- Title: {style.get('textPrimary', style.get('preview', {}).get('titleColor', '#000'))}
- Body: {style.get('textSecondary', style.get('preview', {}).get('bodyColor', '#333'))}
- Accent: {style.get('accentColor', '#3B82F6')}"""

    page_ctx = ""
    if page_content:
        page_ctx = build_page_context_summary(page_content, exclude_ids=element_ids)

    system_prompt = build_multi_element_system_prompt(element_count, element_ids, style_info, page_ctx)

    _tool_nudge = (
        f"\n\nDATA TOOL: `personal_data_tool` is available "
        f"(scoped to {len(folder_ids)} folder(s)). Call it with a focused query "
        f"covering the topic of these elements if you need vault facts. "
        f"Cite each fact with [vault:<doc_id>]."
        if _multi_use_personal else ""
    )
    user_prompt = f"""ELEMENTS TO EDIT:
{json.dumps(elements, indent=2)}

INSTRUCTION: {instruction}
{_tool_nudge}

Return the modified elements as a JSON array:"""

    try:
        if _multi_use_personal:
            from services.enterprise_tools import run_Enterprise_or_Personal_tool
            ai_response = await run_Enterprise_or_Personal_tool(
                prompt=user_prompt,
                system=system_prompt,
                user_id=user_id,
                tier="large",
                temperature=0.2,
                max_tokens=4000,
                filter_tools="auto",
                use_personal_data=True,
                selected_folder_ids=folder_ids,
                max_results_cap=5,  # multi element edit: max 5 chunks per call
                expose_enterprise_tools=False,
                personal_tool_expand_subqueries=False,
            )
        else:
            ai_response = await asyncio.to_thread(llm_call,
                system_prompt, user_prompt,
                user_id=user_id, max_tokens=4000, json_mode=True,
                reasoning_effort="low",
            )

        enhanced_elements = json.loads(extract_json_from_response(ai_response))
        if not isinstance(enhanced_elements, list):
            raise ValueError("Expected JSON array")

        for i, enhanced in enumerate(enhanced_elements):
            if i < len(element_ids):
                enhanced['id'] = element_ids[i]
            if enhanced.get('type') == 'icon':
                enhanced.pop('svgSrc', None)
                enhanced.pop('svgPath', None)
            if enhanced.get('type') == 'image_placeholder':
                enhanced['generationQuality'] = enhanced.get('generationQuality', generation_quality)

        # DISABLED: testing LLM-based layout fixer
        # validate_element_positions(enhanced_elements, canvas, elements, is_layout_change=False)

        return {"success": True, "enhanced_elements": enhanced_elements}

    except json.JSONDecodeError as e:
        logger.error(f"✏️ [MULTI] JSON parse error: {e}")
        return {"success": False, "error": f"Failed to parse AI response: {e}"}
    except Exception as e:
        logger.error(f"✏️ [MULTI] Enhancement failed: {e}")
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# Chart Data Generation
# ═══════════════════════════════════════════════════════════════════════════

async def generate_chart_data(
    chart_type: str,
    query: str,
    user_id: str,
    folder_ids: Optional[List[str]] = None,
    page_context: Optional[Dict[str, Any]] = None,
    source_context: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate Chart.js compatible configuration."""
    logger.info(f"📊 [CHART] Generating {chart_type} chart: {query[:50]}...")

    _VALID_CHART_TYPES = {"bar", "line", "pie", "doughnut", "radar", "polarArea", "scatter", "bubble"}

    def _is_chart_valid(cfg: dict) -> bool:
        if not isinstance(cfg, dict) or cfg.get("type") not in _VALID_CHART_TYPES:
            return False
        data = cfg.get("data")
        if not isinstance(data, dict):
            return False
        ctype = cfg["type"]
        if ctype not in ("scatter", "bubble"):
            if not isinstance(data.get("labels"), list) or not data["labels"]:
                return False
        ds = data.get("datasets")
        if not isinstance(ds, list) or not ds or not isinstance(ds[0], dict) or not ds[0].get("data"):
            return False
        return True

    def _normalize_chart(cfg: dict) -> dict:
        """Apply deterministic fixes (type normalization, misplaced nesting)."""
        if not isinstance(cfg, dict):
            return cfg
        ctype = cfg.get("type", "bar")
        if ctype not in _VALID_CHART_TYPES:
            stripped = ctype.replace("chart-", "").replace("chart_", "")
            cfg["type"] = stripped if stripped in _VALID_CHART_TYPES else "bar"
        if "data" not in cfg and ("labels" in cfg or "datasets" in cfg):
            cfg["data"] = {"labels": cfg.pop("labels", []), "datasets": cfg.pop("datasets", [])}
        return cfg

    async def _ai_retry_chart(bad_config: dict, context_query: str) -> Optional[dict]:
        """Ask AI to fix a malformed chartConfig with full context."""
        try:
            fix_prompt = (
                "You are a Chart.js configuration expert. The following chart config is malformed. "
                "Fix it and return ONLY valid JSON.\n\n"
                "Rules:\n"
                "- type: one of bar, line, pie, doughnut, radar, polarArea, scatter, bubble\n"
                "- data.labels: array of strings (3-6 items) — omit for scatter/bubble\n"
                "- data.datasets: array with at least one {label, data, backgroundColor}\n"
                "- scatter data: [{x, y}], bubble data: [{x, y, r}]\n"
                "- Make data contextually relevant\n\n"
                f"Original query: {context_query}\n"
                f"Broken config: {json.dumps(bad_config)}\n\n"
                "Return ONLY the fixed JSON."
            )
            resp = await asyncio.to_thread(llm_call,
                fix_prompt, "Fix this chart config.",
                user_id=user_id, max_tokens=4000, json_mode=True,
                reasoning_effort="low",
            )
            fixed = json.loads(extract_json_from_response(resp))
            fixed = _normalize_chart(fixed)
            return fixed if _is_chart_valid(fixed) else None
        except Exception as e:
            logger.warning(f"📊 [CHART] AI retry fix failed: {e}")
            return None

    # Try structured data first — sandbox computes the chart data from the file.
    if STRUCTURED_DATA_AVAILABLE and folder_ids:
        try:
            chart_type_line = (
                f"Preferred chart type: {chart_type} (allowed: bar, line, pie, doughnut, radar, polarArea, scatter, bubble)"
                if chart_type else
                "Pick the most appropriate chart type from: bar, line, pie, doughnut, radar, polarArea, scatter, bubble."
            )
            instruction = (
                f"User request: {query}\n\n"
                f"{chart_type_line}\n\n"
                "Write a Python script that:\n"
                "1. Loads the relevant file from /workspace/input/.\n"
                "2. Computes the labels and dataset values needed for the chart.\n"
                "3. Builds a Chart.js config dict with shape: "
                "{\"type\": <chart_type>, \"data\": {\"labels\": [...], \"datasets\": [{\"label\": \"...\", \"data\": [...], \"backgroundColor\": [...]}]}}.\n"
                "4. Prints the config as JSON to stdout via `print(json.dumps(config))`. Print NOTHING ELSE.\n"
                "Use up to 12 labels max — aggregate / take top-N as appropriate."
            )
            sandbox = await run_structured_sandbox(
                user_id=user_id, folder_ids=folder_ids,
                instruction_prompt=instruction, log_prefix="EDIT-CHART",
            )
            if sandbox.get("success") and sandbox.get("stdout"):
                stdout = sandbox["stdout"].strip()
                try:
                    chart_config = json.loads(stdout)
                except Exception:
                    s_idx, e_idx = stdout.find("{"), stdout.rfind("}")
                    chart_config = json.loads(stdout[s_idx:e_idx + 1]) if s_idx != -1 and e_idx > s_idx else None
                if isinstance(chart_config, dict):
                    chart_config = _normalize_chart(chart_config)
                    entries = sandbox.get("entries") or []
                    src_doc = entries[0].filename if entries else None
                    if _is_chart_valid(chart_config):
                        return {"success": True, "chart_config": chart_config, "source": "structured_data",
                                "source_document": src_doc}
                    logger.warning("📊 [CHART] Sandbox chart malformed, attempting AI fix...")
                    fixed = await _ai_retry_chart(chart_config, query)
                    if fixed:
                        return {"success": True, "chart_config": fixed, "source": "structured_data",
                                "source_document": src_doc}
        except Exception as e:
            logger.warning(f"📊 [CHART] Structured sandbox path failed: {e}")

    # Fallback: vault chunks now fetched agentically by the LLM via
    # personal_data_tool inside run_Enterprise_or_Personal_tool below (cap=3).
    _chart_use_personal = bool(folder_ids)

    system_prompt = """Data visualization expert. Generate Chart.js compatible configuration.

Output ONLY valid JSON:
{
  "type": "bar" | "line" | "pie" | "doughnut" | "radar" | "polarArea" | "scatter" | "bubble",
  "data": {"labels": [...], "datasets": [{"label": "...", "data": [...], "backgroundColor": [...]}]},
  "options": {"responsive": true, "plugins": {"title": {"display": true, "text": "..."}}}
}

Chart type guidance:
- bar/line/pie/doughnut: standard charts with labels[] and numeric data[]
- radar: multi-axis comparison with labels[] as axes, data[] per axis
- polarArea: like pie but with variable radius, labels[] and data[]
- scatter: use data as [{x, y}] point objects instead of simple numbers
- bubble: use data as [{x, y, r}] point objects with radius

Use professional colors: #3B82F6, #10B981, #F59E0B, #EF4444, #8B5CF6, #EC4899
If no real data available, create realistic sample data."""

    context_info = (
        f"\n\nDATA TOOL: `personal_data_tool` is available "
        f"(scoped to {len(folder_ids)} folder(s)). Call it with a focused query "
        f"for the chart's topic to fetch real data points BEFORE building the config. "
        f"Cite each fact with [vault:<doc_id>]."
        if _chart_use_personal else ""
    )

    page_ctx = ""
    if page_context:
        source_type = source_context or "document"
        elements = page_context.get("elements", [])
        texts = [el["content"] for el in elements if el.get("type") == "text" and el.get("content")]
        if texts:
            page_ctx = f"\nPAGE CONTENT:\n" + "\n".join(texts[:5])
        title = page_context.get("title", "")
        if title:
            page_ctx = f"\nPAGE TITLE: {title}" + page_ctx

    user_prompt = f'Create a {chart_type} chart for: "{query}"{context_info}{page_ctx}\n\nChart.js JSON:'

    try:
        if _chart_use_personal:
            from services.enterprise_tools import run_Enterprise_or_Personal_tool
            ai_response = await run_Enterprise_or_Personal_tool(
                prompt=user_prompt,
                system=system_prompt,
                user_id=user_id,
                tier="large",
                temperature=0.2,
                max_tokens=16000,
                filter_tools="auto",
                use_personal_data=True,
                selected_folder_ids=folder_ids,
                max_results_cap=3,  # chart fallback gen: max 3 chunks per call
                expose_enterprise_tools=False,
                personal_tool_expand_subqueries=False,
            )
        else:
            ai_response = await asyncio.to_thread(llm_call,
                system_prompt, user_prompt,
                user_id=user_id, max_tokens=16000, json_mode=True,
                reasoning_effort="low",
            )
        chart_config = json.loads(extract_json_from_response(ai_response))
        chart_config = _normalize_chart(chart_config)
        if not _is_chart_valid(chart_config):
            logger.warning(f"📊 [CHART] Vault context chart malformed, attempting AI fix...")
            fixed = await _ai_retry_chart(chart_config, query)
            if fixed:
                chart_config = fixed
            else:
                logger.warning(f"📊 [CHART] AI fix also failed, returning demo fallback")
                chart_config = {
                    "type": chart_type or "bar",
                    "data": {
                        "labels": ["Item 1", "Item 2", "Item 3"],
                        "datasets": [{"label": "Data", "data": [10, 20, 15],
                                      "backgroundColor": ["#3B82F6", "#10B981", "#F59E0B"]}]
                    }
                }
        return {"success": True, "chart_config": chart_config, "source": "vault_context"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"📊 [CHART] Generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrate Single Page Edit
# ═══════════════════════════════════════════════════════════════════════════

async def orchestrate_edit(
    instruction: str,
    page_content: Dict[str, Any],
    user_id: str,
    canvas: CanvasConfig,
    page_id: Optional[str] = None,
    style: Optional[Dict[str, Any]] = None,
    folder_ids: Optional[List[str]] = None,
    edit_mode: str = "PAGE",
    selected_elements: Optional[List[Dict[str, Any]]] = None,
    goal: Optional[str] = None,
    content_type: str = "informative",
    icon_set: str = "lucide",
    user_edit_scope: str = "page",
    template_id: Optional[str] = None,
    generate_page_fn=None,
    enhance_page_with_template_fn=None,
    generation_quality: str = "premium",
    pages_summary: Optional[List[Dict[str, Any]]] = None,
    deck_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Unified single-page orchestrator — classifies intent and routes to handler.
    Works for both presentations and printables via canvas config.
    """
    logger.info(f"🎯 [ORCHESTRATOR-{canvas.content_type}] Classifying: {instruction[:50]}...")

    page_elements = [e.get('type', 'unknown') for e in page_content.get('elements', [])]

    # Selected element summary for scope resolution
    selected_summary = ""
    if selected_elements:
        el_parts = []
        for el in selected_elements[:3]:
            et = el.get('type', 'unknown')
            txt = (el.get('text', '') or el.get('content', ''))[:80]
            el_parts.append(f"{et}: '{txt}'" if txt else et)
        selected_summary = "; ".join(el_parts)

    # Classification
    try:
        from services.parallel_classifier import classify_page_edit, classify_presentation_edit

        if canvas.content_type == "printable":
            classification = await classify_page_edit(
                user_message=instruction, page_summary=str(page_elements),
                mode="edit", user_id=user_id, edit_mode=edit_mode,
                selected_element_summary=selected_summary, user_edit_scope=user_edit_scope,
            )
        else:
            classification = await classify_presentation_edit(
                user_message=instruction, slide_elements=page_elements,
                mode="edit", user_id=user_id, edit_mode=edit_mode,
                selected_element_summary=selected_summary, user_edit_scope=user_edit_scope,
            )

        intent_map = {
            "greeting": "greeting", "help": "help", "create_new": "create_new",
            "edit_text": "simple_edit", "format": "simple_edit", "delete": "simple_edit",
            "add_content": "data_addition", "create_chart": "chart_request",
            "create_table": "data_addition", "create_image": "data_addition",
        }
        intent = intent_map.get(classification.action_type, "simple_edit")
        ai_message = classification.ai_message
        chart_type = classification.chart_type
        chart_query = classification.chart_query or instruction
        create_topic = classification.create_topic or ""
        resolved_scope = getattr(classification, 'resolved_scope', 'slide')
        scope_message = getattr(classification, 'scope_message', '')

    except Exception as e:
        logger.warning(f"🎯 [ORCHESTRATOR] Classification failed, defaulting to simple_edit: {e}")
        intent = "simple_edit"
        ai_message = ""
        chart_type = None
        chart_query = instruction
        create_topic = ""
        resolved_scope = "slide"
        scope_message = ""
        classification = None

    logger.info(f"🎯 [ORCHESTRATOR] Final intent={intent}, action_type={intent}, create_topic={create_topic[:60] if create_topic else 'N/A'}")

    # --- Greeting ---
    if intent == "greeting":
        return {"success": True, "intent": "message_only", "action_type": "message_only",
                "ai_message": ai_message or "Hello! I'm your AI assistant. I can edit pages, create charts, add content, and more!",
                "requires_vault": False}

    # --- Help ---
    if intent == "help":
        return {"success": True, "intent": "message_only", "action_type": "message_only",
                "ai_message": ai_message or "I can: edit text, change layouts, add charts, create new pages, transform elements, and enhance content from your vault!",
                "requires_vault": False}

    # --- Create new ---
    if intent == "create_new" and generate_page_fn:
        try:
            result = await generate_page_fn(instruction, create_topic, goal, content_type, style, user_id)
            new_page = result.get('PAGE', result.get('slide', {}))
            if 'backgroundColor' not in new_page:
                new_page['backgroundColor'] = page_content.get('backgroundColor', '#ffffff')
            return {"success": True, "action_type": "create_new",
                    "ai_message": ai_message or f"Created a new page about {create_topic}.",
                    f"new_{canvas.content_type == 'presentation' and 'slide' or 'PAGE'}": new_page,
                    "intent": "create_new"}
        except Exception as e:
            logger.error(f"❌ [ORCHESTRATOR] Create failed: {e}")
            raise

    # --- Edit/Chart intents ---
    # Use classifier's vault decision directly (no keyword overrides)
    requires_vault = classification.requires_vault if classification else True
    response_data = {
        "success": True, "intent": intent, "action_type": "edit",
        "requires_vault": requires_vault,
        "chart_type": chart_type, "chart_query": chart_query,
        "ai_message": ai_message,
    }

    try:
        sel_elements = selected_elements or []

        # Scope auto-escalation — only if user hasn't explicitly chosen element scope
        effective_mode = edit_mode
        if edit_mode in ['element', 'multi'] and sel_elements:
            if user_edit_scope != 'element' and resolved_scope in ['slide', 'all_relevant', 'global']:
                effective_mode = 'PAGE'
                response_data["scope_escalated"] = True
                response_data["scope_message"] = scope_message or "Your request applies to the full page."

        # Element-level editing
        _el_skip_vault = not (classification.requires_vault if classification else True)
        if effective_mode in ['element', 'multi'] and sel_elements:
            if len(sel_elements) == 1:
                result = await enhance_single_element(
                    element=sel_elements[0], instruction=instruction,
                    user_id=user_id, canvas=canvas, page_content=page_content,
                    style=style, folder_ids=folder_ids,
                    skip_vault=_el_skip_vault,
                    generation_quality=generation_quality,
                )
                if result.get("success"):
                    response_data["enhanced_element"] = result.get("enhanced_element")
                    response_data["intent"] = "element_edit"
                    response_data["ai_message"] = "Updated the selected element."
                elif result.get("error"):
                    response_data["ai_message"] = result.get("ai_message", result["error"])
            else:
                result = await enhance_multiple_elements(
                    elements=sel_elements, instruction=instruction,
                    user_id=user_id, canvas=canvas, page_content=page_content,
                    style=style, folder_ids=folder_ids,
                    skip_vault=_el_skip_vault,
                    generation_quality=generation_quality,
                )
                if result.get("success"):
                    response_data["enhanced_elements"] = result.get("enhanced_elements")
                    response_data["intent"] = "multi_edit"
                    response_data["ai_message"] = f"Updated {len(result.get('enhanced_elements', []))} elements."

        elif intent in ["simple_edit", "data_addition", "update_PAGE"]:
            if page_id:
                skip = not requires_vault
                structural = classification.is_structural if classification else False
                doc_outline = build_document_outline(pages_summary, page_id)
                if structural or not template_id:
                    result = await enhance_page_legacy(
                        page_content=page_content, instruction=instruction,
                        user_id=user_id, canvas=canvas, style=style,
                        folder_ids=folder_ids, skip_vault=skip,
                        goal=goal, content_type=content_type, icon_set=icon_set,
                        is_structural=structural,
                        document_outline=doc_outline,
                        deck_plan=deck_plan,
                    )
                elif template_id and enhance_page_with_template_fn:
                    result = await enhance_page_with_template_fn(
                        page_content=page_content, instruction=instruction,
                        user_id=user_id, canvas=canvas, style=style,
                        folder_ids=folder_ids, skip_vault=skip,
                        goal=goal, content_type=content_type,
                        template_id=template_id, icon_set=icon_set,
                    )
                else:
                    result = await enhance_page_legacy(
                        page_content=page_content, instruction=instruction,
                        user_id=user_id, canvas=canvas, style=style,
                        folder_ids=folder_ids, skip_vault=skip,
                        goal=goal, content_type=content_type, icon_set=icon_set,
                        is_structural=structural,
                        document_outline=doc_outline,
                        deck_plan=deck_plan,
                    )

                if result.get("success"):
                    response_data[canvas.enhanced_key] = result.get(canvas.enhanced_key)
                    response_data["ai_message"] = "Applied your changes." if intent == "simple_edit" else "Enhanced with vault data."

        elif intent == "chart_request":
            result = await generate_chart_data(
                chart_type=chart_type or "bar", query=chart_query,
                user_id=user_id, folder_ids=folder_ids,
            )
            if result.get("success"):
                response_data["chart_config"] = result.get("chart_config")
                response_data["ai_message"] = "Added a chart visualization."

    except HTTPException as he:
        detail_str = str(he.detail) if he.detail else str(he)
        if "insufficient_credits" in detail_str.lower() or "negative balance" in detail_str.lower():
            raise HTTPException(status_code=402, detail={
                "error": "insufficient_credits",
                "message": "Insufficient credits. Please purchase more."
            })
    except Exception as e:
        detail_str = str(e)
        if "insufficient_credits" in detail_str.lower() or "negative balance" in detail_str.lower():
            raise HTTPException(status_code=402, detail={
                "error": "insufficient_credits",
                "message": "Insufficient credits. Please purchase more."
            })
        logger.error(f"❌ [ORCHESTRATOR] Execution failed: {e}")

    return response_data


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrate Single Page Edit — Streaming
# ═══════════════════════════════════════════════════════════════════════════

async def orchestrate_edit_streaming(
    instruction: str,
    page_content: Dict[str, Any],
    user_id: str,
    canvas: CanvasConfig,
    page_id: Optional[str] = None,
    style: Optional[Dict[str, Any]] = None,
    folder_ids: Optional[List[str]] = None,
    edit_mode: str = "PAGE",
    selected_elements: Optional[List[Dict[str, Any]]] = None,
    goal: Optional[str] = None,
    content_type: str = "informative",
    icon_set: str = "lucide",
    user_edit_scope: str = "page",
    template_id: Optional[str] = None,
    generate_page_fn=None,
    enhance_page_with_template_fn=None,
    fast_path: Optional[str] = None,
    generation_quality: str = "premium",
    pages_summary: Optional[List[Dict[str, Any]]] = None,
    deck_plan: Optional[Dict[str, Any]] = None,
):
    """
    Streaming version of orchestrate_edit. Yields SSE events.
    Classification is non-streaming (fast), enhancement streams chunks.
    fast_path='layout_fix' skips all classification LLM calls and goes straight to page enhancement.
    """

    # ── FAST PATH: skip classification entirely for known intents ──
    if fast_path == 'layout_fix' and page_id:
        logger.info(f"⚡ [STREAM] fast_path=layout_fix — skipping classification, going direct to enhance")
        yield f"data: {json.dumps({'type': 'classification', 'intent': 'simple_edit', 'action_type': 'simple_edit', 'ai_message': ''})}\n\n"
        async for event in enhance_page_legacy_streaming(
            page_content=page_content, instruction=instruction,
            user_id=user_id, canvas=canvas, style=style,
            folder_ids=None, skip_vault=True,
            goal=goal, content_type=content_type, icon_set=icon_set,
            deck_plan=deck_plan,
        ):
            yield event
        return

    page_elements = [e.get('type', 'unknown') for e in page_content.get('elements', [])]

    selected_summary = ""
    if selected_elements:
        el_parts = []
        for el in selected_elements[:3]:
            et = el.get('type', 'unknown')
            txt = (el.get('text', '') or el.get('content', ''))[:80]
            el_parts.append(f"{et}: '{txt}'" if txt else et)
        selected_summary = "; ".join(el_parts)

    # Classification (non-streaming — fast)
    try:
        from services.parallel_classifier import classify_page_edit, classify_presentation_edit

        if canvas.content_type == "printable":
            classification = await classify_page_edit(
                user_message=instruction, page_summary=str(page_elements),
                mode="edit", user_id=user_id, edit_mode=edit_mode,
                selected_element_summary=selected_summary, user_edit_scope=user_edit_scope,
            )
        else:
            classification = await classify_presentation_edit(
                user_message=instruction, slide_elements=page_elements,
                mode="edit", user_id=user_id, edit_mode=edit_mode,
                selected_element_summary=selected_summary, user_edit_scope=user_edit_scope,
            )

        intent_map = {
            "greeting": "greeting", "help": "help", "create_new": "create_new",
            "edit_text": "simple_edit", "format": "simple_edit", "delete": "simple_edit",
            "add_content": "data_addition", "create_chart": "chart_request",
            "create_table": "data_addition", "create_image": "data_addition",
        }
        intent = intent_map.get(classification.action_type, "simple_edit")
        ai_message = classification.ai_message
        chart_type = classification.chart_type
        chart_query = classification.chart_query or instruction
        create_topic = classification.create_topic or ""
        resolved_scope = getattr(classification, 'resolved_scope', 'slide')
        scope_message = getattr(classification, 'scope_message', '')

    except Exception as e:
        logger.warning(f"🎯 [STREAM] Classification failed, defaulting to simple_edit: {e}")
        intent = "simple_edit"
        ai_message = ""
        chart_type = None
        chart_query = instruction
        create_topic = ""
        resolved_scope = "slide"
        scope_message = ""
        classification = None

    logger.info(f"🎯 [STREAM] Final intent={intent}, action_type={intent}")

    # Send classification event immediately
    yield f"data: {json.dumps({'type': 'classification', 'intent': intent, 'action_type': intent, 'ai_message': ai_message})}\n\n"

    # Non-edit intents → send result directly
    if intent in ("greeting", "help"):
        msg = ai_message or ("Hello! I'm your AI assistant." if intent == "greeting" else "I can edit text, layouts, add charts, and more!")
        yield f"data: {json.dumps({'type': 'result', 'data': {'success': True, 'intent': 'message_only', 'action_type': 'message_only', 'ai_message': msg}})}\n\n"
        return

    if intent == "create_new" and generate_page_fn:
        try:
            result = await generate_page_fn(instruction, create_topic, goal, content_type, style, user_id)
            new_page = result.get('PAGE', result.get('slide', {}))
            key = "new_slide" if canvas.content_type == "presentation" else "new_PAGE"
            yield f"data: {json.dumps({'type': 'result', 'data': {'success': True, 'action_type': 'create_new', key: new_page, 'intent': 'create_new', 'ai_message': ai_message or f'Created new page.'}})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        return

    # Scope auto-escalation — only if user hasn't explicitly chosen element scope
    effective_mode = edit_mode
    sel_elements = selected_elements or []
    scope_escalated = False
    if edit_mode in ['element', 'multi'] and sel_elements:
        if user_edit_scope != 'element' and resolved_scope in ['slide', 'all_relevant', 'global']:
            effective_mode = 'PAGE'
            scope_escalated = True

    # Element-level → non-streaming (small payloads, fast)
    if effective_mode in ['element', 'multi'] and sel_elements:
        try:
            _skip_vault = not (classification.requires_vault if classification else True)
            if len(sel_elements) == 1:
                result = await enhance_single_element(
                    element=sel_elements[0], instruction=instruction,
                    user_id=user_id, canvas=canvas, page_content=page_content,
                    style=style, folder_ids=folder_ids,
                    skip_vault=_skip_vault,
                    generation_quality=generation_quality,
                )
                if result.get("success"):
                    yield f"data: {json.dumps({'type': 'result', 'data': {'success': True, 'enhanced_element': result['enhanced_element'], 'intent': 'element_edit', 'ai_message': 'Updated element.'}})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'result', 'data': {'success': True, 'intent': 'element_edit', 'ai_message': result.get('ai_message', result.get('error', 'Failed'))}})}\n\n"
            else:
                result = await enhance_multiple_elements(
                    elements=sel_elements, instruction=instruction,
                    user_id=user_id, canvas=canvas, page_content=page_content,
                    style=style, folder_ids=folder_ids,
                    skip_vault=_skip_vault,
                    generation_quality=generation_quality,
                )
                if result.get("success"):
                    enhanced = result['enhanced_elements']
                    msg = f'Updated {len(enhanced)} elements.'
                    yield f"data: {json.dumps({'type': 'result', 'data': {'success': True, 'enhanced_elements': enhanced, 'intent': 'multi_edit', 'ai_message': msg}})}\n\n"
        except HTTPException as he:
            yield f"data: {json.dumps({'type': 'error', 'message': str(he.detail), 'status_code': he.status_code})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        return

    # Full page streaming enhancement
    if intent in ["simple_edit", "data_addition", "update_PAGE"] and page_id:
        requires_vault = classification.requires_vault if classification else True
        skip = not requires_vault
        structural = classification.is_structural if classification else False
        doc_outline = build_document_outline(pages_summary, page_id)

        if structural or not template_id:
            async for event in enhance_page_legacy_streaming(
                page_content=page_content, instruction=instruction,
                user_id=user_id, canvas=canvas, style=style,
                folder_ids=folder_ids, skip_vault=skip,
                goal=goal, content_type=content_type, icon_set=icon_set,
                is_structural=structural,
                document_outline=doc_outline,
                deck_plan=deck_plan,
            ):
                # Inject scope escalation info into the result event
                if scope_escalated and scope_message and '"type": "result"' in event:
                    try:
                        prefix = "data: "
                        json_str = event.strip().removeprefix(prefix).rstrip("\n")
                        parsed = json.loads(json_str)
                        if parsed.get("type") == "result" and isinstance(parsed.get("data"), dict):
                            parsed["data"]["scope_escalated"] = True
                            parsed["data"]["scope_message"] = scope_message
                            event = f"data: {json.dumps(parsed)}\n\n"
                    except Exception:
                        pass
                yield event
        else:
            # Template path — non-streaming fallback
            try:
                if enhance_page_with_template_fn:
                    result = await enhance_page_with_template_fn(
                        page_content=page_content, instruction=instruction,
                        user_id=user_id, canvas=canvas, style=style,
                        folder_ids=folder_ids, skip_vault=skip,
                        goal=goal, content_type=content_type,
                        template_id=template_id, icon_set=icon_set,
                    )
                else:
                    result = await enhance_page_legacy(
                        page_content=page_content, instruction=instruction,
                        user_id=user_id, canvas=canvas, style=style,
                        folder_ids=folder_ids, skip_vault=skip,
                        goal=goal, content_type=content_type, icon_set=icon_set,
                        is_structural=structural,
                        document_outline=doc_outline,
                        deck_plan=deck_plan,
                    )
                if result.get("success"):
                    result_data = {canvas.enhanced_key: result[canvas.enhanced_key], 'success': True, 'ai_message': 'Applied changes.'}
                    if scope_escalated and scope_message:
                        result_data['scope_escalated'] = True
                        result_data['scope_message'] = scope_message
                    yield f"data: {json.dumps({'type': 'result', 'data': result_data})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        return

    # Chart
    if intent == "chart_request":
        try:
            result = await generate_chart_data(
                chart_type=chart_type or "bar", query=chart_query,
                user_id=user_id, folder_ids=folder_ids,
            )
            if result.get("success"):
                yield f"data: {json.dumps({'type': 'result', 'data': {'success': True, 'chart_config': result['chart_config'], 'ai_message': 'Added chart.', 'intent': 'chart_request'}})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        return

    # Fallback
    yield f"data: {json.dumps({'type': 'result', 'data': {'success': True, 'intent': intent, 'ai_message': ai_message or 'No action taken.'}})}\n\n"


# ═══════════════════════════════════════════════════════════════════════════
# Document-Level Edit Planner (prevents redundancy across pages)
# ═══════════════════════════════════════════════════════════════════════════

async def plan_document_edits(
    instruction: str,
    relevant_indices: List[int],
    pages_summary: List[Dict[str, Any]],
    full_pages: List[Dict[str, Any]],
    user_id: str,
    goal: Optional[str] = None,
    content_type: str = "informative",
    is_update_all: bool = False,
    current_page_index: int = 0,
) -> Optional[Dict[int, str]]:
    """
    Document-level planning step that produces a unique edit instruction per slide/page.

    The AI sees the full document outline and the user's high-level instruction,
    then distributes the work across pages so that no content is repeated.

    Returns a dict mapping slide_index → specific_instruction, or None on failure
    (callers should fall back to using the raw instruction for all pages).
    """
    if len(relevant_indices) <= 1:
        return None  # Single page — no planning needed

    # Build a concise document outline for the planner
    outline_parts = []
    for idx in sorted(relevant_indices):
        s = pages_summary[idx] if idx < len(pages_summary) else {}
        full_text = extract_page_full_text(full_pages[idx]) if idx < len(full_pages) else s.get('text_summary', '')
        slide_topic = s.get('outline', '') or s.get('sectionTopic', '') or ''
        current_marker = " ⬅ USER IS VIEWING THIS SLIDE" if idx == current_page_index else ""
        outline_parts.append(
            f"Slide {idx + 1}{current_marker}: [Title: \"{s.get('title', 'Untitled')}\"] "
            f"Topic/Outline: \"{slide_topic}\". "
            f"Elements: {', '.join(s.get('element_types', []))}. "
            f"Current content: \"{full_text[:1000]}\""
        )

    # Build planner rules based on flow type
    if is_update_all:
        narrative_rule = "- Ensure edits across slides form a coherent narrative, but do NOT restrict the AI from rewriting content if the data demands it"
        image_desc_rule = "\n- IMAGE DESCRIPTIONS: When content changes, include a note in the instruction to update image descriptions to match the new content. Images are represented as image_placeholder elements with imageDescription fields. If the slide text/data changes, the image descriptions must change too so fresh relevant images are generated."
        constraint_examples = '(e.g. "do not change images", "keep images as-is", "only update text and data", "do not regenerate images", "preserve existing charts")'
    else:
        narrative_rule = "- Preserve the document's narrative flow and logical structure"
        image_desc_rule = ""
        constraint_examples = '(e.g. "only fix grammar", "only generate charts", "translate to French only", "do not change data", "just update formatting")'

    plan_prompt = f"""You are a document editor planner. The user's instruction applies to the DOCUMENT AS A WHOLE.
Your job is to produce a specific, unique edit instruction for EACH relevant slide/page so that the edits
are complementary and there is NO redundancy or repetition across pages.
The user is currently viewing Slide {current_page_index + 1} — if they say "this slide" or "this one", they mean that slide.

CRITICAL — PRESERVE USER CONSTRAINTS:
First, carefully read the USER INSTRUCTION below and extract ANY user constraints, preferences, or restrictions.
These are phrases that limit WHAT should or should NOT be changed {constraint_examples}.
Return these as "global_constraints" in your JSON output.
Every per-slide instruction MUST include these constraints verbatim. NEVER drop, summarize, or omit them.
If the user says "do not change images" then EVERY slide instruction must include "do not change images".

RULES:
- Distribute content/changes appropriately across slides so there is NO redundancy
- Each slide MUST get a UNIQUE, specific instruction reflecting its role in the document
- If a slide does not need changes for this instruction, set skip: true
{narrative_rule}
- Keep each per-slide instruction concise (1-3 sentences) BUT always append user constraints verbatim
- For formatting/style instructions (font, color, theme), give each slide the same formatting instruction — that is fine
- For CONTENT instructions, ensure each slide covers a DIFFERENT aspect or section{image_desc_rule}

DOCUMENT GOAL: {goal or 'N/A'}
DOCUMENT TYPE: {content_type}

USER INSTRUCTION: "{instruction}"

DOCUMENT OUTLINE:
{chr(10).join(outline_parts)}

Return a JSON object:
{{"global_constraints": "extracted user constraints/restrictions from the instruction, or empty string if none",
  "plan": [
  {{"slide_index": 0, "specific_instruction": "unique instruction for this slide + user constraints", "skip": false}},
  {{"slide_index": 1, "specific_instruction": "unique instruction for this slide + user constraints", "skip": false}},
  ...
]}}"""

    try:
        import json as _json
        max_tok = 10000
        resp = await asyncio.to_thread(llm_call,
            "", plan_prompt,
            user_id=user_id,
            max_tokens=max_tok, json_mode=True,
            reasoning_effort="low",
        )

        # Robust parser: handle both JSON arrays and objects
        plan = None
        text = resp.strip() if resp else ""
        # Remove markdown code blocks
        if "```" in text:
            text = re.sub(r'```json\n?', '', text)
            text = re.sub(r'```\w*\n?', '', text)
            text = text.replace('```', '').strip()
        # Try parsing full response first
        try:
            plan = _json.loads(text)
        except (ValueError, _json.JSONDecodeError):
            pass
        # Try finding a JSON array
        if plan is None:
            arr_start = text.find('[')
            arr_end = text.rfind(']')
            if arr_start != -1 and arr_end > arr_start:
                try:
                    plan = _json.loads(text[arr_start:arr_end + 1])
                except (ValueError, _json.JSONDecodeError):
                    pass
        # Try finding a JSON object
        if plan is None:
            obj_start = text.find('{')
            obj_end = text.rfind('}')
            if obj_start != -1 and obj_end > obj_start:
                try:
                    plan = _json.loads(text[obj_start:obj_end + 1])
                except (ValueError, _json.JSONDecodeError):
                    pass

        if plan is None:
            logger.warning(f"⚠️ [PLANNER] LLM returned unparseable plan, falling back. Raw response ({len(resp)} chars): {resp[:200]}")
            return None

        # Extract global constraints the LLM identified from the user instruction
        global_constraints = ""
        if isinstance(plan, dict):
            global_constraints = plan.get("global_constraints", "") or ""

        # Parse into a dict: slide_index → specific_instruction
        plan_map = {}
        entries = plan if isinstance(plan, list) else plan.get("plan", plan.get("edits", []))
        for entry in entries:
            idx = entry.get("slide_index")
            if idx is None or idx not in relevant_indices:
                continue
            if entry.get("skip", False):
                continue
            specific = entry.get("specific_instruction", "")
            if specific:
                plan_map[idx] = specific

        if not plan_map:
            logger.warning("⚠️ [PLANNER] Plan produced no actionable instructions, falling back")
            return None

        # Safety net: append global_constraints to any per-page instruction that doesn't already contain them
        if global_constraints:
            logger.info(f"🔒 [PLANNER] Global constraints: {global_constraints[:120]}")
            for idx in plan_map:
                if global_constraints.lower() not in plan_map[idx].lower():
                    plan_map[idx] = f"{plan_map[idx]}\nUSER CONSTRAINTS (MUST FOLLOW): {global_constraints}"

        # Always enforce user media preservation in edit-all mode
        if not is_update_all:
            um_constraint = "CRITICAL: Preserve ALL user-uploaded media elements (isUserMedia: true, src starting with '{{UserMedia_') exactly as received. Do not remove or modify them."
            for idx in plan_map:
                if "UserMedia" not in plan_map[idx]:
                    plan_map[idx] = f"{plan_map[idx]}\n{um_constraint}"

        logger.info(f"✅ [PLANNER] Generated plan for {len(plan_map)}/{len(relevant_indices)} pages")
        return plan_map

    except Exception as e:
        logger.error(f"❌ [PLANNER] Planning failed: {e}, falling back to raw instruction")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrate All Pages (with cross-page consistency)
# ═══════════════════════════════════════════════════════════════════════════

async def orchestrate_all_edits(
    instruction: str,
    pages_summary: List[Dict[str, Any]],
    full_pages: List[Dict[str, Any]],
    current_page_index: int,
    user_id: str,
    canvas: CanvasConfig,
    folder_ids: Optional[List[str]] = None,
    style: Optional[Dict[str, Any]] = None,
    goal: Optional[str] = None,
    content_type: str = "informative",
    icon_set: str = "lucide",
    generate_page_fn=None,
    is_update_all: bool = False,
    enhance_page_with_template_fn=None,
    deck_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Smart all-pages orchestrator with cross-page consistency enforcement.
    Uses sequential batches of 3 for consistency context passing.
    Routes template-based pages through template path for reliable JSON + layout preservation.
    """
    logger.info(f"🎯 [ALL-{canvas.content_type}] Instruction: {instruction[:80]}... | {len(pages_summary)} pages")

    _oss_call = llm_call  # module wrapper — pins large tier to the surface model (GLM-5.1)
    from services.parallel_classifier import _parse_json

    # Step 1: LLM-based intent classification (LLM — fast + cheap)
    intent_prompt = f"""Classify this "Edit All Pages" instruction into ONE category.

INSTRUCTION: "{instruction}"

CATEGORIES:
- "create_new": User wants to CREATE/ADD a brand new slide/page (e.g. "create a new slide about X", "add another page for Y")
- "global": User wants to UPDATE/MODIFY ALL existing pages uniformly (e.g. "update all slides with latest data", "change theme", "fix grammar everywhere", "refresh content")
- "specific": User wants to change specific content that may only affect some pages

IMPORTANT DISTINCTIONS:
- "Update all slides" / "refresh all pages" / "update with latest data" → global (modifying existing pages, NOT creating new ones)
- "Generate new descriptions" within an update context → global (it's updating existing content, not creating a new page)
- "Create a new slide about X" / "Add another page for Y" → create_new (explicitly requesting a NEW page)

Return JSON only: {{"intent": "create_new|global|specific", "new_slide_topic": "topic if create_new else empty string"}}"""

    try:
        intent_resp = await asyncio.to_thread(
            _oss_call, "", intent_prompt,
            user_id=user_id,
            max_tokens=4000,
            temperature=0.0,
        )
        intent_result = _parse_json(intent_resp, {"intent": "global", "new_slide_topic": ""})
    except Exception as e:
        logger.warning(f"⚠️ [ALL] Intent classification failed, defaulting to global: {e}")
        intent_result = {"intent": "global", "new_slide_topic": ""}

    detected_intent = intent_result.get("intent", "global")
    logger.info(f"🧠 [ALL] LLM intent: {detected_intent}")

    if detected_intent == "create_new":
        relevance = {"create_new": True, "is_global": False, "relevant_slides": [], "new_slide_topic": intent_result.get("new_slide_topic", "") or instruction}
    elif detected_intent == "global":
        relevance = {"create_new": False, "is_global": True, "relevant_slides": [{"slide_index": i} for i in range(len(full_pages))]}
    else:
        # "specific" — use llm to determine which pages are relevant
        pages_ctx_parts = []
        for i, s in enumerate(pages_summary):
            full_text = extract_page_full_text(full_pages[i]) if i < len(full_pages) else s.get('text_summary', '')
            slide_topic = s.get('outline', '') or s.get('sectionTopic', '') or ''
            pages_ctx_parts.append(
                f"{i+1}. [Title: \"{s.get('title', 'Untitled')}\"] Topic/Outline: \"{slide_topic}\". "
                f"Elements: {', '.join(s.get('element_types', []))}. Text: \"{full_text[:1000]}\""
            )

        relevance_prompt = f"""Given instruction and page summaries, determine which pages need modification.
The user chose "Edit All Pages" mode — err on INCLUDING more pages.

INSTRUCTION: "{instruction}"

PAGES:
{chr(10).join(pages_ctx_parts)}

RULES:
1. Mark pages containing relevant content; when in doubt INCLUDE
2. When unsure, INCLUDE the page

Return JSON: {{"relevant_slides": [{{"slide_index": 0}}]}}"""

        max_tok = max(500, len(pages_summary) * 20 + 100)
        try:
            resp = await asyncio.to_thread(llm_call,
                "", relevance_prompt,
                user_id=user_id, max_tokens=max_tok, json_mode=True,
                reasoning_effort="low",
            )
            relevance = _parse_json(resp, {
                "relevant_slides": [{"slide_index": i} for i in range(len(full_pages))],
            })
            relevance["create_new"] = False
            relevance["is_global"] = False
            if not relevance.get("relevant_slides"):
                relevance["is_global"] = True
                relevance["relevant_slides"] = [{"slide_index": i} for i in range(len(full_pages))]
        except Exception as e:
            logger.error(f"❌ [ALL] Relevance classification failed: {e}")
            relevance = {"relevant_slides": [{"slide_index": i} for i in range(len(full_pages))], "create_new": False, "is_global": True}

    # Step 2: Handle CREATE_NEW
    if relevance.get("create_new") and generate_page_fn:
        topic = relevance.get("new_slide_topic", "") or instruction
        try:
            result = await generate_page_fn(instruction, topic, goal, content_type, style, user_id)
            new_page = result.get('PAGE', result.get('slide', {}))
            return {
                "success": True,
                "edits": [{"slide_index": -1, "action": "create", "slide_data": new_page}],
                "total_matched": 0, "total_slides": len(full_pages),
                "intent": "create_new", "ai_message": f"Created a new page about {topic}."
            }
        except Exception as e:
            raise

    # Step 3: Determine relevant pages
    relevant_indices = set()
    if relevance.get("is_global"):
        relevant_indices = set(range(len(full_pages)))
    else:
        for r in relevance.get("relevant_slides", []):
            idx = r.get("slide_index", 0)
            if 0 <= idx < len(full_pages):
                relevant_indices.add(idx)
    if not relevant_indices:
        relevant_indices = set(range(len(full_pages)))

    logger.info(f"🎯 [ALL] Editing {len(relevant_indices)} of {len(full_pages)} pages")

    # Classify intent for vault decision
    try:
        from services.parallel_classifier import classify_page_edit
        classification = await classify_page_edit(
            user_message=instruction,
            page_summary=str([e.get('type', 'unknown') for e in full_pages[current_page_index].get('elements', [])]),
            mode="edit", user_id=user_id, edit_mode='PAGE', user_edit_scope='all',
        )
        intent_map = {
            "greeting": "greeting", "help": "help", "create_new": "create_new",
            "edit_text": "simple_edit", "format": "simple_edit", "delete": "simple_edit",
            "add_content": "data_addition", "create_chart": "chart_request",
            "create_table": "data_addition", "create_image": "data_addition",
        }
        intent = intent_map.get(classification.action_type, "simple_edit")
    except Exception:
        intent = "simple_edit"
        classification = None
    skip_vault = not (classification.requires_vault if classification else True)

    # Step 4: Document-level planning — produce per-slide specific instructions
    sorted_indices = sorted(relevant_indices)
    edit_plan = await plan_document_edits(
        instruction=instruction,
        relevant_indices=sorted_indices,
        pages_summary=pages_summary,
        full_pages=full_pages,
        user_id=user_id,
        goal=goal,
        content_type=content_type,
        is_update_all=is_update_all,
        current_page_index=current_page_index,
    )
    if edit_plan:
        # Remove skipped pages (planner may have dropped some)
        sorted_indices = [idx for idx in sorted_indices if idx in edit_plan]
        logger.info(f"📋 [ALL] Planner produced {len(edit_plan)} unique instructions, {len(sorted_indices)} pages to edit")

    # Step 5: Edit pages in sequential batches of 3 for cross-page consistency
    batch_size = 3
    edits = []
    consistency_context = ""  # Accumulated from previous batches
    doc_outline = build_document_outline(pages_summary)

    # ── Prefetch structured data once for all pages ──
    prefetched_structured_data = None
    if not skip_vault and folder_ids:
        try:
            from composer_query import prefetch_structured_data_context
            prefetched_structured_data = await prefetch_structured_data_context(
                user_id=user_id, goal=instruction, folder_ids=folder_ids,
            )
            if prefetched_structured_data:
                logger.info(f"📊 [ALL] Prefetched structured data: {len(prefetched_structured_data)} chars")
        except Exception as e:
            logger.warning(f"📊 [ALL] Structured data prefetch failed: {e}")

    for batch_start in range(0, len(sorted_indices), batch_size):
        batch_indices = sorted_indices[batch_start:batch_start + batch_size]

        semaphore = asyncio.Semaphore(3)

        async def edit_page(idx):
            async with semaphore:
                page = full_pages[idx]
                page_id = page.get('id') or pages_summary[idx].get('slide_id', f'page_{idx}')

                # Use per-slide instruction from planner if available, else raw instruction
                base_instruction = edit_plan.get(idx, instruction) if edit_plan else instruction

                # Inject consistency context into instruction for batch 2+
                effective_instruction = base_instruction
                if consistency_context:
                    effective_instruction = f"{base_instruction}\n\nCONSISTENCY (apply same style/decisions as previous pages):\n{consistency_context}"

                try:
                    # Route: template path if page has a template and fn is available
                    page_template_id = page.get("template")
                    if page_template_id and enhance_page_with_template_fn:
                        logger.info(f"✨ [ALL] Page {idx} → template path ({page_template_id})")
                        result = await enhance_page_with_template_fn(
                            page_content=page, instruction=effective_instruction,
                            user_id=user_id, canvas=canvas, style=style,
                            folder_ids=folder_ids, skip_vault=skip_vault,
                            goal=goal, content_type=content_type,
                            template_id=page_template_id, icon_set=icon_set,
                            is_update_all=is_update_all,
                        )
                    else:
                        result = await enhance_page_legacy(
                            page_content=page, instruction=effective_instruction,
                            user_id=user_id, canvas=canvas, style=style,
                            folder_ids=folder_ids, skip_vault=skip_vault,
                            goal=goal, content_type=content_type, icon_set=icon_set,
                            is_update_all=is_update_all,
                            document_outline=doc_outline,
                            prefetched_structured_data=prefetched_structured_data,
                            deck_plan=deck_plan,
                        )
                    if result.get("success"):
                        return {"slide_index": idx, "action": "update",
                                "slide_data": result.get(canvas.enhanced_key)}
                except HTTPException as he:
                    if he.status_code == 402:
                        raise
                    logger.error(f"❌ [ALL] Page {idx} failed: {he.detail}")
                except Exception as e:
                    logger.error(f"❌ [ALL] Page {idx} failed: {e}")
                return None

        tasks = [edit_page(idx) for idx in batch_indices]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, HTTPException):
                raise r
            if isinstance(r, Exception):
                continue
            if r is not None:
                edits.append(r)

        # Build consistency context from this batch for next batch
        if edits and batch_start + batch_size < len(sorted_indices):
            # Extract decisions from completed edits in this batch
            batch_edits = [e for e in edits if e["slide_index"] in batch_indices]
            decisions = []
            for edit in batch_edits:
                sd = edit.get("slide_data", {})
                bg = sd.get("backgroundColor", "")
                if bg:
                    decisions.append(f"bg={bg}")
                # Extract style patterns from the first text element
                for el in sd.get("elements", [])[:2]:
                    if el.get("type") == "text":
                        fs = el.get("fontSize", "")
                        fc = el.get("fill", el.get("color", ""))
                        if fs or fc:
                            decisions.append(f"text: fs={fs} color={fc}")
                        break
            if decisions:
                consistency_context = "; ".join(decisions[:5])

    success_count = len(edits)
    fail_count = len(sorted_indices) - success_count
    ai_msg = (f"Updated {success_count} of {len(sorted_indices)} relevant pages (out of {len(full_pages)} total)."
              if fail_count == 0 else f"Updated {success_count} pages. {fail_count} failed.")

    return {
        "success": True, "edits": edits,
        "total_matched": len(relevant_indices), "total_slides": len(full_pages),
        "intent": intent, "ai_message": ai_msg,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrate All Pages — Streaming
# ═══════════════════════════════════════════════════════════════════════════

async def orchestrate_all_edits_streaming(
    instruction: str,
    pages_summary: List[Dict[str, Any]],
    full_pages: List[Dict[str, Any]],
    current_page_index: int,
    user_id: str,
    canvas: CanvasConfig,
    folder_ids: Optional[List[str]] = None,
    style: Optional[Dict[str, Any]] = None,
    goal: Optional[str] = None,
    content_type: str = "informative",
    icon_set: str = "lucide",
    generate_page_fn=None,
    is_update_all: bool = False,
    enhance_page_with_template_fn=None,
    outline_changed: bool = False,
    auto_match_template_fn=None,
    deck_plan: Optional[Dict[str, Any]] = None,
):
    """Streaming version of orchestrate_all_edits. Yields per-page progress + results."""
    logger.info(f"🎯 [ALL-STREAM-{canvas.content_type}] {instruction[:60]}... | {len(full_pages)} pages")

    _oss_call = llm_call  # module wrapper — pins large tier to the surface model (GLM-5.1)
    from services.parallel_classifier import _parse_json

    new_slide_topic = ""

    # ── Step 1: LLM-based intent classification (LLM) ──
    # Replaces fragile regex patterns with a fast, cheap LLM call
    intent_prompt = f"""Classify this "Edit All Pages" instruction into ONE category.

INSTRUCTION: "{instruction}"

CATEGORIES:
- "create_new": User wants to CREATE/ADD a brand new slide/page (e.g. "create a new slide about X", "add another page for Y")
- "global": User wants to UPDATE/MODIFY ALL existing pages uniformly (e.g. "update all slides with latest data", "change theme", "fix grammar everywhere", "translate to French", "refresh content")
- "specific": User wants to change specific content that may only affect some pages

IMPORTANT DISTINCTIONS:
- "Update all slides" / "refresh all pages" / "update with latest data" → global (modifying existing pages, NOT creating new ones)
- "Generate new descriptions" within an update context → global (it's updating existing content, not creating a new page)
- "Create a new slide about X" / "Add another page for Y" → create_new (explicitly requesting a NEW page)

Return JSON only: {{"intent": "create_new|global|specific", "new_slide_topic": "topic if create_new else empty string"}}"""

    try:
        intent_resp = await asyncio.to_thread(
            _oss_call, "", intent_prompt,
            user_id=user_id,
            max_tokens=4000,
            temperature=0.0,
        )
        intent_result = _parse_json(intent_resp, {"intent": "global", "new_slide_topic": ""})
    except Exception as e:
        logger.warning(f"⚠️ [ALL-STREAM] Intent classification failed, defaulting to global: {e}")
        intent_result = {"intent": "global", "new_slide_topic": ""}

    detected_intent = intent_result.get("intent", "global")
    new_slide_topic = intent_result.get("new_slide_topic", "") or ""
    logger.info(f"🧠 [ALL-STREAM] LLM intent: {detected_intent} | topic: {new_slide_topic[:60]}")

    # ── Step 2: Resolve indices based on intent ──
    is_global = False
    if detected_intent == "create_new":
        relevant_indices = set()
        is_create = True
        new_slide_topic = new_slide_topic or instruction
    elif detected_intent == "global":
        relevant_indices = set(range(len(full_pages)))
        is_create = False
        is_global = True
    else:
        # "specific" — use LLM to determine which pages are relevant
        is_create = False
        pages_ctx_parts = []
        for i, s in enumerate(pages_summary):
            full_text = extract_page_full_text(full_pages[i]) if i < len(full_pages) else s.get('text_summary', '')
            slide_topic = s.get('outline', '') or s.get('sectionTopic', '') or ''
            pages_ctx_parts.append(
                f"{i+1}. [Title: \"{s.get('title', 'Untitled')}\"] Topic/Outline: \"{slide_topic}\". "
                f"Elements: {', '.join(s.get('element_types', []))}. Text: \"{full_text[:1000]}\""
            )

        rel_prompt = f"""Given instruction and page summaries, determine which pages need modification.
The user chose "Edit All Pages" mode — err on INCLUDING more pages.

INSTRUCTION: "{instruction}"

PAGES:
{chr(10).join(pages_ctx_parts)}

RULES:
1. Mark pages containing relevant content; when in doubt INCLUDE
2. When unsure, INCLUDE the page

Return JSON: {{"relevant_slides": [{{"slide_index": 0}}]}}"""

        max_tok = max(500, len(pages_summary) * 20 + 100)
        try:
            resp = await asyncio.to_thread(llm_call, "", rel_prompt, user_id=user_id, max_tokens=max_tok, json_mode=True, reasoning_effort="low")
            rel = _parse_json(resp, {"relevant_slides": [{"slide_index": i} for i in range(len(full_pages))]})
        except Exception:
            rel = {"relevant_slides": [{"slide_index": i} for i in range(len(full_pages))]}

        relevant_indices = {r["slide_index"] for r in rel.get("relevant_slides", []) if 0 <= r.get("slide_index", -1) < len(full_pages)}
        if not relevant_indices:
            relevant_indices = set(range(len(full_pages)))

    yield f"data: {json.dumps({'type': 'classification', 'total_pages': len(full_pages), 'relevant_count': len(relevant_indices), 'is_create': is_create})}\n\n"

    # Handle create
    if is_create and generate_page_fn:
        topic = new_slide_topic or instruction
        try:
            result = await generate_page_fn(instruction, topic, goal, content_type, style, user_id)
            new_page = result.get('PAGE', result.get('slide', {}))
            yield f"data: {json.dumps({'type': 'result', 'data': {'success': True, 'edits': [{'slide_index': -1, 'action': 'create', 'slide_data': new_page}], 'intent': 'create_new', 'ai_message': f'Created new page about {topic[:80]}.'}})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        return

    # Classify intent
    try:
        from services.parallel_classifier import classify_page_edit
        cls = await classify_page_edit(user_message=instruction, page_summary="", mode="edit", user_id=user_id, edit_mode='PAGE', user_edit_scope='all')
        skip_vault = not (cls.requires_vault if cls else True)
    except Exception:
        skip_vault = False  # Safe default: fetch vault

    sorted_idx = sorted(relevant_indices)

    # Document-level planning — produce per-slide specific instructions
    edit_plan = await plan_document_edits(
        instruction=instruction,
        relevant_indices=sorted_idx,
        pages_summary=pages_summary,
        full_pages=full_pages,
        user_id=user_id,
        goal=goal,
        content_type=content_type,
        is_update_all=is_update_all,
        current_page_index=current_page_index,
    )
    if edit_plan:
        sorted_idx = [idx for idx in sorted_idx if idx in edit_plan]
        logger.info(f"📋 [ALL-STREAM] Planner produced {len(edit_plan)} unique instructions")

    # ── Prefetch structured data once for all pages ──
    prefetched_structured_data = None
    if not skip_vault and folder_ids:
        try:
            from composer_query import prefetch_structured_data_context
            prefetched_structured_data = await prefetch_structured_data_context(
                user_id=user_id, goal=instruction, folder_ids=folder_ids,
            )
            if prefetched_structured_data:
                logger.info(f"📊 [ALL-STREAM] Prefetched structured data: {len(prefetched_structured_data)} chars")
        except Exception as e:
            logger.warning(f"📊 [ALL-STREAM] Structured data prefetch failed: {e}")

    edits = []
    consistency_ctx = ""
    batch_size = 5
    doc_outline = build_document_outline(pages_summary)

    for batch_start in range(0, len(sorted_idx), batch_size):
        batch = sorted_idx[batch_start:batch_start + batch_size]
        sem = asyncio.Semaphore(5)

        async def do_edit(idx):
            async with sem:
                yield_idx = idx
                page = full_pages[idx]
                base_instr = edit_plan.get(idx, instruction) if edit_plan else instruction
                eff_instr = f"{base_instr}\n\nCONSISTENCY:\n{consistency_ctx}" if consistency_ctx else base_instr
                try:
                    # Route: template path if page has a template and fn is available
                    page_template_id = page.get("template")

                    # Re-match template when outlines have changed (e.g. user regenerated outlines in Update All)
                    if outline_changed and auto_match_template_fn and enhance_page_with_template_fn:
                        page_title = page.get("title", "")
                        page_outline = page.get("outline", "")
                        page_layout = page.get("layout", "")
                        page_image_prompt = ""
                        # Extract image_prompt from elements if available
                        for el in page.get("elements", []):
                            if el.get("type") == "image_placeholder" and el.get("imageDescription"):
                                page_image_prompt = el["imageDescription"]
                                break
                        re_matched = auto_match_template_fn(
                            page_title or page_outline or "Content",
                            page_outline or base_instr,
                            idx,
                            len(full_pages),
                            layout=page_layout,
                            image_prompt=page_image_prompt,
                        )
                        if re_matched:
                            logger.info(f"🔄 [ALL-STREAM] Page {idx} template re-matched: {page_template_id} → {re_matched}")
                            page_template_id = re_matched

                    if page_template_id and enhance_page_with_template_fn:
                        logger.info(f"✨ [ALL-STREAM] Page {idx} → template path ({page_template_id})")
                        result = await enhance_page_with_template_fn(
                            page_content=page, instruction=eff_instr,
                            user_id=user_id, canvas=canvas, style=style,
                            folder_ids=folder_ids, skip_vault=skip_vault,
                            goal=goal, content_type=content_type,
                            template_id=page_template_id, icon_set=icon_set,
                            is_update_all=is_update_all,
                        )
                    else:
                        result = await enhance_page_legacy(
                            page_content=page, instruction=eff_instr,
                            user_id=user_id, canvas=canvas, style=style,
                            folder_ids=folder_ids, skip_vault=skip_vault,
                            goal=goal, content_type=content_type, icon_set=icon_set,
                            is_update_all=is_update_all,
                            document_outline=doc_outline,
                            prefetched_structured_data=prefetched_structured_data,
                            deck_plan=deck_plan,
                        )
                    if result.get("success"):
                        return {"slide_index": idx, "action": "update", "slide_data": result.get(canvas.enhanced_key)}
                except HTTPException as he:
                    if he.status_code == 402: raise
                except Exception as e:
                    logger.error(f"❌ [ALL-STREAM] Page {idx} failed: {e}")
                return None

        # Progress events
        for idx in batch:
            yield f"data: {json.dumps({'type': 'progress', 'page_index': idx, 'total': len(sorted_idx), 'status': 'editing'})}\n\n"

        tasks = [do_edit(idx) for idx in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, HTTPException):
                yield f"data: {json.dumps({'type': 'error', 'message': str(r.detail), 'status_code': r.status_code})}\n\n"
                return
            if isinstance(r, Exception):
                continue
            if r is not None:
                edits.append(r)
                yield f"data: {json.dumps({'type': 'page_result', 'page_index': r['slide_index'], 'slide_data': r['slide_data']})}\n\n"

        # Build consistency from batch
        if edits:
            batch_edits = [e for e in edits if e["slide_index"] in batch]
            decisions = []
            for ed in batch_edits:
                bg = ed.get("slide_data", {}).get("backgroundColor", "")
                if bg:
                    decisions.append(f"bg={bg}")
            if decisions:
                consistency_ctx = "; ".join(decisions[:5])

    success = len(edits)
    fail = len(sorted_idx) - success
    msg = f"Updated {success} of {len(sorted_idx)} pages." if fail == 0 else f"Updated {success} pages. {fail} failed."
    yield f"data: {json.dumps({'type': 'complete', 'edits_count': success, 'summary': msg})}\n\n"
