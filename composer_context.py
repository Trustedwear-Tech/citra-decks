"""
AI Report Generator - Composer Backend
Generates reports from vault documents based on user goals
"""

import logging
import json
import os
import re
import traceback
from typing import Dict, List, Optional, Any
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
import asyncio
import time
from llm_oss import llm_call, llm_call_with_internet, llm_call_streaming
from citra_auth import get_user_email, get_secure_user_id

from composer_query import retrieve_vault_context
from services.edit_orchestrator import build_document_outline, get_structured_data_context
from services.compute_fact_tool import (
    build_compute_fact_tool_schema,
    make_compute_fact_dispatcher,
    COMPUTE_FACT_ROUTING_RULE,
)
from services.unstructured_file_listing import prefetch_unstructured_metadata_for_outline

router = APIRouter()


def _compose_grounded_system(base_prompt: str) -> str:
    """
    Prefix a base system prompt with the canonical strict-grounding header.
    Best-effort: if the prompts package is unavailable, returns base_prompt
    unchanged so composer keeps working.
    """
    try:
        from prompts.grounding import STRICT_GROUNDING_PROMPT, CITATION_TAGS_RULE
        return (
            STRICT_GROUNDING_PROMPT.strip()
            + "\n\n"
            + CITATION_TAGS_RULE.strip()
            + "\n\n---\n\n"
            + base_prompt
        )
    except Exception:
        return base_prompt

# ═══════════════════════════════════════════════════════════════════════════════════════
# Chart Config Validation for <chart-config> tags in HTML
# ═══════════════════════════════════════════════════════════════════════════════════════

_VALID_CHART_TYPES = {"bar", "line", "pie", "doughnut", "radar", "polarArea", "scatter", "bubble"}


def _is_chart_tag_valid(cfg: dict) -> bool:
    """Check if a chartConfig dict is structurally valid for Chart.js."""
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


def _normalize_chart_config(cfg: dict) -> dict:
    """Apply deterministic fixes to a chart config."""
    if not isinstance(cfg, dict):
        return cfg
    ctype = cfg.get("type", "bar")
    if ctype not in _VALID_CHART_TYPES:
        stripped = ctype.replace("chart-", "").replace("chart_", "")
        cfg["type"] = stripped if stripped in _VALID_CHART_TYPES else "bar"
    if "data" not in cfg and ("labels" in cfg or "datasets" in cfg):
        cfg["data"] = {"labels": cfg.pop("labels", []), "datasets": cfg.pop("datasets", [])}
    return cfg


def _validate_chart_config_tags(html_content: str) -> str:
    """Validate all <chart-config> tags in HTML; remove fatally malformed ones to prevent
    frontend rendering errors. Applies deterministic fixes where possible."""
    if not html_content or "<chart-config>" not in html_content:
        return html_content

    import re as _re
    pattern = _re.compile(r'<chart-config>([\s\S]*?)</chart-config>')

    def _fix_match(match):
        raw_json = match.group(1).strip()
        try:
            cfg = json.loads(raw_json)
            cfg = _normalize_chart_config(cfg)
            if _is_chart_tag_valid(cfg):
                return f"<chart-config>{json.dumps(cfg)}</chart-config>"
            else:
                logging.warning(f"📊 [COMPOSER] Removing malformed <chart-config>: {raw_json[:200]}")
                return ""  # Remove broken chart tag — frontend would crash
        except json.JSONDecodeError:
            logging.warning(f"📊 [COMPOSER] Removing unparseable <chart-config>: {raw_json[:200]}")
            return ""

    return pattern.sub(_fix_match, html_content)


# ═══════════════════════════════════════════════════════════════════════════════════════
# GOAL BREAKDOWN - Break user's goal into actionable to-do items
# ═══════════════════════════════════════════════════════════════════════════════════════

@router.post("/composer/break-goal")
async def break_goal_into_todos(request: Request):
    """
    Break a user's goal into actionable to-do items for report building.
    These to-dos become locked sections once report is generated.
    """
    try:
        payload = await request.json()
        
        goal = payload.get('goal', '')
        document_type = payload.get('document_type', 'report')
        # Prefer report_type if sent, fallback to document_type
        report_type = payload.get('report_type', document_type)
        target_audience = payload.get('target_audience', '')
        folder_ids = payload.get('folder_ids', [])  # NEW: Get folder IDs from payload
        # Data source flags from UI goal-setting toggles
        use_personal_data = bool(payload.get('use_personal_data', bool(folder_ids)))
        user_id = get_secure_user_id(request)
        user_email = get_user_email(request)
        
        if not goal.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Goal is required"
            )
        
        # Pre-bind: lite-mode vault retrieval (no sub-query expansion, no
        # reranker, no agentic tool-loop) using the goal as query. Replaces
        # the previous agentic loop (~30-45 s) with a single Milvus top-k
        # pull (~1-2 s) plus one synthesis call.
        use_personal_for_loop = bool(folder_ids) and bool(use_personal_data)

        # Prefetch unstructured-file metadata (small — filenames + summaries).
        unstructured_metadata_block = ""
        if use_personal_for_loop:
            try:
                _meta = await prefetch_unstructured_metadata_for_outline(
                    user_id=user_id, folder_ids=folder_ids, query=goal,
                )
                if _meta:
                    unstructured_metadata_block = f"\n\n{_meta}"
                    logging.info(f"📄 [REPORT] Prefetched unstructured metadata ({len(_meta)} chars)")
            except Exception as e:
                logging.warning(f"📄 [REPORT] Unstructured metadata prefetch failed (non-blocking): {e}")

        # Pre-bind vault chunks for the goal.
        outline_vault_block = ""
        if use_personal_for_loop:
            from services.personal_data_tool import retrieve_vault_context_for_prompt
            outline_vault_block = await retrieve_vault_context_for_prompt(
                query=goal,
                user_id=user_id,
                user_email=user_email,
                folder_ids=folder_ids,
                max_results=8,
                log_prefix="REPORT-OUTLINE-LITE",
                adaptive_threshold=True,
                adaptive_floor=5,
            )

        vault_block = f"\n\n{outline_vault_block}" if outline_vault_block else ""

        prompt = f"""Break down this report goal into actionable to-do items (report sections):

GOAL: {goal}
DOCUMENT TYPE: {report_type}
TARGET AUDIENCE: {target_audience or 'General'}
{unstructured_metadata_block}{vault_block}

CRITICAL INSTRUCTION:
- If the goal text explicitly mentions a specific number of pages/sections/paragraphs/items (e.g., "create 5 sections", "10 paragraphs", "4 pages"), create EXACTLY that many sections
- Otherwise, create 3-7 sections based on the complexity and scope of the goal

Create a logical structure for a professional report. Each to-do should be a clear section.

Return JSON array:
[
    {{
        "id": "section_1",
        "title": "Section Title",
        "description": "What this section should cover",
        "search_query": "Query to search vault for relevant content",
        "order": 1
    }}
]

Return ONLY the JSON array, no other text."""

        system_for_break = (
            "You are an expert at breaking down complex goals into actionable "
            "tasks for professional report writing. Create logical, comprehensive structures."
        )
        # Single LLM call — vault chunks pre-injected via outline_vault_block
        # (lite-mode retrieval). Compute_fact / personal_data_tool tool-calling
        # intentionally dropped to recover pre-refactor outline latency.
        response = await asyncio.to_thread(lambda: llm_call(
            system_prompt=system_for_break,
            user_prompt=prompt,
            model=None,
            user_id=user_id,
            max_tokens=8000,
            temperature=0.2,
            top_p=0.95,
            tier="large",
        ))
        
        # Parse JSON response with robust error handling
        todos = None
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            raw_json = json_match.group()
            
            # Try multiple parsing strategies
            try:
                todos = json.loads(raw_json)
            except json.JSONDecodeError:
                pass
            
            if todos is None:
                try:
                    # Clean up common AI JSON issues
                    cleaned = re.sub(r',\s*([}\]])', r'\1', raw_json)
                    cleaned = re.sub(r'\}\s*\{', '},{', cleaned)
                    cleaned = cleaned.replace('```json', '').replace('```', '').strip()
                    todos = json.loads(cleaned)
                except json.JSONDecodeError:
                    pass
            
            if todos is None:
                try:
                    # Extract individual objects
                    obj_pattern = r'\{[^{}]*"title"[^{}]*"description"[^{}]*\}'
                    objects = re.findall(obj_pattern, raw_json, re.DOTALL)
                    if objects:
                        todos = []
                        for obj_str in objects:
                            try:
                                obj = json.loads(obj_str)
                                if 'title' in obj:
                                    todos.append(obj)
                            except (json.JSONDecodeError, ValueError):
                                # best-effort: skip individual unparseable object
                                continue
                except (re.error, ValueError, TypeError):
                    # best-effort: object-extraction strategy failed, fall back below
                    pass
        
        if todos and isinstance(todos, list) and len(todos) > 0:
            return JSONResponse({
                "success": True,
                "todos": todos,
                "goal": goal
            })
        else:
            # Fallback structure
            logging.warning(f"Failed to parse AI response for todos, using fallback. Response was: {response[:500]}")
            return JSONResponse({
                "success": True,
                "todos": [
                    {"id": "section_1", "title": "Introduction", "description": "Overview and context", "search_query": goal, "order": 1},
                    {"id": "section_2", "title": "Main Analysis", "description": "Core content and findings", "search_query": goal, "order": 2},
                    {"id": "section_3", "title": "Conclusion", "description": "Summary and recommendations", "search_query": goal, "order": 3}
                ],
                "goal": goal
            })
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error breaking goal into todos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing goal: {str(e)}"
        )


# ═══════════════════════════════════════════════════════════════════════════════════════
# BREAK GOAL STREAMING - Stream sections as they are generated
# ═══════════════════════════════════════════════════════════════════════════════════════

