"""
Parallel Intent Classifier for Maximum Speed
=============================================

This module splits classification into parallel AI calls,
each with a focused small prompt for faster processing.

Instead of ONE heavy call doing everything:
  - Intent classification
  - Data requirement check  

We run TWO lightweight parallel calls:
  1. Intent Call (~500 tokens) → action_type, scope
  2. Data Call (~200 tokens) → requires_data: bool

Benefits:
  - Each call processes fewer tokens → faster response
  - Parallel execution → total time ≈ slowest single call

Note: SaaS data source selection has been removed.
      SaaS data is now pre-embedded in Milvus and retrieved via semantic search.
      See services/source_provider.py for the new unified retrieval approach.
"""

import asyncio
import json
import logging
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Result from parallel classification"""
    # Intent classification
    intent: str = "edit"
    action_type: str = "edit_text"
    scope: str = "full"
    confidence: float = 0.8
    
    # Resolved scope (agentic scope intelligence)
    # Determines what the user ACTUALLY intended regardless of UI selection
    # Values: 'element', 'slide', 'all_relevant', 'global', 'new_content'
    resolved_scope: str = "slide"
    scope_message: str = ""  # Explanation if scope was auto-escalated
    
    # Structural change detection (layout/card/column/grid changes)
    is_structural: bool = False
    
    # Data requirements
    requires_data: bool = True  # Default True (safe)
    requires_vault: bool = True
    requires_image: bool = False
    
    # Additional info
    ai_message: str = ""
    clarification_needed: Optional[str] = None
    chart_type: Optional[str] = None
    chart_query: Optional[str] = None
    create_topic: Optional[str] = None


async def parallel_classify(
    user_message: str,
    context_summary: str,
    context_type: str = "page",  # "page", "presentation", "diagram"
    user_id: str = None,
    edit_mode: str = "slide",  # Frontend edit mode: 'slide'/'PAGE'/'element'/'multi'/'selection'/'overall'
    selected_element_summary: str = "",  # Brief description of selected element(s)
    user_edit_scope: str = "page"  # Frontend radio: 'element', 'page', 'all'
) -> ClassificationResult:
    """
    Run parallel classification calls for maximum speed.
    
    Args:
        user_message: User's request/instruction
        context_summary: Brief summary of current content (page/slide/diagram)
        context_type: Type of content being edited
        user_id: User ID for logging
        
    Returns:
        ClassificationResult with all routing decisions
    """
    from llm_oss import llm_call
    
    logger.info(f"⚡ [PARALLEL] Starting parallel classification for: {user_message[:50]}...")
    
    # === DEFINE PARALLEL TASKS ===
    
    async def classify_scope() -> dict:
        """Small focused call for scope resolution — determines what user ACTUALLY intends"""
        selection_ctx = ""
        if selected_element_summary:
            selection_ctx = f"\nCURRENTLY SELECTED: {selected_element_summary}"
        
        prompt = f"""Determine the TRUE scope of this editing request.

REQUEST: "{user_message}"
UI EDIT MODE: {edit_mode} (what user has selected in UI)
UI SCOPE SETTING: {user_edit_scope} (radio button choice: element/page/all){selection_ctx}
CONTENT CONTEXT: {context_summary[:300]}

Determine the user's TRUE intent:
- "element": User wants to edit ONLY the selected element (e.g. "make this bold", "change this text to...")
- "slide": User wants to edit the current page/slide (e.g. "add a chart", "change the layout")
- "all_relevant": User wants to edit specific content across multiple pages (e.g. "update Q3 revenue", "fix grammar everywhere")
- "global": User wants to apply a change to ALL pages (e.g. "change the theme", "change font to Arial", "add logo")
- "new_content": User wants to CREATE new page/slide (e.g. "create a new slide about...", "add a summary page")

IMPORTANT:
- If an element is selected but the request doesn't relate to that element, escalate to "slide" or broader
- If user says "create new" anything, always return "new_content"
- "Fix grammar" or "fix typos" across all = "all_relevant", not "global" (only text content is affected)
- "Change theme/font/colors" = "global" (affects all slides uniformly)

Return JSON only:
{{"resolved_scope": "element|slide|all_relevant|global|new_content", "scope_message": "brief explanation if scope differs from UI selection"}}"""
        
        try:
            response = await asyncio.to_thread(
                llm_call, "", prompt,
                user_id=user_id,
                max_tokens=4000
            )
            return _parse_json(response, {"resolved_scope": "slide", "scope_message": ""})
        except Exception as e:
            logger.warning(f"⚡ [PARALLEL] Scope call failed: {e}")
            return {"resolved_scope": "slide", "scope_message": ""}
    
    async def classify_intent() -> dict:
        """Small focused call for intent/action classification + structural detection"""
        prompt = f"""Classify this {context_type} editing request into ONE action type and detect if it requires structural/layout changes.