@router.post("/composer/break-goal-stream")
async def break_goal_into_todos_streaming(request: Request):
    """
    Stream report sections one by one as they are generated.
    Uses Server-Sent Events (SSE) format for real-time updates.
    Accepts section_count parameter to generate specific number of sections (3-100).
    """
    try:
        payload = await request.json()
        goal = payload.get('goal', '')
        report_type = payload.get('report_type', 'report')
        section_count = payload.get('section_count', 7)  # Default 7, user can specify 3-100
        user_id = get_secure_user_id(request)
        user_email = get_user_email(request)
        
        # Validate section count
        section_count = max(3, min(100, int(section_count)))
        
        if not goal:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Goal is required"
            )
        
        use_internet_search = payload.get('use_internet_search', False)
        folder_ids = payload.get('folder_ids', [])
        # Data source flags from UI goal-setting toggles
        use_personal_data = bool(payload.get('use_personal_data', bool(folder_ids)))
        
        async def generate_sections_stream():
            """Generator that yields sections as SSE events"""
            try:
                # Send initial progress event
                yield f"data: {json.dumps({'type': 'progress', 'message': 'Analyzing your goal...', 'step': 1, 'target_count': section_count})}\n\n"
                
                # Internet search: deterministic prefetch (no LLM orchestration)
                # Embeds raw search answer(s) into the user's vault so the
                # subsequent vault retrieval — and downstream section/page
                # generation — can pick them up via Milvus.
                internet_context = ""
                if use_internet_search:
                    try:
                        yield f"data: {json.dumps({'type': 'progress', 'message': 'Searching the internet for latest data...', 'step': 1})}\n\n"
                        from services.internet_prefetch import prefetch_internet_research

                        prefetch_results = await prefetch_internet_research(
                            goal=goal,
                            doc_type=report_type or "report",
                            target_audience=None,
                            user_id=user_id,
                            user_email=user_email,
                            folder_id=(folder_ids[0] if folder_ids else None),
                            num_queries=1,
                        )
                        for r in prefetch_results:
                            yield f"data: {json.dumps({'type': 'internet_research', 'document_id': r['document_id'], 'folder_id': r['folder_id'], 'word_count': r['word_count']})}\n\n"
                        if prefetch_results:
                            # Use the first result as a short anchor in the
                            # outline prompt; full text is in vault for
                            # retrieval-time use.
                            internet_context = prefetch_results[0]["text"]
                            logging.info(
                                f"\ud83c\udf10 [REPORT] Internet prefetch embedded {len(prefetch_results)} doc(s) in vault"
                            )
                    except Exception as e:
                        logging.warning(f"\ud83c\udf10 [REPORT] Internet prefetch failed (non-blocking): {e}")
                        yield f"data: {json.dumps({'type': 'progress', 'message': 'Internet search skipped, continuing...', 'step': 1})}\n\n"
                
                internet_context_block = ""
                if internet_context:
                    internet_context_block = f"\n\nINTERNET RESEARCH DATA (use this to inform section structure):\n{internet_context[:5000]}\n"
                
                # Vault chunks are now fetched agentically inside the
                # tool-loop below — no pre-fetch. The system prompt nudge
                # tells the LLM to call personal_data_tool first.
                use_personal_for_loop_section = bool(folder_ids) and bool(use_personal_data)
                vault_context_block = ""

                # Prefetch schema-only structured-data context for better section planning
                # Gated by use_personal_data flag (uploaded Excel/JSON in user's vault)
                structured_data_block = ""
                if folder_ids and use_personal_data:
                    try:
                        from composer_query import prefetch_structured_data_context
                        structured_data_context = await prefetch_structured_data_context(
                            user_id=user_id,
                            goal=goal,
                            folder_ids=folder_ids
                        )
                        if structured_data_context:
                            structured_data_block = f"\n\nSTRUCTURED DATA FROM USER'S FILES (real precomputed values from uploaded spreadsheets/CSVs):\n{structured_data_context}\n(IMPORTANT: These are REAL aggregates from the user's files — top categories, totals, date ranges, breakdowns. Anchor every section title and outline on these actual values. Reference real names, real numbers, real periods. Do NOT write generic narrative when concrete facts are available, and never invent numbers.)\n"
                            logging.info(f"🌊 [REPORT] Prefetched structured data for section planning ({len(structured_data_context)} chars)")
                    except Exception as e:
                        logging.warning(f"🌊 [REPORT] Structured data prefetch failed (non-blocking): {e}")

                # Prefetch unstructured-file metadata so the outline LLM can
                # pick search_query strings that map to actual vault files.
                unstructured_metadata_block = ""
                if folder_ids and use_personal_data:
                    try:
                        _meta = await prefetch_unstructured_metadata_for_outline(
                            user_id=user_id, folder_ids=folder_ids, query=goal,
                        )
                        if _meta:
                            unstructured_metadata_block = f"\n\n{_meta}\n"
                            logging.info(f"📄 [REPORT] Prefetched unstructured metadata for section planning ({len(_meta)} chars)")
                    except Exception as e:
                        logging.warning(f"📄 [REPORT] Unstructured metadata prefetch failed (non-blocking): {e}")

                # Pre-bind: lite-mode vault retrieval using the goal as
                # query. Replaces the previous agentic loop (~30-45 s) with
                # a single Milvus top-k pull (~1-2 s) plus one synthesis call.
                outline_vault_block = ""
                if use_personal_for_loop_section:
                    from services.personal_data_tool import retrieve_vault_context_for_prompt
                    outline_vault_block = await retrieve_vault_context_for_prompt(
                        query=goal,
                        user_id=user_id,
                        user_email=getattr(request.state, 'user_email', None) if hasattr(request, 'state') else None,
                        folder_ids=folder_ids,
                        max_results=8,
                        log_prefix="REPORT-OUTLINE-STREAM-LITE",
                        adaptive_threshold=True,
                        adaptive_floor=5,
                    )

                personal_tool_nudge_block = f"\n\n{outline_vault_block}\n" if outline_vault_block else ""

                prompt = f"""Break this report goal into EXACTLY {section_count} logical sections for a {report_type}.

Goal: {goal}
{vault_context_block}{personal_tool_nudge_block}{internet_context_block}{structured_data_block}{unstructured_metadata_block}
CRITICAL: You MUST create EXACTLY {section_count} sections. No more, no less.

For each section, provide:
- A clear title
- A brief description of what this section will cover
- A search query to find relevant content in the user's vault

Return ONLY a JSON array with NO markdown formatting or code blocks:
[
  {{"id": "section_1", "title": "Section Title", "description": "What this section covers", "search_query": "query to search vault", "order": 1}},
  {{"id": "section_2", "title": "Section Title", "description": "What this section covers", "search_query": "query to search vault", "order": 2}},
  ... (continue until section_{section_count})
]

Be specific with search queries to find the most relevant content.
REMEMBER: Return EXACTLY {section_count} sections."""

                yield f"data: {json.dumps({'type': 'progress', 'message': f'Creating {section_count} report sections...', 'step': 2})}\n\n"

                _system_for_sections = (
                    f"You are an expert at breaking down complex goals into actionable tasks "
                    f"for professional report writing. Create logical, comprehensive structures. "
                    f"You MUST generate EXACTLY {section_count} sections as requested."
                )
                # Single LLM call — vault chunks pre-injected via
                # outline_vault_block. Compute_fact / personal_data_tool
                # tool-calling intentionally dropped here.
                full_response = await asyncio.to_thread(lambda: llm_call(
                    system_prompt=_system_for_sections,
                    user_prompt=prompt,
                    model=None,
                    user_id=user_id,
                    max_tokens=8000,
                    temperature=0.2,
                    top_p=0.95,
                    tier="large",
                ))
                # Send progress chunk after generation
                yield f"data: {json.dumps({'type': 'progress', 'message': 'Generating sections...', 'step': 2})}\n\n"
                
                yield f"data: {json.dumps({'type': 'progress', 'message': 'Processing sections...', 'step': 3})}\n\n"
                
                # Parse the response with robust JSON handling
                sections = None
                
                # Try multiple parsing strategies
                json_match = re.search(r'\[.*\]', full_response, re.DOTALL)
                if json_match:
                    raw_json = json_match.group()
                    
                    # Strategy 1: Direct parse
                    try:
                        sections = json.loads(raw_json)
                    except json.JSONDecodeError:
                        pass
                    
                    # Strategy 2: Clean up common AI JSON issues
                    if sections is None:
                        try:
                            # Remove trailing commas before ] or }
                            cleaned = re.sub(r',\s*([}\]])', r'\1', raw_json)
                            # Fix missing commas between objects
                            cleaned = re.sub(r'\}\s*\{', '},{', cleaned)
                            # Remove any markdown artifacts
                            cleaned = cleaned.replace('```json', '').replace('```', '').strip()
                            sections = json.loads(cleaned)
                        except json.JSONDecodeError:
                            pass
                    
                    # Strategy 3: Extract individual objects and rebuild array
                    if sections is None:
                        try:
                            # Find all JSON objects in the response
                            obj_pattern = r'\{[^{}]*"title"[^{}]*"description"[^{}]*\}'
                            objects = re.findall(obj_pattern, raw_json, re.DOTALL)
                            if objects:
                                sections = []
                                for obj_str in objects:
                                    try:
                                        obj = json.loads(obj_str)
                                        if 'title' in obj:
                                            sections.append(obj)
                                    except (json.JSONDecodeError, ValueError):
                                        # best-effort: skip individual unparseable object
                                        continue
                        except (re.error, ValueError, TypeError):
                            # best-effort: object-extraction strategy failed, try next strategy
                            pass
                    
                    # Strategy 4: Use ast.literal_eval as last resort
                    if sections is None:
                        try:
                            import ast
                            # Convert JSON-like to Python-like syntax
                            python_like = raw_json.replace('null', 'None').replace('true', 'True').replace('false', 'False')
                            sections = ast.literal_eval(python_like)
                        except (ValueError, SyntaxError, TypeError):
                            # best-effort: last-resort literal_eval failed, fall back below
                            pass
                
                # Final fallback: create generic sections based on goal
                if not sections or not isinstance(sections, list) or len(sections) == 0:
                    logging.warning(f"Failed to parse AI response for sections, using fallback. Response was: {full_response[:500]}")
                    sections = []
                    for i in range(section_count):
                        if i == 0:
                            sections.append({"id": f"section_{i+1}", "title": "Introduction", "description": "Overview and context", "search_query": goal, "order": i+1})
                        elif i == section_count - 1:
                            sections.append({"id": f"section_{i+1}", "title": "Conclusion", "description": "Summary and recommendations", "search_query": goal, "order": i+1})
                        else:
                            sections.append({"id": f"section_{i+1}", "title": f"Section {i+1}", "description": f"Content for section {i+1}", "search_query": goal, "order": i+1})
                
                # Stream each section individually
                for idx, section in enumerate(sections):
                    section['order'] = idx + 1  # Ensure order is set
                    section['id'] = f"section_{idx + 1}"  # Ensure ID is set
                    yield f"data: {json.dumps({'type': 'section', 'index': idx, 'section': section, 'total': len(sections)})}\n\n"
                    await asyncio.sleep(0.05)  # Small delay for visual effect
                
                # Send completion event
                yield f"data: {json.dumps({'type': 'done', 'total': len(sections), 'goal': goal})}\n\n"
                
            except Exception as e:
                logging.error(f"Error in streaming section generation: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        
        return StreamingResponse(
            generate_sections_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in break-goal streaming: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing goal: {str(e)}"
        )


# ═══════════════════════════════════════════════════════════════════════════════════════
# REPORT GENERATION - Generate full report from vault using Milvus
# ═══════════════════════════════════════════════════════════════════════════════════════

@router.post("/composer/generate-report")
async def generate_report_from_vault(request: Request):
    """
    Generate a complete multi-page report by querying Milvus for each to-do item.
    Uses vault documents to create content with citations.
    """
    try:
        payload = await request.json()
        
        goal = payload.get('goal', '')
        report_type = payload.get('report_type', 'report')
        todos = payload.get('todos', [])
        folder_ids = payload.get('folder_ids', [])
        # Data source flags from UI goal-setting toggles
        use_personal_data = bool(payload.get('use_personal_data', bool(folder_ids)))
        user_id = get_secure_user_id(request)
        user_email = get_user_email(request)
        special_instructions = payload.get('special_instructions', '')  # User guidance for AI

        if not todos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="To-do items are required"
            )
        
        
        # Generate all sections in parallel
        async def generate_section(todo, index):
            """Generate a single section asynchronously"""
            section_id = todo.get('id', f"section_{index + 1}")
            section_title = todo.get('title', 'Section')
            search_query = todo.get('search_query', todo.get('description', goal))
            
            # Vault chunks are now fetched agentically by the LLM via
            # personal_data_tool below.
            # Section citations now come from inline [vault:doc_id] tags the
            # LLM emits in the response, parsed by downstream UI code.
            section_citations: List[Dict[str, Any]] = []
            use_personal_for_section = bool(folder_ids) and bool(use_personal_data)
            # Pre-bind: lite-mode vault retrieval (no sub-query expansion, no
            # reranker) for THIS section. Returns a prompt-ready block; "" when
            # vault is disabled / no match. Also keep the unstructured-metadata
            # block so the LLM can see which file the passages came from.
            section_unstructured_block = ""
            section_vault_block = ""
            if use_personal_for_section:
                _section_query = f"{section_title}. {todo.get('description', '')}".strip()
                try:
                    _meta = await prefetch_unstructured_metadata_for_outline(
                        user_id=user_id, folder_ids=folder_ids, query=_section_query,
                    )
                    if _meta:
                        section_unstructured_block = f"\n\n{_meta}"
                except Exception as e:
                    logging.warning(f"📄 [REPORT] section unstructured prefetch failed (non-blocking): {e}")
                from services.personal_data_tool import retrieve_vault_context_for_prompt
                section_vault_block = await retrieve_vault_context_for_prompt(
                    query=_section_query,
                    user_id=user_id,
                    user_email=user_email,
                    folder_ids=folder_ids,
                    max_results=5,
                    log_prefix="REPORT-SECTION-LITE",
                )

            grounding_block = ""
            if section_vault_block:
                grounding_block = f"\n\n{section_vault_block}"

            static_ctx = f"""REPORT CONTEXT:

Goal: {goal}
Type: {report_type} (Strictly follow this format/tone)
Section: {section_title}
Search hint: {search_query}{section_unstructured_block}{grounding_block}"""
            prompt = f"""Write the "{section_title}" section.

OBJECTIVE: {todo.get('description', section_title)}

GROUNDING: Use the VAULT PASSAGES above as the source of truth. If a claim is not in the provided passages, do not state it as a fact — describe qualitatively or omit. DO NOT include any citation markers, doc IDs, or bracketed references (e.g. [vault:...], [doc:...], [source:...], [internet:...], [structured:...]) in the rendered output. The passages are for grounding only, not for display.

FORMAT: Clean HTML (<p>, <strong>, <em>, <h3>, <ul>, <li>, <table>, <tr>, <th>, <td>)
- No markdown syntax (no **, no ##, no ```)
- No section title in output
- Use HTML tables when presenting structured data
- [OPTIONAL] If the section contains financial/numerical data BEST visualized as a chart, generate a VALID JSON chart config wrapped in <chart-config> tags. Supported types: bar, line, pie, doughnut, radar, polarArea, scatter, bubble.
- Professional and concise
{f"- SPECIAL INSTRUCTIONS (MUST FOLLOW): {special_instructions}" if special_instructions else ""}"""

            full_prompt = f"{static_ctx}\n\n{prompt}"
            # Single LLM call per section — vault chunks are pre-injected
            # via section_vault_block (lite-mode retrieval). Compute_fact /
            # personal_data_tool tool-calling intentionally dropped to
            # recover pre-refactor latency; structured aggregates already
            # flow in via the planning phase, vault passages already flow
            # in via section_vault_block.
            section_content = await asyncio.to_thread(lambda: llm_call(
                system_prompt=_compose_grounded_system(
                    "You are a professional content writer creating high-quality "
                    "report sections. Use clean HTML formatting and be comprehensive "
                    "yet concise. DATA ACCURACY: Do NOT hallucinate or fabricate "
                    "numbers, statistics, projections, dates, or factual claims — "
                    "use ONLY verifiable facts from provided context/vault data. "
                    "DO NOT emit any citation markers, doc IDs, or bracketed "
                    "references (e.g. [vault:...], [doc:...], [source:...]) in the "
                    "rendered HTML — vault passages are for grounding only."
                ),
                user_prompt=full_prompt,
                model=None,
                user_id=user_id,
                max_tokens=8000,
                temperature=0.2,
                top_p=0.95,
                tier="large",
            ))
            
            # Clean up any markdown code fences from generated content
            if section_content:
                import re
                section_content = re.sub(r'```\w*\n?', '', section_content).replace('```', '').strip()
                # Defensive: strip [vault:...]/[doc:...]/[source:...] tags that
                # the LLM may have inserted into the rendered HTML despite the
                # grounding directive. They're for grounding only, never for
                # display.
                from services.personal_data_tool import strip_citation_tags
                section_content = strip_citation_tags(section_content)
                section_content = _validate_chart_config_tags(section_content)
            
            # Create page object
            return {
                "id": section_id,
                "title": section_title,
                "content": section_content,
                "order": todo.get('order', index + 1),
                "citations": section_citations,
                "todo_id": todo.get('id')
            }
        
        # Generate all sections in parallel with max concurrency of 5
        MAX_CONCURRENT_SECTIONS = 5
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_SECTIONS)
        
        async def generate_section_with_limit(todo, index):
            """Generate a section with concurrency limiting"""
            async with semaphore:
                return await generate_section(todo, index)
        
        logging.info(f"🚀 Generating {len(todos)} sections in parallel (max {MAX_CONCURRENT_SECTIONS} concurrent)...")
        start_time = time.time()
        
        pages = await asyncio.gather(
            *[generate_section_with_limit(todo, i) for i, todo in enumerate(todos)],
            return_exceptions=True
        )
        
        # Filter out exceptions and collect results
        successful_pages = []
        all_citations = []
        for page in pages:
            if isinstance(page, Exception):
                logging.error(f"Section generation failed: {page}")
                continue
            successful_pages.append(page)
            all_citations.extend(page.get('citations', []))
        
        elapsed_time = time.time() - start_time
        logging.info(f"✅ Generated {len(successful_pages)} sections in {elapsed_time:.2f}s (parallel, max {MAX_CONCURRENT_SECTIONS} concurrent)")
        
        return JSONResponse({
            "success": True,
            "pages": successful_pages,
            "citations": all_citations,
            "goal": goal,
            "generated_at": datetime.now().isoformat(),
            "generation_time_seconds": round(elapsed_time, 2),
            "parallel_mode": True,
            "max_concurrent_sections": MAX_CONCURRENT_SECTIONS,
            "total_sections": len(todos),
            "successful_sections": len(successful_pages)
        })
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error generating report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating report: {str(e)}"
        )