REQUEST: "{user_message}"

CURRENT {context_type.upper()}: {context_summary[:500]}

ACTION TYPES:
- greeting: Just saying hi/thanks
- help: Asking what you can do
- chat_only: Question/discussion, no edits needed
- edit_text: Modify existing text (rewrite, translate, shorten)
- add_content: Add paragraphs/details to the CURRENT page (expand existing content in-place)
- create_chart: Add visualization/chart
- create_image: Generate AI image
- create_table: Add table
- delete: Remove content
- format: Change styling/layout
- create_new: Create a NEW page/slide/section in the document (adds a separate page, NOT in-place)

DECISION GUIDE for add_content vs create_new:
- "Add a new section titled X" → create_new (separate page)
- "Add a new page about X" / "Add another page for Y" → create_new
- "Create a section for X" / "Create a page about X" → create_new
- "new section", "new page", "new slide", "new report" → ALWAYS create_new
- "add a section", "add section", "create a section", "add a new", "create a new" → create_new
- "Expand on this topic" → add_content (in-place)
- "Add more details about X" → add_content (in-place)
- "Add bullet points" / "Add a paragraph" → add_content (in-place on current page)

STRUCTURAL CHANGE DETECTION (is_structural):
is_structural=true means the request changes the PAGE LAYOUT or ELEMENT ARRANGEMENT:
- Layout changes: "change to 3 cards", "split into columns", "convert to grid", "side by side"
- Adding/removing structural elements: "add a card", "remove a section", "more cards", "fewer cards"
- Reorganization: "rearrange", "restructure", "reorganize", "different layout", "redesign"
- Template transformations: "convert to", "transform to", "turn into", "make it a timeline"
- Process/layout types: "timeline", "comparison", "bullet list", "steps", "process"
is_structural=false for:
- Text edits, color/font changes, content updates, data additions, grammar fixes
- "Make the title bold" → false (formatting, not layout)
- "Change background color" → false (styling)

Return JSON only:
{{"action_type": "...", "scope": "full|selected", "confidence": 0.0-1.0, "ai_message": "brief response", "is_structural": true/false}}"""
        
        try:
            response = await asyncio.to_thread(
                llm_call, "", prompt, 
                user_id=user_id,
                max_tokens=4000
            )
            return _parse_json(response, {"action_type": "edit_text", "scope": "full", "confidence": 0.5})
        except Exception as e:
            logger.warning(f"⚡ [PARALLEL] Intent call failed: {e}")
            return {"action_type": "edit_text", "scope": "full", "confidence": 0.3}
    
    async def classify_data_need() -> dict:
        """Tiny call to determine if external data is needed"""
        prompt = f"""Does this request need external data lookup, or can it be done with just the current content?

REQUEST: "{user_message}"

NO DATA NEEDED (requires_data: false):
- Formatting/styling changes
- Deleting/removing content
- Reordering/reorganizing
- Simple text edits (grammar, shorten, rewrite, translate)
- Greetings/help questions
- Layout/structural changes (cards, columns, grids)

DATA NEEDED (requires_data: true):
- Adding new information
- Creating charts from data
- Research-based content
- "Add stats about...", "Include data..."
- UPDATE/REFRESH requests: "update", "refresh", "sync", "latest", "newest", "current", "recent", "new data", "fresh data", "latest data" → ALWAYS requires_data=true (user wants the latest data from their vault)
- Expanding or elaborating on content

CRITICAL: If the request contains words like "update", "refresh", "sync", "latest", "newest", "current data", "recent" — ALWAYS return requires_data=true. The user wants their content refreshed with the latest data.