# ═══════════════════════════════════════════════════════════════════════════════════════
# SINGLE SECTION GENERATION - Generate one section at a time (UI-controlled batching)
# ═══════════════════════════════════════════════════════════════════════════════════════

@router.post("/composer/generate-section")
async def generate_single_section(request: Request):
    """
    Generate a SINGLE report section.
    UI calls this endpoint in parallel batches of 5 for better progress visibility.
    This gives UI full control over batching and progress display.
    
    Supports optional user-selected style:
    - style: { id, colors: {primary, secondary, text, ...}, fonts: {heading, body, ...} }
    
    If style not provided, generates plain HTML (default behavior).
    """
    try:
        payload = await request.json()
        
        section = payload.get('section', {})  # Single todo/section item
        goal = payload.get('goal', '')
        report_type = payload.get('report_type', 'report')
        folder_ids = payload.get('folder_ids', [])
        # Data source flags from UI goal-setting toggles
        use_personal_data = bool(payload.get('use_personal_data', bool(folder_ids)))
        user_id = get_secure_user_id(request)
        user_email = get_user_email(request)
        special_instructions = payload.get('special_instructions', '')
        section_index = payload.get('section_index', 0)
        total_sections = payload.get('total_sections', 1)
        
        # User-selected style (optional)
        user_style = payload.get('style')  # { id, colors, fonts } or None
        
        if not section:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Section is required"
            )
        
        section_id = section.get('id', f"section_{section_index + 1}")
        section_title = section.get('title', 'Section')
        search_query = section.get('search_query', section.get('description', goal))
        
        logging.info(f"🔄 [SINGLE_SECTION] Generating section {section_index + 1}/{total_sections}: {section_title} (style: {user_style.get('id') if user_style else 'default'})")
        start_time = time.time()
        
        # Vault chunks are now fetched agentically by the LLM via
        # personal_data_tool inside run_Enterprise_or_Personal_tool below.
        vault_context = ""
        use_personal_for_single = bool(folder_ids) and bool(use_personal_data)
        
        # Prefetch schema-only structured-data context
        # Gated by use_personal_data flag (uploaded Excel/JSON in user's vault)
        structured_data_context = None
        if folder_ids and use_personal_data:
            try:
                from composer_query import prefetch_structured_data_context
                # Use the top-level report goal (not per-section search_query) so
                # the overview cache is shared with the planning phase and with
                # presentation/printable runs on the same goal.
                structured_data_context = await prefetch_structured_data_context(
                    user_id=user_id,
                    goal=goal,
                    folder_ids=folder_ids
                )
                if structured_data_context:
                    logging.info(f"🌊 [SINGLE_SECTION] Section '{section_title}' structured data: {len(structured_data_context)} chars")
            except Exception as e:
                logging.warning(f"🌊 [SINGLE_SECTION] Structured data prefetch failed for section {section_title} (non-blocking): {e}")

        # Prefetch unstructured-file metadata scoped to THIS section so the
        # LLM can pick which vault docs to fetch via personal_data_tool.
        section_unstructured_block = ""
        if folder_ids and use_personal_data:
            try:
                _section_query = f"{section_title}. {section.get('description', '')}".strip()
                _meta = await prefetch_unstructured_metadata_for_outline(
                    user_id=user_id, folder_ids=folder_ids, query=_section_query,
                )
                if _meta:
                    section_unstructured_block = f"\n\n{_meta}"
                    logging.info(f"📄 [SINGLE_SECTION] Unstructured metadata for '{section_title}': {len(_meta)} chars")
            except Exception as e:
                logging.warning(f"📄 [SINGLE_SECTION] Unstructured metadata prefetch failed (non-blocking): {e}")

        # Parse citations from vault context
        section_citations = []
        if vault_context:
            source_matches = re.findall(r'\[([^\]]+)\]', vault_context)
            for source in source_matches[:5]:
                section_citations.append({
                    "document_id": "",
                    "topic": source,
                    "chunk_id": ""
                })
        
        context_text = vault_context
        
        # Build style instructions if user selected a specific style
        style_instructions = ""
        if user_style and user_style.get('colors'):
            colors = user_style['colors']
            fonts = user_style.get('fonts', {})
            style_instructions = f"""
STYLING (USER-SELECTED - MUST APPLY):
- Apply inline styles to HTML elements using these colors:
- Headers (h2, h3): color: {colors.get('primary', '#1E40AF')}; font-family: {fonts.get('heading', 'inherit')}
- Body text: color: {colors.get('text', '#111827')}; font-family: {fonts.get('body', 'inherit')}
- Important/highlighted text: color: {colors.get('secondary', '#3B82F6')}
- Tables: header background {colors.get('primary', '#1E40AF')} with white text
- Blockquotes: border-left: 4px solid {colors.get('primary', '#1E40AF')}; background: {colors.get('surface', '#F3F4F6')}
- Links: color: {colors.get('secondary', '#3B82F6')}
Example: <h2 style="color: {colors.get('primary', '#1E40AF')}">Title</h2>"""
        
        # Generate section content using AI
        structured_data_block = ""
        if structured_data_context:
            structured_data_block = f"""

STRUCTURED DATA FROM USER'S FILES (real precomputed values from uploaded spreadsheets/CSVs):
{structured_data_context}
(IMPORTANT: These are REAL aggregates from the user's files — top categories, totals, date ranges, breakdowns. Anchor this section on these actual values. Reference real names, real numbers, real periods verbatim. Do NOT write generic narrative when concrete facts are available, and never invent numbers.)"""

        # Pre-bind: lite-mode vault retrieval (no sub-query expansion, no
        # reranker) for THIS section. Returns prompt-ready block; "" when
        # vault is disabled / no match.
        section_vault_block = ""
        if use_personal_for_single:
            from services.personal_data_tool import retrieve_vault_context_for_prompt
            _section_query_for_lite = (
                f"{section_title}. {section.get('description', '')}"
            ).strip(" .")
            section_vault_block = await retrieve_vault_context_for_prompt(
                query=_section_query_for_lite or goal,
                user_id=user_id,
                user_email=getattr(request.state, 'user_email', None) if hasattr(request, 'state') else None,
                folder_ids=folder_ids,
                max_results=5,
                log_prefix="REPORT-SINGLE-SECTION-LITE",
            )

        personal_tool_block = ""
        if section_vault_block:
            personal_tool_block = f"\n\n{section_vault_block}"

        if context_text or use_personal_for_single:
            static_ctx = f"""REPORT CONTEXT:

Goal: {goal}
Type: {report_type} (Strictly follow this format/tone)
Section: {section_title} (Section {section_index + 1} of {total_sections})

SOURCES FROM VAULT:
{context_text}
{structured_data_block}{personal_tool_block}{section_unstructured_block}"""
            prompt = f"""Write the "{section_title}" section.

OBJECTIVE: {section.get('description', section_title)}

GROUNDING: Use the provided context/VAULT PASSAGES as the source of truth. If a claim is not supported by the provided context, do not state it as a fact — describe qualitatively or omit. DO NOT include any citation markers, doc IDs, or bracketed references (e.g. [vault:...], [doc:...], [source:...], [internet:...], [structured:...]) in the rendered output. The provided context is for grounding only, not for display.

FORMAT: Clean HTML (<p>, <strong>, <em>, <h3>, <ul>, <li>, <table>, <tr>, <th>, <td>)
- No markdown syntax (no **, no ##, no ```)
- No section title in output
- Use HTML tables (<table>, <tr>, <th>, <td>) when presenting structured data
- [OPTIONAL] If the section contains financial/numerical data that is BEST visualized as a chart, generate a VALID JSON chart config wrapped in <chart-config> tags (Supported types: bar, line, pie, doughnut, radar, polarArea, scatter, bubble)
- Professional and concise
{f"- SPECIAL INSTRUCTIONS (MUST FOLLOW): {special_instructions}" if special_instructions else ""}{style_instructions}"""

            full_prompt = f"{static_ctx}\n\n{prompt}"
            _system_for_section = _compose_grounded_system(
                "You are a professional content writer creating high-quality report sections. "
                "Use clean HTML formatting and be comprehensive yet concise. DATA ACCURACY: "
                "Do NOT hallucinate or fabricate numbers, statistics, projections, dates, or "
                "factual claims — use ONLY verifiable facts from provided context/vault data. "
                "DO NOT emit any citation markers, doc IDs, or bracketed references "
                "(e.g. [vault:...], [doc:...], [source:...]) in the rendered HTML — "
                "vault passages are for grounding only."
            )
            # Single LLM call per section — vault chunks are pre-injected via
            # section_vault_block (lite-mode retrieval). Compute_fact /
            # personal_data_tool tool-calling intentionally dropped to recover
            # pre-refactor latency.
            section_content = await asyncio.to_thread(lambda: llm_call(
                system_prompt=_system_for_section,
                user_prompt=full_prompt,
                model=None,
                user_id=user_id,
                max_tokens=8000,
                temperature=0.2,
                top_p=0.95,
                tier="large",
            ))
        else:
            prompt = f"""Write "{section_title}" for: {goal}

OBJECTIVE: {section.get('description', section_title)}
{structured_data_block}{personal_tool_block}
FORMAT: Clean HTML (<p>, <strong>, <em>, <h3>, <table>, <tr>, <th>, <td>)
- No markdown, no section title
- Use HTML tables when appropriate for structured data
{f"- SPECIAL INSTRUCTIONS (MUST FOLLOW): {special_instructions}" if special_instructions else ""}{style_instructions}"""

            section_content = await asyncio.to_thread(lambda: llm_call(
                system_prompt=_compose_grounded_system("You are a professional content writer creating high-quality report sections. Use clean HTML formatting and be comprehensive yet concise. DATA ACCURACY: Do NOT hallucinate or fabricate numbers, statistics, projections, dates, or factual claims — use ONLY verifiable facts from provided context/vault data."),
                user_prompt=prompt,
                model=None,
                user_id=user_id,
                max_tokens=8000,
                temperature=0.2,
                top_p=0.95,
                tier="large",
            ))
        
        # Clean up any markdown code fences
        if section_content:
            section_content = re.sub(r'```\w*\n?', '', section_content).replace('```', '').strip()
            # Defensive: strip [vault:...]/[doc:...]/[source:...] tags that
            # leaked through into the rendered HTML.
            from services.personal_data_tool import strip_citation_tags
            section_content = strip_citation_tags(section_content)
            section_content = _validate_chart_config_tags(section_content)
        
        elapsed_time = time.time() - start_time
        logging.info(f"✅ [SINGLE_SECTION] Generated section '{section_title}' in {elapsed_time:.2f}s")
        
        return JSONResponse({
            "success": True,
            "page": {
                "id": section_id,
                "title": section_title,
                "content": section_content,
                "order": section.get('order', section_index + 1),
                "citations": section_citations,
                "todo_id": section.get('id'),
                "style_id": user_style.get('id') if user_style else None
            },
            "section_index": section_index,
            "generation_time_seconds": round(elapsed_time, 2)
        })
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error generating single section: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating section: {str(e)}"
        )


# ═══════════════════════════════════════════════════════════════════════════════════════
# AI EDIT - Handle chat-based editing (insert, rewrite, overall)
# ═══════════════════════════════════════════════════════════════════════════════════════

@router.post("/composer/ai-edit")
async def ai_edit_content(request: Request):
    """
    Handle AI-powered editing through chat interface with intelligent two-stage workflow.
    
    Supports 3 edit modes:
    - 'selection': Edit only the selected text, return replacement HTML
    - 'insertion': Insert content at cursor position, return insertion HTML
    - 'overall': Modify entire page, return complete page HTML
    
    EDIT MANAGER: Backend orchestrates the entire process
    - Stage 1: LLM assesses if it needs vault data
    - Stage 2: If needed, fetch vault data and re-process
    - Frontend receives final result in single response
    """
    try:
        payload = await request.json()
        
        edit_mode = payload.get('edit_mode', 'overall')  # 'selection', 'insertion', or 'overall'
        instruction = payload.get('instruction', '')
        current_content = payload.get('current_content', '')
        selected_text = payload.get('selected_text', '')
        cursor_position = payload.get('cursor_position', 0)
        page_id = payload.get('page_id')
        goal = payload.get('goal', '')
        user_id = get_secure_user_id(request)
        user_email = get_user_email(request)
        folder_ids = payload.get('folder_ids', [])
        report_type = payload.get('report_type', 'report')
        image_context = payload.get('image_context')  # Context for image/chart editing
        user_edit_scope = payload.get('user_edit_scope', 'page')  # Frontend radio: 'element', 'page', 'all'
        pages_summary = payload.get('pages_summary')  # Document-level context for single-page edits
        document_outline = build_document_outline(pages_summary, page_id)
        
        if not instruction.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Instruction is required"
            )
        
        # ═══════════════════════════════════════════════════════════════════════════
        # PARALLEL AI INTENT CLASSIFICATION (2 focused calls instead of 1 heavy)
        # Note: SaaS data is now pre-embedded in Milvus - supplementary_sources removed
        # ═══════════════════════════════════════════════════════════════════════════
        logging.info(f"🎯 [EDIT_MANAGER] Classifying intent: {instruction[:50]}...")
        
        import json
        import re
        
        # Try parallel classification first (fast)
        try:
            from services.parallel_classifier import classify_report_edit
            classification = await classify_report_edit(
                user_message=instruction,
                edit_mode=edit_mode,
                content_preview=current_content[:500] if current_content else "",
                selected_text=selected_text,
                user_id=user_id,
                user_edit_scope=user_edit_scope
            )
            
            # Map parallel classification to legacy intent format
            intent_map = {
                "greeting": "greeting",
                "help": "help",
                "create_new": "create_new",
                "edit_text": "edit",
                "add_content": "edit",
                "format": "edit",
                "delete": "edit",
                "create_chart": "edit",
                "create_table": "edit",
                "create_image": "edit",  # Treat image requests as edit (no AI image generation)
                "chat_only": "greeting"  # Questions without edits
            }
            intent = intent_map.get(classification.action_type, "edit")
            ai_message = classification.ai_message
            create_topic = classification.create_topic
            requires_vault = classification.requires_vault
            
            # ═══════════════════════════════════════════════════════════════════════════
            # SCOPE AUTO-ESCALATION for report selection mode
            # ═══════════════════════════════════════════════════════════════════════════
            resolved_scope = getattr(classification, 'resolved_scope', 'slide')
            scope_message = getattr(classification, 'scope_message', '')
            
            if edit_mode == 'selection' and selected_text and resolved_scope in ['slide', 'all_relevant', 'global']:
                logging.info(f"🔄 [EDIT_MANAGER] Scope auto-escalation: selection → overall (resolved_scope={resolved_scope})")
                edit_mode = 'overall'  # Auto-escalate to full page
                # Will include scope_message in response
            
            logging.info(f"⚡ [EDIT_MANAGER] Parallel classification: intent_received={classification.action_type}, "
                        f"intent_final={intent}, requires_vault={requires_vault}, "
                        f"resolved_scope={resolved_scope}, create_topic={create_topic}")
            
            # Handle quick intents immediately
            if intent == "greeting":
                logging.info("💬 [EDIT_MANAGER] Greeting intent - returning message only")
                return JSONResponse({
                    "success": True,
                    "action_type": "message_only",
                    "ai_message": ai_message or "Hello! I'm your AI document assistant. I can edit content, add new pages, expand topics using your vault data, and reformat text. Just describe what you'd like to change!"
                })
            
            if intent == "help":
                logging.info("❓ [EDIT_MANAGER] Help intent - returning capabilities")
                return JSONResponse({
                    "success": True,
                    "action_type": "message_only",
                    "ai_message": ai_message or "Here's what I can do:\n• Edit text: 'Make this more concise' or 'Fix the grammar'\n• Add content: 'Expand on this topic' or 'Add more details'\n• Create pages: 'Create a new page about conclusions'\n• Format: 'Add bullet points' or 'Make headers bold'\n\nSelect text to edit just that, or edit the whole page!"
                })
            
            if intent == "create_new":
                logging.info(f"🆕 [EDIT_MANAGER] Create new page intent - topic: {create_topic}")
                # Fall through to create_new handling below
                
        except ImportError:
            logging.warning("📄 [EDIT_MANAGER] Parallel classifier not available, using legacy llm")
            intent = None  # Will trigger legacy classification
            supplementary_sources = []
        except Exception as e:
            logging.error(f"❌ [EDIT_MANAGER] Parallel classification failed: {e}, using legacy")
            intent = None
            supplementary_sources = []
        
        # Legacy llm classification (fallback)
        if intent is None:
            classify_system_prompt = """You are an intent classifier for a document editor AI assistant.
Classify the user's instruction into EXACTLY ONE category:

1. GREETING - Simple greetings, acknowledgments, or casual conversation:
   - "hi", "hello", "hey", "thanks", "okay", "cool"
   - Any social pleasantry that doesn't request an action

2. HELP - Questions about what the assistant can do:
   - "what can you do", "help", "how do I...", "what are your capabilities"
   - Questions asking about features or how to use the tool

3. CREATE_NEW - Requests to create a NEW page or section:
   - "create a new page about...", "add a page for..."
   - "make a new section", "generate a page about..."
   - Any request to ADD a completely new page to the document

4. UPDATE - Explicit requests to REFRESH or UPDATE existing content:
   - "Update this page", "Refresh with latest data"
   - "Sync with vault", "Update the numbers"
   - "Check for changes and update"
   - Requests that mean "Keep the structure, just update the content/stats"

5. EDIT - Any modification to existing content:
   - Grammar fixes, rephrasing, shortening, formatting
   - Adding content to existing page, expanding sections
   - Restructuring, deleting content
   - Any changes to the CURRENT page
   - Requests to add images or visuals (user can upload their own)

Output ONLY valid JSON:
{
  "intent": "greeting" | "help" | "create_new" | "update" | "edit",
  "ai_message": "Brief friendly message describing what you understood and will do (1 sentence)",
  "create_topic": "topic for new page (only if intent is create_new, else null)"
}

IMPORTANT: Always include a helpful ai_message."""

        classify_user_prompt = f"""Classify this instruction:
"{instruction}"

Output JSON classification:"""

        try:
            if intent is None:
                classify_response = await asyncio.to_thread(lambda: llm_call(
                    system_prompt=classify_system_prompt,
                    user_prompt=classify_user_prompt, 
                    model=None,
                    user_id=user_id,
                    temperature=0.2,
                    top_p=0.95,
                    tier="large",
                ))
                
                # Parse JSON
                classify_response = re.sub(r'```json\n?', '', classify_response)
                classify_response = re.sub(r'```\w*\n?', '', classify_response).strip()
                classify_response = classify_response.replace('```', '').strip()
                
                classification = json.loads(classify_response)
                intent = classification.get("intent", "edit")
                ai_message = classification.get("ai_message", "")
                create_topic = classification.get("create_topic", "")
                
                logging.info(f"🎯 [EDIT_MANAGER] Classified as: {intent}")
            
            # ═══════════════════════════════════════════════════════════════════════════
            # HANDLE GREETING INTENT
            # ═══════════════════════════════════════════════════════════════════════════
            if intent == "greeting":
                logging.info("💬 [EDIT_MANAGER] Greeting intent - returning message only")
                return JSONResponse({
                    "success": True,
                    "action_type": "message_only",
                    "ai_message": ai_message or "Hello! I'm your AI document assistant. I can edit content, add new pages, expand topics using your vault data, and reformat text. Just describe what you'd like to change!"
                })
            
            # ═══════════════════════════════════════════════════════════════════════════
            # HANDLE HELP INTENT
            # ═══════════════════════════════════════════════════════════════════════════
            if intent == "help":
                logging.info("❓ [EDIT_MANAGER] Help intent - returning capabilities")
                return JSONResponse({
                    "success": True,
                    "action_type": "message_only",
                    "ai_message": ai_message or "Here's what I can do:\n• Edit text: 'Make this more concise' or 'Fix the grammar'\n• Add content: 'Expand on this topic' or 'Add more details'\n• Create pages: 'Create a new page about conclusions'\n• Format: 'Add bullet points' or 'Make headers bold'\n\nSelect text to edit just that, or edit the whole page!"
                })
            
            # ═══════════════════════════════════════════════════════════════════════════
            # HANDLE CREATE_NEW INTENT
            # ═══════════════════════════════════════════════════════════════════════════
            if intent == "create_new":
                logging.info(f"🆕 [EDIT_MANAGER] Create new page intent - topic: {create_topic}")
                
                create_prompt = f"""You are creating a NEW page for a document.

REPORT GOAL: {goal}

EXISTING PAGE CONTENT (for context):
{current_content[:1000] if current_content else "No existing content"}

USER REQUEST: {instruction}
TOPIC: {create_topic}

Generate the content for this new page. 
Return a JSON response:
{{
  "new_title": "Suggested title for the new page",
  "new_content": "Full HTML content for the new page using <h2>, <h3>, <p>, <ul>, <li>, <strong>, <em>, <blockquote>, <table> tags",
  "ai_message": "Brief description of what you created (1 sentence)"
}}

IMPORTANT:
- Generate substantive, well-structured content
- Use proper HTML formatting (NO markdown)
- [OPTIONAL] If adding financial/numerical data BEST visualized as a chart, generate a VALID JSON chart config wrapped in <chart-config> tags (type: bar, line, pie, doughnut, radar, polarArea, scatter, bubble)
- The content should relate to the report goal and existing context
- Do NOT include any <img> tags, image URLs, or image placeholders (e.g. {{{{UserImage_...}}}})
- The user can upload their own images later — only generate text, tables, and charts
- Return ONLY valid JSON"""
                
                create_response = await asyncio.to_thread(lambda: llm_call(
                    system_prompt=_compose_grounded_system("You are a document creation assistant. Always respond with valid JSON. DATA ACCURACY: Do NOT hallucinate or fabricate numbers, statistics, projections, dates, or factual claims — use ONLY verifiable facts from provided context."),
                    user_prompt=create_prompt, 
                    model=None,
                    user_id=user_id,
                    max_tokens=8000,
                    temperature=0.2,
                    top_p=0.95,
                    tier="large",
                ))
                
                # Parse response
                create_response = re.sub(r'```json\n?', '', create_response)
                create_response = re.sub(r'```\w*\n?', '', create_response).strip()
                create_response = create_response.replace('```', '').strip()
                
                try:
                    create_data = json.loads(create_response)
                    new_content = create_data.get('new_content', '')
                    new_title = create_data.get('new_title', create_topic or 'New Page')
                    
                    # Defensive: ensure content is non-empty
                    if not new_content or len(new_content.strip()) < 10:
                        logging.warning(f"⚠️ [EDIT_MANAGER] create_new returned near-empty content (len={len(new_content)}), using fallback")
                        new_content = f"<h2>{new_title}</h2><p>Content could not be generated. Please try again with more details.</p>"
                    
                    logging.info(f"📄 [EDIT_MANAGER] create_new response: title='{new_title}', content_len={len(new_content)}, image_detected={bool('<img' in new_content.lower())}")
                    
                    return JSONResponse({
                        "success": True,
                        "action_type": "create_new",
                        "ai_message": create_data.get('ai_message', ai_message or 'Created a new page based on your request.'),
                        "new_content": new_content,
                        "new_title": new_title,
                        "page_id": page_id
                    })
                except json.JSONDecodeError as e:
                    logging.error(f"❌ [EDIT_MANAGER] Create new page JSON parse error: {e}")
                    # Fallback: treat the response as content
                    return JSONResponse({
                        "success": True,
                        "action_type": "create_new",
                        "ai_message": ai_message or "Created a new page based on your request.",
                        "new_content": f"<h2>{create_topic or 'New Page'}</h2>{create_response}",
                        "new_title": create_topic or "New Page",
                        "page_id": page_id
                    })

            # If intent is "edit", continue to the existing edit workflow below
            
        except Exception as classify_err:
            logging.error(f"❌ [EDIT_MANAGER] Intent classification failed: {classify_err}", exc_info=True)
            requires_vault = False  # Safe default: don't penalize simple edits with vault fetch
        
        # Debug logging
        logging.info(f"🎯 [EDIT_MANAGER] Starting edit workflow")
        logging.info(f"🎯 [EDIT_MANAGER] Instruction: {instruction[:100]}...")
        logging.info(f"🎯 [EDIT_MANAGER] Content length: {len(current_content)}")
        logging.info(f"🎯 [EDIT_MANAGER] Folder IDs: {folder_ids}")
        logging.info(f"🎯 [EDIT_MANAGER] Classifier requires_vault: {requires_vault}")
        
        # ═══════════════════════════════════════════════════════════════════════════
        # VAULT ACCESS: classifier decides whether to enable personal_data_tool.
        # Vault chunks are NOT pre-fetched anymore — the LLM calls the tool on
        # demand inside run_Enterprise_or_Personal_tool (cap=5 per call).
        # ═══════════════════════════════════════════════════════════════════════════
        _edit_use_personal = bool(requires_vault) and bool(folder_ids) and bool(user_id)
        vault_context = ""  # always empty; tool fetches on demand

        vault_section = ""
        if _edit_use_personal:
            vault_section = (
                "\n\nDATA TOOL: `personal_data_tool` is available "
                f"(scoped to {len(folder_ids)} folder(s)). Call it with a focused query "
                "for facts/passages you need from the user's vault BEFORE writing the "
                "edit. Cite each fact with [vault:<document_id>] inline.\n"
            )
            logging.info("⚡ [EDIT_MANAGER] personal_data_tool enabled for this edit")
        else:
            logging.info("⚡ [EDIT_MANAGER] No vault needed — direct edit")
        
        # Build edit mode specific instructions
        if edit_mode == 'selection':
            mode_prompt_section = f"""EDITING MODE: SELECTION
You are editing ONLY the selected text, not the entire page.
Selected text: "{selected_text}"

Return ONLY the replacement HTML for the selected portion.
Do NOT return the entire page content - only the replacement text with proper HTML formatting.
The returned content will replace the selected text.
For DELETE/REMOVE requests: Return an EMPTY STRING as the response to delete the selection.

🚫 USER MEDIA PROTECTION (CRITICAL):
- Elements with 'data-user-media="true"' or src containing '{{{{UserImage_' are USER-UPLOADED (images, videos, iframes)
- DO NOT modify, remove, or replace user media elements UNLESS user explicitly asks to
- PRESERVE user-uploaded images, videos, embeds (YouTube, Vimeo, Loom, etc.) as-is"""
        elif edit_mode == 'insertion':
            mode_prompt_section = """EDITING MODE: INSERTION
You are inserting NEW content at the cursor position.

Return ONLY the new HTML content to be inserted.
Do NOT return the entire page content - only the new content to insert.
The returned content will be placed at the cursor position."""
        else:
            mode_prompt_section = """EDITING MODE: OVERALL
You are modifying the entire page based on the user's instruction.
Return the COMPLETE edited page as HTML.
Preserve all existing content that the user didn't ask to change.

🚫 USER MEDIA PROTECTION (CRITICAL):
- Elements with 'data-user-media="true"' or src containing '{{{{UserImage_' are USER-UPLOADED (images, videos, iframes)
- DO NOT modify, remove, or replace user media elements UNLESS user explicitly asks to
- PRESERVE user-uploaded images, videos, embeds (YouTube, Vimeo, Loom, etc.) as-is
- You MAY add captions or wrap media in styled containers, but keep the src/href intact"""
        
        outline_section = f"\nDOCUMENT OUTLINE (context only — edit THIS page only):\n{document_outline}\n\nNOTE: If the DOCUMENT OUTLINE above conflicts with the actual PAGE CONTENT below, treat the PAGE CONTENT as the authoritative source of truth. The outline may be outdated from initial generation or stale after manual edits by the user.\n" if document_outline else ""
        
        # Unified edit prompt (single LLM call — with or without vault context)
        static_context = f"""You are editing a document page.

REPORT GOAL: {goal}
TYPE (Strictly follow): {report_type}
{outline_section}
{vault_section}
PAGE CONTENT:
{current_content}
"""

        prompt = f"""USER REQUEST: {instruction}

{mode_prompt_section}

IMPORTANT EDITING GUIDELINES:
- For SIMPLE EDITS (grammar, spelling, shortening, formatting, rephrasing), edit directly using your knowledge
- For CONTENT ADDITIONS (adding new information, expanding sections, research-based edits), use vault sources if available
{"- Return ONLY the replacement HTML for selected text, NOT the full page" if edit_mode == 'selection' else "- Return ONLY the new content to insert, NOT the full page" if edit_mode == 'insertion' else "- Always return the ENTIRE edited page, not just the changed section"}

RESPONSE FORMAT - Return ONLY clean HTML:
- Use HTML tags: <p>, <strong>, <em>, <h2>, <h3>, <h4>, <ul>, <ol>, <li>, <blockquote>
- Use HTML tables (<table>, <tr>, <th>, <td>) for structured data, comparisons, specifications, statistics
- [OPTIONAL] If the edit involves adding financial/numerical data BEST visualized as a chart, generate a VALID JSON chart config wrapped in <chart-config> tags:
  <chart-config>
  {{
    "type": "bar",
    "data": {{ "labels": ["Q1", "Q2"], "datasets": [{{ "label": "Revenue", "data": [100, 200] }}] }}
  }}
  </chart-config>
  (Supported types: bar, line, pie, doughnut, radar, polarArea, scatter, bubble. For scatter use data as [{{x,y}}], for bubble use [{{x,y,r}}].)
- NO markdown syntax (no **, ##, ```, etc.)
- NO JSON wrapping, NO explanations - just the HTML content
- Preserve any existing [Source X] citations"""

        full_prompt = f"{static_context}\n\n{prompt}"
        _edit_system = _compose_grounded_system(
            "You are a professional content editor refining report content. "
            "Maintain the original meaning while improving clarity, structure, "
            "and formatting. DATA ACCURACY: Do NOT hallucinate or fabricate "
            "numbers, statistics, projections, dates, or factual claims — use "
            "ONLY verifiable facts from provided context or tool results."
        )
        if _edit_use_personal:
            from services.enterprise_tools import run_Enterprise_or_Personal_tool
            result_content = await run_Enterprise_or_Personal_tool(
                prompt=full_prompt,
                system=_edit_system + "\n\n" + COMPUTE_FACT_ROUTING_RULE,
                user_id=user_id,
                tier="large",
                temperature=0.2,
                max_tokens=8000,
                filter_tools="auto",
                use_personal_data=True,
                selected_folder_ids=folder_ids,
                max_results_cap=5,  # ai-edit per-section content: max 5 chunks per call
                expose_enterprise_tools=False,
                personal_tool_expand_subqueries=False,
                extra_tools=[build_compute_fact_tool_schema()],
                extra_tool_dispatch=make_compute_fact_dispatcher(
                    user_id=user_id, folder_ids=folder_ids,
                    log_prefix="REPORT-AI-EDIT-FACT",
                ),
            )
        else:
            result_content = await asyncio.to_thread(lambda: llm_call(
                system_prompt=_edit_system,
                user_prompt=full_prompt,
                model=None,
                user_id=user_id,
                max_tokens=8000,
                temperature=0.2,
                top_p=0.95,
                tier="large",
            ))
        
        # Clean markdown fences if AI added them despite instructions
        if result_content:
            result_content = re.sub(r'```html\n?', '', result_content)
            result_content = re.sub(r'```\w*\n?', '', result_content).strip()
            result_content = result_content.replace('```', '').strip()
        
        # Validate any <chart-config> tags
        if result_content:
            from services.personal_data_tool import strip_citation_tags
            result_content = strip_citation_tags(result_content)
            result_content = _validate_chart_config_tags(result_content)
        
        # Handle empty response
        if not result_content or not result_content.strip():
            logging.error(f"🎯 [EDIT_MANAGER] Empty response from LLM")
            return JSONResponse({
                "success": False,
                "error": "Empty AI response",
                "message": "AI couldn't process the request. Please try again."
            })
        
        used_vault = bool(_edit_use_personal)  # Tool was offered; LLM decided whether to call
        workflow = "edit_with_vault" if used_vault else "quick_edit"
        logging.info(f"✅ [EDIT_MANAGER] Edit completed (workflow={workflow})")
        logging.info(f"✅ [EDIT_MANAGER] Edited content length: {len(result_content)} chars")
        logging.info(f"✅ [EDIT_MANAGER] Edit mode: {edit_mode}, used_vault: {used_vault}")
        
        # Generate ai_message based on the action
        is_deletion = any(word in instruction.lower() for word in ['remove', 'delete', 'clear', 'erase'])
        if is_deletion and edit_mode == 'selection':
            ai_message = "Removed the selected content as requested."
        elif edit_mode == 'selection':
            ai_message = "Updated the selected text with your requested changes." if not used_vault else "Updated the selected text using information from your vault."
        elif edit_mode == 'insertion':
            ai_message = "Inserted new content at the cursor position." if not used_vault else "Added new content from your vault at the cursor position."
        else:
            ai_message = "Applied your edits to the page content." if not used_vault else "Enhanced the page content using relevant information from your vault."
        
        return JSONResponse({
            "success": True,
            "action_type": "edit",
            "ai_message": ai_message,
            "edited_content": result_content,
            "page_id": page_id,
            "used_vault_data": used_vault,
            "workflow": workflow,
            "edit_mode": edit_mode
        })
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"❌ [EDIT_MANAGER] Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing edit: {str(e)}"
        )