Return JSON only: {{"requires_data": true/false, "requires_image": true/false}}"""
        
        try:
            response = await asyncio.to_thread(
                llm_call, "", prompt,
                user_id=user_id,
                max_tokens=4000
            )
            return _parse_json(response, {"requires_data": False, "requires_image": False})
        except Exception as e:
            logger.warning(f"⚡ [PARALLEL] Data-need call failed: {e}")
            return {"requires_data": False, "requires_image": False}  # Safe default: don't penalize simple edits
    
    # === RUN IN PARALLEL ===
    tasks = [classify_intent(), classify_data_need(), classify_scope()]
    logger.info(f"⚡ [PARALLEL] Running 3 parallel calls (intent + data + scope)")
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # === AGGREGATE RESULTS ===
    intent_result = results[0] if not isinstance(results[0], Exception) else {}
    data_result = results[1] if not isinstance(results[1], Exception) else {}
    scope_result = results[2] if not isinstance(results[2], Exception) else {}
    
    action_type = intent_result.get("action_type", "edit_text")
    
    # Resolve scope
    resolved_scope = scope_result.get("resolved_scope", "slide")
    scope_message = scope_result.get("scope_message", "")
    
    # Override scope if action_type implies it
    if action_type == "create_new":
        resolved_scope = "new_content"
    elif action_type in ["greeting", "help", "chat_only"]:
        resolved_scope = "slide"  # Doesn't matter for non-edit intents
    
    # Build final result
    result = ClassificationResult(
        intent=action_type,
        action_type=action_type,
        scope=intent_result.get("scope", "full"),
        confidence=intent_result.get("confidence", 0.5),
        resolved_scope=resolved_scope,
        scope_message=scope_message,
        is_structural=intent_result.get("is_structural", False),
        
        requires_data=data_result.get("requires_data", False),
        requires_vault=data_result.get("requires_data", False),  # Vault = data need
        requires_image=data_result.get("requires_image", False),
        ai_message=intent_result.get("ai_message", ""),
        chart_type=intent_result.get("chart_type"),
        chart_query=intent_result.get("chart_query"),
        create_topic=intent_result.get("create_topic")
    )
    
    # Override requires_data for non-edit intents
    if action_type in ["greeting", "help", "chat_only"]:
        result.requires_data = False
        result.requires_vault = False
    
    logger.info(f"⚡ [PARALLEL] Classification complete: action={result.action_type}, "
                f"requires_data={result.requires_data}, resolved_scope={result.resolved_scope}, "
                f"is_structural={result.is_structural}")
    
    return result


def _parse_json(response: str, default: dict):
    """Robust JSON extraction from AI response (objects and arrays)"""
    text = response.strip()
    
    # Remove markdown code blocks
    if "```" in text:
        text = re.sub(r'```json\n?', '', text)
        text = re.sub(r'```\w*\n?', '', text)
        text = text.replace('```', '').strip()
    
    # Find JSON array first (for prompts that request arrays)
    try:
        arr_start = text.find('[')
        arr_end = text.rfind(']')
        obj_start = text.find('{')
        # If '[' appears before '{', try parsing as array
        if arr_start != -1 and arr_end > arr_start and (obj_start == -1 or arr_start < obj_start):
            return json.loads(text[arr_start:arr_end + 1])
    except json.JSONDecodeError:
        pass
    
    # Find JSON object
    try:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        pass
    
    return default


# ==================== CONTEXT TYPE SPECIFIC HELPERS ====================

async def classify_page_edit(
    user_message: str,
    page_summary: str,
    mode: str,
    user_id: str = None,
    edit_mode: str = "PAGE",
    selected_element_summary: str = "",
    user_edit_scope: str = "page"
) -> ClassificationResult:
    """Parallel classification for page edits"""
    context = f"Mode: {mode}\nPage: {page_summary}"
    return await parallel_classify(
        user_message=user_message,
        context_summary=context,
        context_type="page",
        user_id=user_id,
        edit_mode=edit_mode,
        selected_element_summary=selected_element_summary,
        user_edit_scope=user_edit_scope
    )


async def classify_presentation_edit(
    user_message: str,
    slide_elements: List[str],
    mode: str = "edit",
    user_id: str = None,
    edit_mode: str = "slide",
    selected_element_summary: str = "",
    user_edit_scope: str = "page"
) -> ClassificationResult:
    """Parallel classification for presentation edits"""
    context = f"Mode: {mode}\nSlide elements: {', '.join(slide_elements)}"
    return await parallel_classify(
        user_message=user_message,
        context_summary=context,
        context_type="presentation",
        user_id=user_id,
        edit_mode=edit_mode,
        selected_element_summary=selected_element_summary,
        user_edit_scope=user_edit_scope
    )


async def classify_diagram_edit(
    user_message: str,
    diagram_type: str,
    diagram_summary: str,
    user_id: str = None
) -> ClassificationResult:
    """Parallel classification for diagram edits"""
    context = f"Diagram type: {diagram_type}\nContent: {diagram_summary}"
    return await parallel_classify(
        user_message=user_message,
        context_summary=context,
        context_type="diagram",
        user_id=user_id
    )


async def classify_report_edit(
    user_message: str,
    edit_mode: str,
    content_preview: str,
    selected_text: Optional[str] = None,
    user_id: str = None,
    user_edit_scope: str = "page"
) -> ClassificationResult:
    """Parallel classification for report edits"""
    context = f"Edit mode: {edit_mode}\n"
    selected_summary = ""
    if selected_text:
        context += f"Selected: {selected_text[:200]}\n"
        selected_summary = f"Selected text: '{selected_text[:100]}'"
    context += f"Page preview: {content_preview[:300]}"
    return await parallel_classify(
        user_message=user_message,
        context_summary=context,
        context_type="report",
        user_id=user_id,
        edit_mode=edit_mode,
        selected_element_summary=selected_summary,
        user_edit_scope=user_edit_scope
    )