# ═══════════════════════════════════════════════════════════════════════════════════════
# Document-Level Edit Planner for Reports (prevents redundancy across pages)
# ═══════════════════════════════════════════════════════════════════════════════════════

def _recover_truncated_plan(raw: str, num_pages: int, instruction: str):
    """
    Extract key decisions from a truncated planner JSON response.
    The LLM outputs requires_vault and create_new FIRST, so even if the pages
    array gets cut off, we can recover the top-level decisions and build a
    usable plan from whatever page entries are complete.
    """
    import re as _re
    import json as _json

    # Extract top-level booleans via regex
    vault_match = _re.search(r'"requires_vault"\s*:\s*(true|false)', raw, _re.IGNORECASE)
    create_match = _re.search(r'"create_new"\s*:\s*(true|false)', raw, _re.IGNORECASE)
    topic_match = _re.search(r'"new_topic"\s*:\s*"([^"]*)"', raw)

    if not vault_match:
        return None  # Can't recover anything useful

    requires_vault = vault_match.group(1).lower() == "true"
    create_new = create_match.group(1).lower() == "true" if create_match else False
    new_topic = topic_match.group(1) if topic_match else ""

    # Try to extract complete page entries from the truncated pages array
    page_map = {}
    page_pattern = _re.compile(
        r'\{\s*"slide_index"\s*:\s*(\d+)\s*,\s*"specific_instruction"\s*:\s*"([^"]*)"\s*,\s*"skip"\s*:\s*(true|false)\s*\}',
        _re.IGNORECASE
    )
    for m in page_pattern.finditer(raw):
        idx = int(m.group(1))
        instr = m.group(2)
        skip = m.group(3).lower() == "true"
        if not skip and 0 <= idx < num_pages and instr:
            page_map[idx] = instr

    # If we got no complete page entries, fall back to all pages with the original instruction
    if not page_map and not create_new:
        page_map = {i: instruction for i in range(num_pages)}

    logging.info(
        f"🔧 [SMART-PLANNER] Recovered from truncated JSON: "
        f"requires_vault={requires_vault}, create_new={create_new}, pages={len(page_map)}/{num_pages}"
    )
    return {
        "create_new": create_new,
        "new_topic": new_topic,
        "requires_vault": requires_vault,
        "pages": page_map,
    }


async def plan_edit_all(
    instruction: str,
    full_pages: list,
    pages_summary: list,
    user_id: str,
    goal: str = "",
    report_type: str = "report",
    is_update_all: bool = False,
    current_page_index: int = 0,
):
    """
    Unified Smart Planner — single LLM call that replaces the old 3-step decision pipeline
    (relevance classification + parallel classifier + per-page planner).

    Decides in ONE pass:
      1. Whether this is a CREATE NEW request
      2. Whether vault/reference data is needed
      3. Which pages to edit and with what per-page instruction

    Returns dict:
      {
        "create_new": bool,
        "new_topic": str,
        "requires_vault": bool,
        "pages": {page_index: specific_instruction, ...}
      }
    Falls back to safe defaults on failure (all pages, requires_vault=True).
    """
    def _extract_text(page, max_len=1200):
        import re as _re
        parts = []
        if page.get('title'):
            parts.append(page['title'])
        content = page.get('content', '')
        if content:
            plain = _re.sub(r'<[^>]*>', ' ', content)
            plain = plain.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
            plain = _re.sub(r'\s+', ' ', plain).strip()
            parts.append(plain)
        text = ' '.join(parts)
        return text[:max_len] if len(text) > max_len else text

    # Build per-page context for the planner
    page_parts = []
    for i, s in enumerate(pages_summary):
        full_text = _extract_text(full_pages[i]) if i < len(full_pages) else s.get('text_summary', '')
        section_order = s.get('section_order', i + 1)
        current_marker = " ⬅ USER IS VIEWING THIS PAGE" if i == current_page_index else ""
        page_parts.append(
            f"Page {i + 1} (index {i}){current_marker}: [Title: \"{s.get('title', 'Untitled')}\"] "
            f"Section {section_order}. "
            f"Content: \"{full_text[:1000]}\""
        )
    pages_ctx = "\n".join(page_parts)

    update_all_note = """
NOTE — UPDATE-ALL MODE: The user has uploaded new data into their vault and wants the entire report updated
against that data. You MUST set requires_vault: true. For each page, instruct precise comparison of current
content against the vault reference data — update what changed, preserve what is still accurate.""" if is_update_all else ""

    plan_prompt = f"""You are a smart document-edit planner. Given the user's instruction and the full document outline,
make ALL of the following decisions in a single response:

1. **CREATE NEW**: Is the user asking to create a brand-new page/section? (e.g. "add a page about X")
2. **VAULT NEED**: Does fulfilling this instruction require fetching reference data from the user's vault/files?
   - YES if: adding factual content, updating data/figures, incorporating uploaded files, "use my data", "update with latest"
   - NO if: grammar/typo fixes, formatting/styling, reorganizing existing text, deleting content, font/color changes
3. **PER-PAGE PLAN**: For each page, decide whether it needs editing and provide a specific instruction.

USER IS VIEWING: Page {current_page_index + 1} (index {current_page_index}) — if the user says "this page" or "this one", they mean that page.

REPORT GOAL: {goal or 'N/A'}
REPORT TYPE: {report_type}
{update_all_note}

USER INSTRUCTION: "{instruction}"

DOCUMENT ({len(pages_summary)} pages):
{pages_ctx}

RULES:
- If the instruction is about CREATING NEW content (new page/section), set create_new: true and provide new_topic
- For GLOBAL changes (grammar, formatting, theme, proofreading), include ALL pages with appropriate instructions
- For TARGETED changes (specific content edits), only include pages whose content is relevant
- For ambiguous scope, include at minimum the current page (index {current_page_index})
- Each page instruction must be SPECIFIC and UNIQUE — no redundancy across pages
- For formatting/style, give each page the same styling instruction
- For content edits, ensure each page covers a DIFFERENT aspect
- Keep per-page specific_instruction to ≤10 words (e.g. "Fix grammar and typos" NOT "Review the text for grammatical errors including subject-verb agreement and fix any typos found throughout the paragraphs")
- Set skip: true for pages that genuinely need no changes for this instruction

Return ONLY valid JSON:
{{
  "create_new": false,
  "new_topic": "",
  "requires_vault": false,
  "pages": [
    {{"slide_index": 0, "specific_instruction": "...", "skip": false}},
    {{"slide_index": 1, "specific_instruction": "...", "skip": true}},
    ...
  ]
}}"""

    fallback = {
        "create_new": False,
        "new_topic": "",
        "requires_vault": True,
        "pages": {i: instruction for i in range(len(full_pages))},
    }

    try:
        from services.parallel_classifier import _parse_json
        max_tok = max(3500, len(pages_summary) * 250)
        plan_response = await asyncio.to_thread(
            llm_call, "", plan_prompt,
            None,
            user_id,
            None,
            max_tok,
            0.3,
            0.95
        )
        plan = _parse_json(plan_response, None)
        if plan is None:
            # Try to recover key decisions from truncated JSON
            recovered = _recover_truncated_plan(plan_response, len(full_pages), instruction)
            if recovered is not None:
                if is_update_all:
                    recovered["requires_vault"] = True
                return recovered
            logging.warning(f"⚠️ [SMART-PLANNER] Unparseable response, using fallback. Raw (500 chars): {plan_response[:500]}")
            return fallback

        # Extract decisions
        create_new = plan.get("create_new", False)
        new_topic = plan.get("new_topic", "") or ""
        requires_vault = plan.get("requires_vault", True)

        # Force vault for update-all mode
        if is_update_all:
            requires_vault = True

        # Parse per-page plan
        page_entries = plan.get("pages", [])
        if isinstance(page_entries, dict):
            page_entries = list(page_entries.values())

        page_map = {}
        for entry in page_entries:
            idx = entry.get("slide_index")
            if idx is None or not (0 <= idx < len(full_pages)):
                continue
            if entry.get("skip", False):
                continue
            specific = entry.get("specific_instruction", "")
            if specific:
                page_map[idx] = specific

        # If planner returned no pages but it's not a create_new, fall back to all pages
        if not page_map and not create_new:
            logging.warning("⚠️ [SMART-PLANNER] No actionable pages, falling back to all pages")
            page_map = {i: instruction for i in range(len(full_pages))}

        result = {
            "create_new": create_new,
            "new_topic": new_topic,
            "requires_vault": requires_vault,
            "pages": page_map,
        }
        logging.info(
            f"✅ [SMART-PLANNER] create_new={create_new}, requires_vault={requires_vault}, "
            f"pages_to_edit={len(page_map)}/{len(full_pages)}"
        )
        return result

    except Exception as e:
        logging.error(f"❌ [SMART-PLANNER] Failed: {e}, using fallback")
        return fallback


# ═══════════════════════════════════════════════════════════════════════════════════════
# AI Edit-All Endpoint (Smart Multi-Page for Reports)
# ═══════════════════════════════════════════════════════════════════════════════════════

async def _edit_all_process(payload: dict, user_id: str):
    """
    Core processing logic for ai-edit-all.
    Returns JSONResponse with batch edits.
    """
    try:
        instruction = payload.get('instruction', '')
        pages_summary = payload.get('pages_summary', [])  # [{page_index, page_id, text_summary}]
        full_pages = payload.get('full_pages', [])  # [{content: html, id: ...}]
        current_page_index = payload.get('current_page_index', 0)
        folder_ids = payload.get('folder_ids', [])
        goal = payload.get('goal', '')
        report_type = payload.get('report_type', 'report')
        is_update_all = payload.get('is_update_all', False)
        
        if not user_id:
            logging.warning("⚠️ [EDIT-ALL] No user_id resolved from request — vault/SaaS retrieval will fail")
        if not folder_ids:
            logging.warning("⚠️ [EDIT-ALL] No folder_ids in payload — SaaS and folder-scoped retrieval will be skipped")
        
        if not instruction.strip():
            raise HTTPException(status_code=400, detail="Instruction is required")
        
        logging.info(f"🎯 [EDIT-ALL] Instruction: {instruction[:80]}... | {len(pages_summary)} pages")
        
        # STEP 1: Unified Smart Planner — single LLM call replaces old 3-step pipeline
        # (relevance classification + parallel classifier + per-page planner)
        plan = await plan_edit_all(
            instruction=instruction,
            full_pages=full_pages,
            pages_summary=pages_summary,
            user_id=user_id,
            goal=goal,
            report_type=report_type,
            is_update_all=is_update_all,
            current_page_index=current_page_index,
        )

        # STEP 2: Handle CREATE_NEW — generate full content
        if plan.get("create_new"):
            topic = plan.get("new_topic", "") or instruction
            logging.info(f"🆕 [EDIT-ALL] Create new page: {topic}")
            
            # Build context from existing pages
            existing_context = ""
            if full_pages:
                ctx_page = full_pages[min(current_page_index, len(full_pages) - 1)]
                existing_context = ctx_page.get('content', '')[:1000]
            
            # Vault chunks now fetched agentically by the LLM via
            # personal_data_tool inside run_Enterprise_or_Personal_tool below.
            _create_use_personal = bool(folder_ids) and bool(user_id)
            vault_section_create = (
                "\n\nDATA TOOL: `personal_data_tool` is available "
                f"(scoped to {len(folder_ids)} folder(s)). Call it with a focused "
                "query for the new page's topic to ground content in the user's "
                "vault. Cite each fact with [vault:<document_id>] inline.\n"
                if _create_use_personal else ""
            )
            
            create_prompt = f"""You are creating a NEW page for a document.

REPORT GOAL: {goal}
{vault_section_create}
EXISTING PAGE CONTENT (for context):
{existing_context if existing_context else "No existing content"}

USER REQUEST: {instruction}
TOPIC: {topic}

Generate the content for this new page.
Return a JSON response:
{{
  "new_title": "Suggested title for the new page",
  "new_content": "Full HTML content for the new page using <h2>, <h3>, <p>, <ul>, <li>, <strong>, <em>, <blockquote>, <table> tags",
  "ai_message": "Brief description of what you created (1 sentence)"
}}

IMPORTANT:
- Generate substantive, well-structured content
- Use proper HTML formatting (NO markdown)
- [OPTIONAL] If adding financial/numerical data BEST visualized as a chart, generate a VALID JSON chart config wrapped in <chart-config> tags (type: bar, line, pie, doughnut, radar, polarArea, scatter, bubble)
- The content should relate to the report goal and existing context
- Do NOT include any <img> tags, image URLs, or image placeholders (e.g. {{{{UserImage_...}}}})
- The user can upload their own images later — only generate text, tables, and charts
- Return ONLY valid JSON"""

            try:
                if _create_use_personal:
                    from services.enterprise_tools import run_Enterprise_or_Personal_tool
                    create_response = await run_Enterprise_or_Personal_tool(
                        prompt=create_prompt,
                        system="You are a document creation assistant. Always respond with valid JSON.\n\n" + COMPUTE_FACT_ROUTING_RULE,
                        user_id=user_id,
                        tier="large",
                        temperature=0.2,
                        max_tokens=8000,
                        filter_tools="auto",
                        use_personal_data=True,
                        selected_folder_ids=folder_ids,
                        max_results_cap=5,  # edit-all create-new: max 5 chunks per call
                        expose_enterprise_tools=False,
                        personal_tool_expand_subqueries=False,
                        extra_tools=[build_compute_fact_tool_schema()],
                        extra_tool_dispatch=make_compute_fact_dispatcher(
                            user_id=user_id, folder_ids=folder_ids,
                            log_prefix="REPORT-EDIT-ALL-CREATE-FACT",
                        ),
                    )
                else:
                    create_response = await asyncio.to_thread(lambda: llm_call(
                        system_prompt="You are a document creation assistant. Always respond with valid JSON.",
                        user_prompt=create_prompt,
                        model=None,
                        user_id=user_id,
                        temperature=0.2,
                        top_p=0.95,
                        tier="large",
                    ))
                
                create_response = re.sub(r'```json\n?', '', create_response)
                create_response = re.sub(r'```\w*\n?', '', create_response).strip()
                create_response = create_response.replace('```', '').strip()
                
                create_data = json.loads(create_response)
                new_content = create_data.get('new_content', '')
                new_title = create_data.get('new_title', topic)
                ai_msg = create_data.get('ai_message', f'Created a new page about {topic}.')
            except Exception as gen_err:
                logging.warning(f"⚠️ [EDIT-ALL] Content generation failed for create_new: {gen_err}, returning topic-only")
                new_content = f"<h2>{topic}</h2><p>Content generation is in progress. Please try again.</p>"
                new_title = topic
                ai_msg = f"Created a new page about {topic}."
            
            # Use current_page_index for insertion position (not end of document)
            after_idx = min(current_page_index, len(full_pages) - 1) if full_pages else 0
            
            logging.info(f"📄 [EDIT-ALL] create_new: title='{new_title}', content_len={len(new_content)}, after_index={after_idx}")
            
            return JSONResponse({
                "success": True,
                "edits": [{
                    "slide_index": -1, "action": "create",
                    "topic": new_title,
                    "content": new_content,
                    "after_slide_index": after_idx
                }],
                "total_matched": 0, "total_slides": len(full_pages),
                "intent": "create_new", "ai_message": ai_msg
            })
        
        # STEP 3: Edit pages per smart planner
        edit_plan = plan.get("pages", {})
        requires_vault = plan.get("requires_vault", True)
        sorted_edit_indices = sorted(edit_plan.keys())
        
        logging.info(f"🎯 [EDIT-ALL] Editing {len(sorted_edit_indices)} of {len(full_pages)} pages (requires_vault={requires_vault})")
        
        # Build document outline for LLM context
        doc_outline = build_document_outline(pages_summary)
        outline_section = f"\nDOCUMENT OUTLINE (context only \u2014 edit THIS page only):\n{doc_outline}\n\nNOTE: If the DOCUMENT OUTLINE above conflicts with the actual PAGE CONTENT below, treat the PAGE CONTENT as the authoritative source of truth. The outline may be outdated from initial generation or stale after manual edits by the user.\n" if doc_outline else ""

        # Edit each relevant page using existing ai-edit logic (parallel with semaphore)
        semaphore = asyncio.Semaphore(5)
        edits = []
        
        async def edit_page(idx):
            async with semaphore:
                page = full_pages[idx]
                page_content = page.get('content', '')
                page_id = page.get('id') or pages_summary[idx].get('page_id', f'page_{idx}')
                
                # Use per-page instruction from planner if available, else raw instruction
                page_instruction = edit_plan.get(idx, instruction) if edit_plan else instruction
                
                try:
                    # Strip base64 image data to save tokens — AI can't read pixels anyway
                    # Preserve alt text which contains chart data summaries
                    import re as _re
                    cleaned_content = _re.sub(
                        r'<img([^>]*?)src="data:image/[^"]+"([^>]*?)/>',
                        lambda m: f'<img{m.group(1)}src="[IMAGE]"{m.group(2)}/>',
                        page_content
                    )
                    # Also handle src without self-closing
                    cleaned_content = _re.sub(
                        r'<img([^>]*?)src="data:image/[^"]+"([^>]*?)>',
                        lambda m: f'<img{m.group(1)}src="[IMAGE]"{m.group(2)}>',
                        cleaned_content
                    )

                    # Reuse the same two-stage assessment logic
                    # Stage 1: Quick assessment (can we edit without vault?)
                    if not requires_vault:
                        # Direct edit without vault
                        if is_update_all:
                            no_vault_rules = """- The user has uploaded new files in their vault. Compare the current page content against the user's instruction and make PRECISE changes.
- Change exactly what the data/instruction demands — no more, no less.
- Preserve the HTML structure and formatting unless the content changes require structural adjustment.
- If the instruction calls for significant content changes, restructure as needed; otherwise keep layout stable."""
                            no_vault_system = "You are a professional document editor. Compare the current content against the user's instruction and make precise, targeted edits. Preserve content that is still accurate. Return ONLY the edited HTML content."
                        else:
                            no_vault_rules = """- Preserve the HTML structure and formatting
- Make ONLY changes related to the instruction"""
                            no_vault_system = "You are a professional document editor. Edit the HTML content based on the user's instruction. Return ONLY the edited HTML content."

                        edit_prompt = f"""Edit this HTML content based on the user's instruction.
{outline_section}
INSTRUCTION: {page_instruction}

CURRENT CONTENT:
{cleaned_content[:15000]}

Rules:
- Return ONLY the edited HTML content
{no_vault_rules}
- Do NOT wrap in code blocks
- CHART IMAGES: If an <img> has alt text containing "Chart | Data:" it is a rendered chart. If the user asks to update chart data, REPLACE the <img> tag with a <chart-config> tag containing updated Chart.js JSON. Example: <chart-config>{{"type":"bar","data":{{"labels":[...],"datasets":[...]}}}}</chart-config>
- For non-chart images, preserve the <img> tag as-is
- USER MEDIA: Elements with 'data-user-media="true"' or src containing '{{{{UserImage_' are user-uploaded. You MUST include ALL such <img> tags in your output exactly as they appear in the input. Dropping them is a critical error. Preserve them unless the user explicitly asks to remove them."""
                        
                        edited_content = await asyncio.to_thread(
                            llm_call,
                            no_vault_system,
                            edit_prompt,
                            None,
                            user_id,
                            None,
                            8000
                        )
                    else:
                        # Vault chunks now fetched agentically by the LLM via
                        # personal_data_tool inside run_Enterprise_or_Personal_tool.
                        _page_title = page.get('title', '')

                        # Retrieve structured data (Excel/CSV) for chart-oriented edits.
                        # Schema-only metadata stays pre-fetched (small, helps the LLM
                        # decide whether to use execute_code on the file).
                        structured_data_context = await get_structured_data_context(
                            user_id, page_instruction, _page_title, folder_ids
                        )

                        if is_update_all:
                            vault_intro = f"""Edit this HTML content based on the user's instruction.
Pull the LATEST reference data from the user's vault via `personal_data_tool`. Compare it against the current page content and make PRECISE updates."""
                            vault_rules = """- Compare the current page content against vault data (fetched via personal_data_tool) and make PRECISE changes.
- Change only what the new data demands: if numbers changed, update numbers; if the narrative shifted, update the narrative; if the topic is fundamentally different, restructure as needed.
- Preserve HTML structure and formatting unless the content changes require structural adjustment.
- Do NOT change content that is still accurate and aligned with the reference data.
- Update charts and tables only where the data has actually changed."""
                            vault_system = "You are a professional document editor. Compare the current content against vault data (fetched via personal_data_tool) and make precise, targeted edits. Preserve content that is still accurate. You may restructure only if the data demands it. Return ONLY the edited HTML content."
                        else:
                            vault_intro = f"""Edit this HTML content based on the user's instruction.
Pull relevant reference data from the user's vault via `personal_data_tool` to enhance or update the content."""
                            vault_rules = """- Preserve the HTML structure and formatting
- Pull relevant data from the user's vault via personal_data_tool and incorporate it
- Make ONLY changes related to the instruction
- Cite vault facts inline with [vault:<document_id>]"""
                            vault_system = "You are a professional document editor. Edit the HTML content based on the user's instruction. Use personal_data_tool to fetch relevant reference data. Return ONLY the edited HTML content."

                        edit_prompt = f"""{vault_intro}
{outline_section}
INSTRUCTION: {page_instruction}

{structured_data_context}

CURRENT CONTENT:
{cleaned_content[:12000]}

Rules:
- Return ONLY the edited HTML content
{vault_rules}
- Do NOT wrap in code blocks
- CHART IMAGES: If an <img> has alt text containing "Chart | Data:" it is a rendered chart. If the user asks to update chart data, REPLACE the <img> tag with a <chart-config> tag containing updated Chart.js JSON. Example: <chart-config>{{"type":"bar","data":{{"labels":[...],"datasets":[...]}}}}</chart-config>
- For non-chart images, preserve the <img> tag as-is
- USER MEDIA: Elements with 'data-user-media="true"' or src containing '{{{{UserImage_' are user-uploaded. You MUST include ALL such <img> tags in your output exactly as they appear in the input. Dropping them is a critical error. Preserve them unless the user explicitly asks to remove them."""

                        from services.enterprise_tools import run_Enterprise_or_Personal_tool
                        edited_content = await run_Enterprise_or_Personal_tool(
                            prompt=edit_prompt,
                            system=vault_system + "\n\n" + COMPUTE_FACT_ROUTING_RULE,
                            user_id=user_id,
                            tier="large",
                            temperature=0.2,
                            max_tokens=8000,
                            filter_tools="auto",
                            use_personal_data=True,
                            selected_folder_ids=folder_ids,
                            max_results_cap=5,  # edit-all per-page edit: max 5 chunks per call
                            expose_enterprise_tools=False,
                            personal_tool_expand_subqueries=False,
                            extra_tools=[build_compute_fact_tool_schema()],
                            extra_tool_dispatch=make_compute_fact_dispatcher(
                                user_id=user_id, folder_ids=folder_ids,
                                log_prefix="REPORT-EDIT-ALL-EDIT-FACT",
                            ),
                        )
                    
                    # Clean response
                    if edited_content:
                        edited_content = re.sub(r'^```html\n?', '', edited_content.strip())
                        edited_content = re.sub(r'\n?```$', '', edited_content.strip())
                        from services.personal_data_tool import strip_citation_tags
                        edited_content = strip_citation_tags(edited_content)
                        edited_content = _validate_chart_config_tags(edited_content)
                    
                    if edited_content and edited_content.strip():
                        # Extract updated title from first <h1> or <h2> in returned HTML
                        _title_match = _re.search(r'<h[12][^>]*>(.*?)</h[12]>', edited_content, _re.IGNORECASE)
                        _extracted_title = _re.sub(r'<[^>]+>', '', _title_match.group(1)).strip() if _title_match else None
                        return {
                            "slide_index": idx,
                            "action": "update",
                            "content": edited_content,
                            "topic": _extracted_title or page.get('title', ''),
                            "page_id": page_id,
                            "ai_message": f"Updated page {idx + 1}"
                        }
                except Exception as e:
                    logging.error(f"❌ [EDIT-ALL] Page {idx} failed ({type(e).__name__}): {e}\n{traceback.format_exc()}")
                return None
        
        tasks = [edit_page(idx) for idx in sorted_edit_indices]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for r in results:
            if isinstance(r, Exception):
                logging.error(f"❌ [EDIT-ALL] Task exception: {r}")
                continue
            if r is not None:
                edits.append(r)
        
        success_count = len(edits)
        fail_count = len(sorted_edit_indices) - success_count
        ai_message = (
            f"Updated {success_count} of {len(sorted_edit_indices)} relevant pages (out of {len(full_pages)} total)."
            if fail_count == 0 else f"Updated {success_count} pages. {fail_count} failed."
        )
        
        return JSONResponse({
            "success": True, "edits": edits,
            "total_matched": len(sorted_edit_indices), "total_slides": len(full_pages),
            "intent": "edit", "ai_message": ai_message
        })
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"❌ [EDIT-ALL] Error ({type(e).__name__}): {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error processing batch edit ({type(e).__name__}): {str(e)}")


@router.post("/composer/ai-edit-all")
async def ai_edit_all_pages(request: Request):
    """
    Streaming wrapper for ai-edit-all — sends keepalive whitespace every 15 seconds
    to prevent reverse-proxy (Traefik/ALB) timeouts on long-running multi-page AI edits.
    The final JSON payload is identical to the non-streaming version.
    """
    # Pre-read body and auth BEFORE the StreamingResponse starts — the ASGI receive
    # channel becomes unreadable once the response begins streaming, so request.json()
    # inside asyncio.create_task() would hang forever.
    payload = await request.json()
    user_id = get_secure_user_id(request)

    async def _keepalive_stream():
        done = asyncio.Event()
        result_bytes = [None]

        async def _run():
            try:
                response = await _edit_all_process(payload, user_id)
                result_bytes[0] = response.body
            except HTTPException as he:
                logging.error(f"❌ [EDIT-ALL] Stream wrapper caught HTTPException: {he.status_code} {he.detail}")
                error_body = {"success": False, "error": True, "status_code": he.status_code, "detail": he.detail}
                result_bytes[0] = json.dumps(error_body).encode()
            except Exception as e:
                logging.error(f"❌ [EDIT-ALL] Stream wrapper error ({type(e).__name__}): {e}\n{traceback.format_exc()}")
                error_body = {"success": False, "error": True, "status_code": 500,
                              "detail": f"Error processing batch edit ({type(e).__name__}): {str(e)}"}
                result_bytes[0] = json.dumps(error_body).encode()
            finally:
                done.set()

        asyncio.create_task(_run())

        while not done.is_set():
            try:
                await asyncio.wait_for(done.wait(), timeout=15)
            except asyncio.TimeoutError:
                yield b" \n"

        if result_bytes[0]:
            yield result_bytes[0]
        else:
            logging.error("❌ [EDIT-ALL] Stream wrapper: result_bytes was never set, yielding fallback error")
            fallback = {"success": False, "error": True, "status_code": 500, "detail": "Internal error: no response generated"}
            yield json.dumps(fallback).encode()

    return StreamingResponse(
        _keepalive_stream(),
        media_type="application/json",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# LEGACY ENDPOINTS (kept for compatibility, simplified)
# ═══════════════════════════════════════════════════════════════════════════════════════

@router.post("/composer/generate-outline", deprecated=True)
async def generate_report_outline(request: Request):
    """
    LEGACY / DEPRECATED — Marked for deletion.
    UI uses /composer/break-goal-stream for initial outline
    and /composer/generate-outline (ReportComposer refresh) which hits this.
    Lacks internet search, vault context, and structured-file context.
    Remove once ReportComposer refresh is migrated to break-goal-stream.
    """
    try:
        payload = await request.json()
        
        report_goal = payload.get('report_goal', {})
        existing_outline = payload.get('existing_outline', None)
        user_id = get_secure_user_id(request)
        user_email = get_user_email(request)
        
        purpose = report_goal.get('purpose', '')
        
        existing_outline_section = ""
        if existing_outline and isinstance(existing_outline, list) and len(existing_outline) > 0:
            outline_items = json.dumps([{"id": item.get('id', i+1), "title": item.get('title', ''), "objective": item.get('outline', '')} for i, item in enumerate(existing_outline)])
            existing_outline_section = f"""\n\nEXISTING SECTION OUTLINE (use the SAME "id" values so changes map back to original sections):
{outline_items}

IMPORTANT: Return EXACTLY {len(existing_outline)} sections, each keeping its original "id".
- If a section is still relevant to the PURPOSE and CONTEXT: refine its title and objective.
- If a section is NO LONGER valid or applicable given the purpose/context: completely rewrite its title and objective to something that IS relevant. Do NOT keep outdated or irrelevant content.
- You have full freedom to overhaul every section if the data warrants it. The only constraint is keeping the same count and the same id values."""

        # Use break-goal logic
        prompt = f"""Create a document outline for:

PURPOSE: {purpose}
AUDIENCE: {report_goal.get('targetAudience', 'General')}
TOPICS: {', '.join(report_goal.get('keyTopics', []))}
TONE: {report_goal.get('tone', 'professional')}{existing_outline_section}

Return JSON:
{{
    "suggested_topic": "A concise 1-2 sentence topic/purpose that best captures the document focus given the PURPOSE and any context. You have FULL FREEDOM to completely rewrite this if the data warrants a different angle.",
    "title": "Document Title",
    "sections": [
        {{
            "id": 1,
            "title": "Section Title",
            "objective": "What this section covers",
            "key_points": ["point1", "point2"]
        }}
    ]
}}"""

        response = await asyncio.to_thread(lambda: llm_call(
            system_prompt="You are an expert at creating structured report outlines. Generate logical, comprehensive outlines with clear objectives and key points.",
            user_prompt=prompt,
            model=None,
            user_id=user_id,
            max_tokens=8000,
            temperature=0.2,
            top_p=0.95,
            tier="large",
        ))
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            outline = json.loads(json_match.group())
        else:
            outline = {
                "title": purpose or "New Report",
                "sections": [
                    {"id": 1, "title": "Introduction", "objective": "Overview", "key_points": []}
                ]
            }
        
        return JSONResponse({
            "outline": outline,
            "suggested_topic": outline.get('suggested_topic', ''),
            "estimated_pages": len(outline.get('sections', [])),
            "key_sections": [s.get('title', '') for s in outline.get('sections', [])],
            "success": True
        })
    
    except Exception as e:
        logging.error(f"Error generating outline: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating outline: {str(e)}"
        )


# ==================== Agentic Report Editor (Claude-on-Word) ====================

from pydantic import BaseModel as _BaseModel, Field as _Field
from typing import Optional as _Optional, List as _List, Dict as _Dict, Any as _Any


class AgentReportEditRequest(_BaseModel):
    """Agentic whole-report edit — the entire document (per-page HTML) is sent in
    one shot; the LLM works in rounds and streams operations the ReportComposer
    applies (patch_page/edit_page/add/delete/reorder/update_letterhead/...)."""
    instruction: str = _Field(..., description="User's natural-language chat message")
    pages: _List[_Dict[str, _Any]] = _Field(..., description="ENTIRE document: [{id, title, content(HTML), order}]")
    current_page_index: int = _Field(default=0, description="Index of the page the user is viewing")
    metadata: _Optional[_Dict[str, _Any]] = _Field(default=None, description="Report metadata incl. title/goal/letterheadConfig/headerConfig/footerConfig")
    chat_history: _Optional[_List[_Dict[str, _Any]]] = _Field(default=None, description="Recent chat turns [{role,text}]")
    folder_ids: _Optional[_List[str]] = _Field(default=None, description="Vault folder IDs for grounding")
    selected_text: _Optional[str] = _Field(default=None, description="Text the user has selected in the editor ('this' refers to it)")


@router.post("/composer/agent-edit-stream")
async def composer_agent_edit_stream(request: Request, body: AgentReportEditRequest):
    """Agentic report edit (SSE). Streams status / operations / ask_user / finish
    events — same protocol as the presentation/printable agent editors."""
    from services.agent_report_editor import agent_edit_report_streaming
    user_id = get_secure_user_id(request)

    async def event_generator():
        async for event in agent_edit_report_streaming(
            instruction=body.instruction,
            pages=body.pages,
            user_id=user_id,
            current_index=body.current_page_index,
            metadata=body.metadata,
            chat_history=body.chat_history,
            folder_ids=body.folder_ids,
            selected_text=body.selected_text,
        ):
            yield event

    return StreamingResponse(event_generator(), media_type="text/event-stream")
