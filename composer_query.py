# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Composer Query API - Dedicated endpoint for Report Composer AI assistance

This module provides AI assistance specifically designed for the Report Composer,
with optimized processing for content generation, review, and suggestions.

Unlike the main query API which is designed for chat interactions, this endpoint
is optimized for:
- Content expansion and generation
- Writing review and suggestions
- Context-aware report assistance
- Simplified response format
- Chart data generation from structured data (Excel, JSON, SaaS)
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from citra_auth import get_secure_user_id, get_user_email
from citra_mongo import get_sync_database

import logging
import json
import re
import time
import uuid
import os
import asyncio

# Import the existing reply function and utilities

from persona import generate_persona_system_prompt

# Structured data services for chart generation
from services.structured_file_listing import (
    list_structured_files,
    format_schema_preview_for_prompt,
)
from services.structured_sandbox import run_structured_sandbox
from services.structured_prompt_builder import StructuredPromptBuilder
from services.compute_fact_tool import (
    build_compute_fact_tool_schema,
    make_compute_fact_dispatcher,
    COMPUTE_FACT_ROUTING_RULE,
)
from services.unstructured_file_listing import prefetch_unstructured_metadata_for_outline

router = APIRouter()

logger = logging.getLogger(__name__)

# Import UnifiedQueryEngine for fast vault retrieval
_query_engine = None

from config.milvus_config import get_milvus_client

def get_query_engine():
    """Lazy initialization of UnifiedQueryEngine for fast Milvus retrieval."""
    global _query_engine
    if _query_engine is None:
        try:
            from llamaindex_query_engine import UnifiedQueryEngine
            _query_engine = UnifiedQueryEngine()
            logger.info("🎨 [COMPOSER] UnifiedQueryEngine initialized successfully")
        except Exception as e:
            logger.error(f"🎨 [COMPOSER] Failed to initialize UnifiedQueryEngine: {e}")
            _query_engine = None
    return _query_engine


# ==================== STRUCTURED DATA RETRIEVAL ====================
# Structured files (Excel/CSV/JSON) are NOT embedded. Schema-only metadata
# lives in Mongo `structured_file_metadata`; the LLM reads the raw bytes via
# the `execute_code` sandbox.
# See: services/structured_file_listing.py, services/structured_sandbox.py


def saas_enabled(
    use_personal_data: bool,
    folder_ids,
    include_supplementary: bool = True
) -> bool:
    """
    Returns True when SaaS data should be searched.
    SaaS data (file uploads embedded in Milvus 'saas' collection) is searched
    whenever folder_ids are provided — this ensures presentations, printable
    pages, and report sections all get SaaS context from the selected folder.
    """
    return bool(folder_ids)



async def retrieve_vault_context(
    user_id: str,
    query: str,
    folder_ids: list = None,
    top_k: int = 2,
    milvus_fetch_k: int = None,
    use_saas: bool = True,
    skip_saas: bool = False
):
    """
    Fast vector retrieval from user vault + folder-synced cloud files + SaaS data from Milvus.
    
    This bypasses the heavy persona.py processing and directly queries Milvus
    for relevant document chunks, then fetches text from MongoDB.
    
    File-upload SaaS records (Excel/JSON/CSV >50 rows) are searched from the Milvus
    'saas' collection.

    Folder-synced cloud files: if any of the provided folder_ids have a folder sync
    Args:
        user_id: User identifier for vault access
        query: Search query for semantic matching
        folder_ids: Optional list of folder IDs (vault IDs) to filter by
        top_k: Number of top results to return per source
        use_saas: Whether to also search SaaS data in Milvus (default False; use saas_enabled() to compute)
        skip_saas: If True, skip the SaaS path entirely (used when structured data is pre-fetched at outline level)
    
    Returns:
        str: Concatenated context from vault documents, cloud-synced files, and SaaS data
    """
    import asyncio

    if not user_id:
        logger.warning("⚠️ [COMPOSER] retrieve_vault_context called without user_id — data retrieval will fail")
    if not folder_ids:
        logger.warning("⚠️ [COMPOSER] retrieve_vault_context called without folder_ids — SaaS and folder-scoped retrieval will be skipped")

    engine = get_query_engine()
    
    async def fetch_vault():
        """Fetch from personal vault in Milvus"""
        if not engine:
            logger.warning("🎨 [COMPOSER] UnifiedQueryEngine not available")
            return ""
        try:
            logger.info(f"🎨 [COMPOSER] Retrieving vault context for user: {user_id}, query: {query[:50]}...")
            contexts = await engine.retrieve_personal_context(
                query=query,
                user_id=user_id,
                selected_folder_ids=folder_ids,
                folder_search_enabled=bool(folder_ids),
                top_k=top_k,
                milvus_fetch_k=milvus_fetch_k
            )
            if contexts:
                result = format_flattened_context(contexts)
                logger.info(f"🎨 [COMPOSER] Vault context: {len(result)} chars")
                return result
            logger.info("🎨 [COMPOSER] No vault context found")
            return ""
        except Exception as e:
            logger.error(f"🎨 [COMPOSER] Error retrieving vault context: {e}")
            return ""
    
    async def fetch_saas():
        """Fetch from pre-embedded SaaS data in Milvus 'saas' collection"""
        if not use_saas or skip_saas:
            return ""
        
        try:
            from agentic_rag.source_provider import SourceProvider, SourceConfig
            source_provider = SourceProvider()
            
            # File-listing metadata pre-fetch via SaaSDataTool (Mongo).
            # Personal vault chunks are agentic now.
            saas_config = SourceConfig(
                use_saas=True,
                # Pass folder_ids so file-upload records (connection_id==folder_id)
                # are correctly scoped to the requested vaults.
                selected_folder_ids=folder_ids or [],
                additional_kwargs={'max_results': 20}
            )
            
            results = await source_provider.retrieve_from_sources(
                query=query,
                user_id=user_id,
                source_config=saas_config,
                context_label="composer_saas"
            )
            
            saas_contexts = results.get('saas', [])
            if saas_contexts:
                # Format SaaS contexts
                formatted_parts = []
                for ctx in saas_contexts:
                    metadata = ctx.get('metadata', {})
                    provider = metadata.get('provider', ctx.get('provider', 'Unknown'))
                    record_type = metadata.get('object_type', ctx.get('record_type', 'Record'))
                    text = ctx.get('text', ctx.get('content', ''))
                    if text:
                        formatted_parts.append(f"[{provider.upper()} - {record_type}]\n{text}")
                
                if formatted_parts:
                    saas_text = "\n\n".join(formatted_parts)
                    logger.info(f"🎨 [COMPOSER] SaaS context: {len(saas_text)} chars from {len(saas_contexts)} records")
                    return saas_text
            
            logger.info("🎨 [COMPOSER] No SaaS context found")
            return ""
            
        except Exception as e:
            logger.warning(f"🎨 [COMPOSER] SaaS fetch failed: {e}")
            return ""
    
    # === EXECUTE IN PARALLEL ===
    vault_context, saas_context = await asyncio.gather(
        fetch_vault(), fetch_saas()
    )

    # === COMBINE RESULTS ===
    parts = []
    if vault_context:
        parts.append(f"[VAULT DOCUMENTS]\n{vault_context}")
    if saas_context:
        parts.append(f"[SAAS DATA]\n{saas_context}")

    if not parts:
        return ""
    if len(parts) == 1:
        # Single source — return without section label to preserve backward compat
        return list(parts)[0].split("\n", 1)[1] if "\n" in parts[0] else parts[0]
    return "\n\n---\n\n".join(parts)


def format_flattened_context(contexts: list) -> str:
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
    
    logger.info(f"🎨 [COMPOSER] Flattened {chunk_count} chunks from {len(grouped_content)} documents")
    
    return "\n\n---\n\n".join(formatted_parts)


async def prefetch_structured_data_context(
    user_id: str,
    goal: str,
    folder_ids: list = None,
    *,
    role: str = "outline",
) -> Optional[str]:
    """
    Prefetch a goal-aware structured-data context block once and let every
    downstream consumer (outline, per-slide, per-page, per-section) reuse
    it via the cache in :mod:`services.structured_data_overview`.

    The LLM-authored overview script picks only the files relevant to the
    goal (mirrors the ``quick_chat`` pattern) and computes a rich set of
    aggregates the downstream LLM can cite directly. If that path fails
    we fall back to the legacy schema-only preview so we never regress.

    Returns ``None`` if the user has no structured files in scope.
    """
    if not folder_ids:
        return None

    # Goal-aware overview (LLM picks files + computes real aggregates).
    try:
        from services.structured_data_overview import (
            get_data_overview, format_overview_for_prompt,
        )
        overview = await get_data_overview(
            user_id=user_id, folder_ids=folder_ids, goal=goal or "",
            log_prefix="PREFETCH",
        )
        if overview:
            block = format_overview_for_prompt(overview, role=role)
            logger.info(
                "📊 [PREFETCH] Overview ready: %d chars, %d files used (cache_hit=%s)",
                len(block), len(overview.get("source_files") or []),
                overview.get("cache_hit", False),
            )
            return block
    except Exception as e:
        logger.warning("📊 [PREFETCH] Overview compute failed (will fall back): %s", e)

    # Fallback: legacy schema-only preview.
    try:
        listing = await list_structured_files(user_id, folder_ids=folder_ids)
        entries = listing.get("entries", [])
        if not entries:
            logger.info("📊 [PREFETCH] User has no structured data — skipping prefetch")
            return None

        schema_text = format_schema_preview_for_prompt(
            entries, truncated_files=listing.get("truncated_files"),
        )

        parts = [
            "=== PRE-FETCHED STRUCTURED DATA (schema only — fallback) ===",
            schema_text,
            "",
            "NOTE: only column samples above are reliable. To compute chart values, "
            "hit the composer/generate-chart endpoint (sandboxed Python).",
        ]
        context = "\n".join(parts)
        logger.info(
            "📊 [PREFETCH] Schema-only fallback ready: %d chars, %d files",
            len(context), len(entries),
        )
        return context

    except Exception as e:
        logger.warning("📊 [PREFETCH] Structured data prefetch failed: %s", e)
        return None


def validate_composer_payload(payload: Dict[str, Any]) -> tuple:
    """
    Validate and extract fields from composer request payload.
    
    Returns:
        tuple: (user_id, query, ai_model, context_type, current_content, report_metadata, user_flags)
    """
    # Required fields
    user_id = payload.get('user_id')
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    
    query = payload.get('query')
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    
    # Optional fields with defaults
    ai_model = payload.get('ai_model', 'citra-ai-lite')  # Default to Citra AI Lite for composer
    context_type = payload.get('context_type', 'expand')  # expand, review, suggest
    current_content = payload.get('current_content', '')
    report_metadata = payload.get('report_metadata', {})
    
    # User preference flags for data sources and model selection
    user_flags = {
        'use_personal_data': payload.get('use_personal_data', False),
        'include_supplementary': payload.get('include_supplementary', False),
        # use_internet and use_india_kanoon removed - legacy flags no longer used
        'persona_data': payload.get('persona_data', None)
    }
    
    return user_id, query, ai_model, context_type, current_content, report_metadata, user_flags

def build_composer_system_prompt(context_type: str) -> str:
    """Build system prompt for composer interactions."""
    base = "Professional report writing assistant. Clear, well-structured responses."
    
    if context_type == 'expand':
        return f"{base}\nExpand content per user request. HTML only: <p>,<strong>,<em>,<h3>,<h4>,<ul>,<ol>,<li>,<blockquote>,<table>. NO markdown. Use tables for comparisons/data/stats."
    elif context_type == 'review':
        return f"{base}\nReview content: grammar, style, clarity, structure. Specific suggestions + strengths."
    elif context_type == 'suggest':
        return f"{base}\nSuggest improvements: content gaps, structure, topics, narrative strength, next steps."
    else:
        return f"{base}\nAssist with writing and content creation."

def build_composer_prompt(
    query: str, 
    context_type: str, 
    current_content: str, 
    report_metadata: Dict[str, Any],
    vault_context: str = ""
) -> str:
    """Build prompt for composer AI assistance."""
    goal = report_metadata.get('overall_goal', 'General report')
    title = report_metadata.get('title', 'Untitled Report')
    page = report_metadata.get('current_page_title', 'Current Page')
    page_info = report_metadata.get('page_info', '')
    
    prompt = f"REPORT: {title} | Goal: {goal} | Page: {page}"
    if page_info:
        prompt += f" ({page_info})"
    
    content = current_content.strip() if current_content else "[Empty]"
    prompt += f"\n\nCONTENT:\n{content}"
    
    if vault_context:
        prompt += f"\n\nREFERENCE DOCS:\n{vault_context}"
    
    prompt += f"\n\nREQUEST: {query}"
    return prompt

@router.post("/composer/query")
async def composer_query(request: Request, payload: Dict[str, Any]):
    """
    POST /composer/query - Dedicated endpoint for Report Composer AI assistance
    
    Expected payload:
    {
        "user_id": "user_user_id",
        "query": "user's request or question",
        "ai_model": "citra-ai-lite",  // optional, defaults to citra-ai-lite
        "context_type": "expand",  // expand, review, suggest
        "current_content": "current page content",
        "report_metadata": {
            "overall_goal": "report goal",
            "title": "report title",
            "current_page_title": "current page title",
            "page_info": "page 1 of 3",
            // other metadata...
        },
        "use_personal_data": false,  // Enable personal data search
        "persona_data": {}           // User persona information
    }
    
    Returns:
    {
        "response": "AI generated response",
        "context_type": "expand",
        "processing_time": 1.234
    }
    """
    start_time = time.time()
    
    try:
        logger.info("🎨 [COMPOSER] Processing composer query request")
        logger.info(f"🎨 [COMPOSER] Payload keys: {list(payload.keys())}")
        
        # SECURITY: Inject authenticated user_id from JWT (prevents spoofing)
        payload["user_id"] = get_secure_user_id(request)
        user_email = get_user_email(request)
        
        # Validate and extract payload
        user_id, query, ai_model, context_type, current_content, report_metadata, user_flags = validate_composer_payload(payload)
        
        logger.info(f"🎨 [COMPOSER] Request details:")
        logger.info(f"   └─ Device ID: {user_id}")
        logger.info(f"   └─ Context Type: {context_type}")
        logger.info(f"   └─ AI Model: {ai_model}")
        logger.info(f"   └─ Query Length: {len(query)} chars")
        logger.info(f"   └─ Current Content Length: {len(current_content)} chars")
        logger.info(f"   └─ Report Goal: {report_metadata.get('overall_goal', 'Not specified')}")
        logger.info(f"🎨 [COMPOSER] User Flags:")
        logger.info(f"   └─ Personal Data: {user_flags['use_personal_data']}")
        
        # Check if any data source flags are enabled
        any_data_sources_enabled = user_flags['use_personal_data']
        
        if any_data_sources_enabled:
            logger.info("🎨 [COMPOSER] Data sources enabled - using FAST vault retrieval")
            
            # Extract folder_ids from payload if provided
            folder_ids = payload.get('folder_ids', None)
            
            # Build query combining user query + page context for semantic matching
            # Note: We exclude overall_goal to keep search focused on current page
            vault_query_parts = [query]  # User's question/request is primary
            
            # Add page title if available (helps semantic search understand context)
            if report_metadata and report_metadata.get('current_page_title'):
                vault_query_parts.append(report_metadata.get('current_page_title'))
            
            # Add content snippet (semantic search benefit)
            if current_content:
                vault_query_parts.append(current_content[:250])
            
            vault_query = " ".join(vault_query_parts)
            logger.info(f"🎨 [COMPOSER] Vault query: {vault_query[:100]}...")
            
            # FAST PATH: Use UnifiedQueryEngine for direct Milvus retrieval
            # This bypasses heavy persona.py processing
            # use_saas=False: structured-file context is fetched separately below
            # to avoid duplicate listings (SaaSDataTool and direct retriever)
            logger.info(f"🎨 [COMPOSER] Vault fetch: personal docs only (no SaaS) "
                        f"(personal={user_flags['use_personal_data']}, "
                        f"folders={bool(folder_ids)})")

            # Vault chunks are now fetched agentically by the LLM via
            # personal_data_tool inside run_Enterprise_or_Personal_tool below.
            # Only structured-file schema metadata is still pre-fetched.
            async def _fetch_structured_data():
                try:
                    listing = await list_structured_files(user_id, folder_ids=folder_ids)
                    entries = listing.get("entries", [])
                    if not entries:
                        return ""
                    schema_text = format_schema_preview_for_prompt(
                        entries, truncated_files=listing.get("truncated_files"),
                    )
                    logger.info(
                        f"🎨 [COMPOSER] Schema preview added for {len(entries)} structured file(s)"
                    )
                    return (
                        "\n\nSTRUCTURED DATA AVAILABLE (schema + samples only):\n"
                        f"{schema_text}\n"
                        "CRITICAL: The samples above are 3 values per column — they are NOT enough to compute totals, top-N, distributions, averages, or any aggregate. "
                        "If the user asks for a chart or stat that depends on the file (e.g. 'total colleges', 'P&L by quarter', 'top 5 customers'), "
                        "DO NOT author numeric values from those samples — they will be wrong. "
                        "Either (a) tell the user the value will be computed and emit a placeholder like <chart-placeholder data-description=\"...\" data-metric=\"sum|count|avg|top_n|distribution|trend\" data-dimension=\"<column>\" data-source-hint=\"<filename>\"/> (the frontend will replace it via composer/generate-chart against the full file), "
                        "or (b) describe the answer narratively without inventing numbers. "
                        "Never embed fabricated numbers in <chart-config> or prose."
                    )
                except Exception as e:
                    logger.warning(f"🎨 [COMPOSER] Structured data retrieval failed: {e}")
                return ""

            structured_data_context = await _fetch_structured_data()

            # Build prompt — vault context is now fetched agentically by the
            # LLM via personal_data_tool, so it is NOT pre-injected here.
            system_prompt = build_composer_system_prompt(context_type)
            full_prompt = build_composer_prompt(
                query, context_type, current_content, report_metadata,
                vault_context=""
            )

            # Append structured data context if available (schema-only hint)
            if structured_data_context:
                full_prompt += structured_data_context

            # Use the agentic tool-loop helper whenever personal-vault is
            # enabled. The LLM picks `personal_data_tool` on demand. When
            # disabled, fall back to the direct LLM call (no data tools).
            use_personal_for_loop = bool(user_flags.get('use_personal_data')) and bool(folder_ids)
            if use_personal_for_loop:
                logger.info(
                    f"🎨 [COMPOSER] Agentic tool-loop (personal={use_personal_for_loop})"
                )
                # Prefetch unstructured-file metadata so the composer LLM
                # knows which vault docs match before calling personal_data_tool.
                # The bool result also gates whether personal_data_tool is even
                # exposed downstream (mirrors streaming_response.py).
                _meta = None
                try:
                    _meta = await prefetch_unstructured_metadata_for_outline(
                        user_id=user_id, folder_ids=folder_ids, query=query,
                    )
                    if _meta:
                        full_prompt += f"\n\n{_meta}"
                        logger.info(f"📄 [COMPOSER] Prefetched unstructured metadata ({len(_meta)} chars)")
                except Exception as e:
                    logger.warning(f"📄 [COMPOSER] Unstructured metadata prefetch failed (non-blocking): {e}")

                from services.enterprise_tools import run_Enterprise_or_Personal_tool
                response = await run_Enterprise_or_Personal_tool(
                    prompt=full_prompt,
                    system=system_prompt + "\n\n" + COMPUTE_FACT_ROUTING_RULE,
                    user_id=user_id,
                    user_email=user_email,
                    tier="large",
                    temperature=0.2,
                    max_tokens=16000,
                    filter_tools="auto",
                    use_personal_data=use_personal_for_loop,
                    selected_folder_ids=folder_ids,
                    persona_data=payload.get('persona_data'),
                    max_results_cap=5,  # Composer: max 5 chunks per data-tool call
                    expose_enterprise_tools=False,
                    has_unstructured_files=bool(_meta),
                    personal_tool_expand_subqueries=False,
                    extra_tools=[build_compute_fact_tool_schema()],
                    extra_tool_dispatch=make_compute_fact_dispatcher(
                        user_id=user_id, folder_ids=folder_ids,
                        log_prefix="COMPOSER-QUERY-FACT",
                    ),
                )
            else:
                logger.info("🎨 [COMPOSER] No data sources — direct LLM call")
                from llm_oss import llm_call
                response = llm_call(
                    system_prompt=system_prompt,
                    user_prompt=full_prompt,
                    model=None,
                    user_id=user_id,
                    user_email=user_email,
                    temperature=0.2,
                    top_p=0.95,
                    tier="large",
                )
        
        else:
            logger.info("🎨 [COMPOSER] No data sources enabled - using direct model call")
            
            # Use llm_oss for direct calls
            logger.info("🎨 [COMPOSER] Using llm_oss model")
            
            # Build system prompt for the specific context type
            system_prompt = build_composer_system_prompt(context_type)
            
            # Build the complete prompt with context
            full_prompt = build_composer_prompt(query, context_type, current_content, report_metadata)
            
            logger.info(f"🎨 [COMPOSER] Generated prompt length: {len(full_prompt)} chars")
            
            # Generate AI response
            logger.info("🎨 [COMPOSER] Calling AI model...")
            from llm_oss import llm_call
            response = llm_call(
                system_prompt=system_prompt,
                user_prompt=full_prompt,
                model=None,
                user_id=user_id,
                user_email=user_email,
                temperature=0.2,
                top_p=0.95,
                tier="large",
            )
        
        processing_time = time.time() - start_time
        logger.info(f"🎨 [COMPOSER] Generated response in {processing_time:.3f}s")
        logger.info(f"🎨 [COMPOSER] Response length: {len(response)} chars")
        
        # Prepare response
        response_data = {
            "response": response,
            "context_type": context_type,
            "processing_time": round(processing_time, 3)
        }
        
        return JSONResponse(content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"🎨 [COMPOSER] Error processing request: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Internal server error in composer query: {str(e)}"
        )

@router.get("/composer/health")
async def composer_health():
    """Health check endpoint for composer service"""
    return JSONResponse(content={
        "status": "healthy",
        "service": "composer_query",
        "timestamp": time.time()
    })


# ==================== STRUCTURED DATA CHART GENERATION ====================

# StructuredPromptBuilder is still used (it formats the LLM prompt for chart/table tasks).
_prompt_builder = None


def get_prompt_builder():
    """Lazy initialization of StructuredPromptBuilder."""
    global _prompt_builder
    if _prompt_builder is None:
        _prompt_builder = StructuredPromptBuilder()
        logger.info("🎨 [COMPOSER] StructuredPromptBuilder initialized successfully")
    return _prompt_builder


async def _run_structured_sandbox(
    user_id: str,
    folder_ids: Optional[list],
    instruction_prompt: str,
    *,
    log_prefix: str = "COMPOSER",
) -> Dict[str, Any]:
    """Thin wrapper around :func:`services.structured_sandbox.run_structured_sandbox`."""
    return await run_structured_sandbox(
        user_id=user_id,
        folder_ids=folder_ids,
        instruction_prompt=instruction_prompt,
        log_prefix=log_prefix,
    )


@router.post("/composer/generate-chart")
async def generate_report_chart(request: Request, payload: Dict[str, Any]):
    """
    POST /composer/generate-chart - Generate a Chart.js config from the user's
    structured vault files via the sandbox `execute_code` path.

    The LLM writes a small Python script that loads the relevant file from
    /workspace/input/, computes the requested aggregation, and prints a
    Chart.js JSON config to stdout. The endpoint then validates and returns
    that config to the caller. No data rows are dumped into the LLM prompt —
    only the schema preview from ``structured_file_metadata``.

    Expected payload::

        {
            "user_id": "...",
            "query": "Create a bar chart showing sales by region",
            "folder_ids": [...],         # optional
            "chart_type": "bar",          # optional hint
            "report_context": {...}       # optional
        }
    """
    start_time = time.time()

    try:
        user_id = get_secure_user_id(request)
        query = payload.get("query")
        if not query:
            raise HTTPException(status_code=400, detail="query is required")

        folder_ids = payload.get("folder_ids")
        chart_type_hint = payload.get("chart_type")
        report_context = payload.get("report_context", {}) or {}

        logger.info(f"📊 [COMPOSER-CHART] user={user_id} query='{query[:80]}…' type={chart_type_hint} folders={folder_ids}")

        # Build a single instruction prompt for the sandbox helper.
        ctx_lines = []
        if report_context.get("title"):
            ctx_lines.append(f"Report: {report_context['title']}")
        if report_context.get("page_title"):
            ctx_lines.append(f"Page: {report_context['page_title']}")
        if report_context.get("overall_goal"):
            ctx_lines.append(f"Overall goal: {report_context['overall_goal']}")
        ctx_block = "\n".join(ctx_lines)

        chart_type_line = (
            f"Preferred chart type: {chart_type_hint} (allowed: bar, line, pie, doughnut, radar, polarArea, scatter, bubble)"
            if chart_type_hint else
            "Pick the most appropriate chart type from: bar, line, pie, doughnut, radar, polarArea, scatter, bubble."
        )

        instruction = (
            f"User request: {query}\n"
            f"{ctx_block}\n\n"
            f"{chart_type_line}\n\n"
            "Write a Python script that:\n"
            "1. Loads the relevant file from /workspace/input/ (use pandas for csv/xlsx, json module for json).\n"
            "2. Computes the labels and dataset values needed for the chart.\n"
            "3. Builds a Chart.js config dict with this exact shape:\n"
            "   {\"type\": \"<chart_type>\", \"data\": {\"labels\": [...], \"datasets\": [{\"label\": \"...\", \"data\": [...], \"backgroundColor\": [...]}]}}\n"
            "4. Prints the config as JSON to stdout using `print(json.dumps(config))`. Print NOTHING ELSE.\n"
            "Use up to 12 labels max — aggregate / take top-N as appropriate. Use realistic backgroundColor hex values."
        )

        result = await _run_structured_sandbox(
            user_id=user_id, folder_ids=folder_ids,
            instruction_prompt=instruction, log_prefix="COMPOSER-CHART",
        )

        if result.get("error") == "no_structured_data":
            return JSONResponse(content={
                "success": False, "error": "no_structured_data",
                "message": "No structured data (Excel/CSV/JSON) found in the selected folders. Please upload relevant files first.",
                "processing_time": round(time.time() - start_time, 3),
            })
        if result.get("error") == "no_script":
            return JSONResponse(content={
                "success": False, "error": "invalid_chart_config",
                "message": "Could not derive a Python computation from the request.",
                "raw_response": (result.get("raw_response") or "")[:500],
                "processing_time": round(time.time() - start_time, 3),
            })
        if not result.get("success"):
            logger.error(f"📊 [COMPOSER-CHART] sandbox failed stderr={result.get('stderr')[:300]}")
            return JSONResponse(content={
                "success": False, "error": "exec_failed",
                "message": "Failed to compute chart data from the file.",
                "stderr": result.get("stderr", "")[:500],
                "processing_time": round(time.time() - start_time, 3),
            })

        # Parse stdout as JSON.
        stdout = (result.get("stdout") or "").strip()
        chart_config = None
        try:
            chart_config = json.loads(stdout)
        except Exception:
            # Fallback: extract the first {...} block.
            start_idx = stdout.find("{")
            end_idx = stdout.rfind("}")
            if start_idx != -1 and end_idx > start_idx:
                try:
                    chart_config = json.loads(stdout[start_idx:end_idx + 1])
                except Exception:
                    chart_config = None
        if not isinstance(chart_config, dict):
            return JSONResponse(content={
                "success": False, "error": "invalid_chart_config",
                "message": "Sandbox output was not valid JSON.",
                "stdout_preview": stdout[:500],
                "processing_time": round(time.time() - start_time, 3),
            })

        # Deterministic normalization.
        _VALID_CHART_TYPES = {"bar", "line", "pie", "doughnut", "radar", "polarArea", "scatter", "bubble"}
        ctype = chart_config.get("type", "bar")
        if ctype not in _VALID_CHART_TYPES:
            stripped = ctype.replace("chart-", "").replace("chart_", "")
            chart_config["type"] = stripped if stripped in _VALID_CHART_TYPES else "bar"
        if "data" not in chart_config and ("labels" in chart_config or "datasets" in chart_config):
            chart_config["data"] = {
                "labels": chart_config.pop("labels", []),
                "datasets": chart_config.pop("datasets", []),
            }

        prompt_builder = get_prompt_builder()
        if not prompt_builder.validate_chart_config(chart_config):
            logger.warning("📊 [COMPOSER-CHART] Chart config invalid after sandbox, returning best-effort")

        entries = result.get("entries") or []
        source_doc = entries[0].filename if entries else None
        processing_time = time.time() - start_time
        logger.info(f"📊 [COMPOSER-CHART] Chart generated in {processing_time:.3f}s from '{source_doc}'")

        return JSONResponse(content={
            "success": True,
            "chart_config": chart_config,
            "source_document": source_doc,
            "data_preview": {},
            "schema_fields": [c.get("name") for c in (entries[0].columns if entries else [])][:10],
            "processing_time": round(processing_time, 3),
        })

    except HTTPException:
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"📊 [COMPOSER-CHART] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate chart: {e}")


@router.post("/composer/generate-table")
async def generate_report_table(request: Request, payload: Dict[str, Any]):
    """
    POST /composer/generate-table - Generate an HTML table from the user's
    structured vault files via the sandbox `execute_code` path.

    Same architecture as `/composer/generate-chart`: the LLM writes a Python
    script that loads the file, computes the requested rows, and prints a
    markdown table to stdout. The endpoint then converts that markdown to
    HTML and returns it.
    """
    start_time = time.time()

    try:
        user_id = get_secure_user_id(request)
        query = payload.get("query")
        if not query:
            raise HTTPException(status_code=400, detail="query is required")

        folder_ids = payload.get("folder_ids")
        max_rows = int(payload.get("max_rows", 15) or 15)
        report_context = payload.get("report_context", {}) or {}

        logger.info(f"📋 [COMPOSER-TABLE] user={user_id} query='{query[:80]}…' max_rows={max_rows}")

        ctx_lines = []
        if report_context.get("title"):
            ctx_lines.append(f"Report: {report_context['title']}")
        if report_context.get("page_title"):
            ctx_lines.append(f"Page: {report_context['page_title']}")
        ctx_block = "\n".join(ctx_lines)

        instruction = (
            f"User request: {query}\n"
            f"{ctx_block}\n\n"
            "Write a Python script that:\n"
            "1. Loads the relevant file from /workspace/input/ (use pandas for csv/xlsx, json module for json).\n"
            f"2. Computes / filters / sorts to produce at most {max_rows} rows.\n"
            "3. Prints exactly ONE markdown table to stdout (header row, separator row of `---`, then data rows).\n"
            "Do NOT print explanations, code fences, or anything other than the markdown table."
        )

        result = await _run_structured_sandbox(
            user_id=user_id, folder_ids=folder_ids,
            instruction_prompt=instruction, log_prefix="COMPOSER-TABLE",
        )

        if result.get("error") == "no_structured_data":
            return JSONResponse(content={
                "success": False, "error": "no_structured_data",
                "message": "No structured data (Excel/CSV/JSON) found in the selected folders.",
                "processing_time": round(time.time() - start_time, 3),
            })
        if result.get("error") == "no_script":
            return JSONResponse(content={
                "success": False, "error": "invalid_table_response",
                "message": "Could not derive a Python computation from the request.",
                "raw_response": (result.get("raw_response") or "")[:500],
                "processing_time": round(time.time() - start_time, 3),
            })
        if not result.get("success"):
            logger.error(f"📋 [COMPOSER-TABLE] sandbox failed stderr={result.get('stderr')[:300]}")
            return JSONResponse(content={
                "success": False, "error": "exec_failed",
                "message": "Failed to compute table data from the file.",
                "stderr": result.get("stderr", "")[:500],
                "processing_time": round(time.time() - start_time, 3),
            })

        markdown_output = (result.get("stdout") or "").strip()
        table_html = convert_markdown_table_to_html(markdown_output)
        row_count = max(0, table_html.count("<tr>") - 1)

        entries = result.get("entries") or []
        source_doc = entries[0].filename if entries else None
        processing_time = time.time() - start_time
        logger.info(f"📋 [COMPOSER-TABLE] Table generated in {processing_time:.3f}s ({row_count} rows from '{source_doc}')")

        return JSONResponse(content={
            "success": True,
            "table_html": table_html,
            "source_document": source_doc,
            "row_count": row_count,
            "processing_time": round(processing_time, 3),
        })
        
    except HTTPException:
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"📋 [COMPOSER-TABLE] Error generating table: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate table: {str(e)}"
        )


def convert_markdown_table_to_html(markdown_text: str) -> str:
    """
    Convert markdown table in AI response to HTML table.
    
    Args:
        markdown_text: AI response containing markdown table
        
    Returns:
        HTML table string with styling classes
    """
    import re
    
    # Find markdown table in response
    lines = markdown_text.strip().split('\n')
    table_lines = []
    in_table = False
    
    for line in lines:
        line = line.strip()
        if '|' in line:
            in_table = True
            table_lines.append(line)
        elif in_table and not line:
            break  # End of table
    
    if not table_lines:
        # No table found, wrap response in simple div
        return f'<div class="ai-response">{markdown_text}</div>'
    
    # Parse markdown table
    html_rows = []
    header_processed = False
    
    for line in table_lines:
        # Skip separator line (|---|---|)
        if re.match(r'^[\|\s\-:]+$', line):
            continue
        
        # Split by | and clean cells
        cells = [cell.strip() for cell in line.split('|')]
        cells = [c for c in cells if c]  # Remove empty cells
        
        if not header_processed:
            # First row is header
            header_cells = ''.join(f'<th>{cell}</th>' for cell in cells)
            html_rows.append(f'<thead><tr>{header_cells}</tr></thead>')
            html_rows.append('<tbody>')
            header_processed = True
        else:
            # Data rows
            data_cells = ''.join(f'<td>{cell}</td>' for cell in cells)
            html_rows.append(f'<tr>{data_cells}</tr>')
    
    html_rows.append('</tbody>')
    
    # Build complete table with styling
    table_html = f'''<table class="structured-data-table" style="width: 100%; border-collapse: collapse; margin: 1rem 0;">
        {''.join(html_rows)}
    </table>'''
    
    return table_html


# ==================== AI IMAGE DESCRIPTION GENERATION ====================

@router.post("/composer/generate-image-description")
async def generate_image_description(request: Request, payload: Dict[str, Any]):
    """
    POST /composer/generate-image-description - Generate an optimized image generation prompt
    
    Common endpoint used by Report Composer, Presentation, and Printable UIs.
    Takes a user's image idea + page context, optionally enriches with vault data,
    then uses llm to produce an optimized image generation prompt and classify the image type.
    
    Expected payload:
    {
        "user_query": "Create a better image of Hotel",
        "page_title": "The Grand Horizon - Title Page",
        "page_snippet": "First 300 chars of page content...",
        "folder_ids": ["folder1", "folder2"],  // optional - vault folders for context
        "user_id": "user_device_id"
    }
    
    Returns:
    {
        "success": true,
        "image_description": "A luxurious modern hotel with glass facade...",
        "image_type": "photo"  // photo | infographic | photo_with_text
    }
    """
    start_time = time.time()
    
    try:
        # --- Validate required fields ---
        user_id = get_secure_user_id(request)
        
        user_query = payload.get('user_query', '').strip()
        if not user_query:
            raise HTTPException(status_code=400, detail="user_query is required")
        
        page_title = payload.get('page_title', '')
        page_snippet = payload.get('page_snippet', '')
        folder_ids = payload.get('folder_ids', [])
        
        logger.info(f"🖼️ [IMAGE_DESC] Request from user: {user_id}")
        logger.info(f"🖼️ [IMAGE_DESC] Query: {user_query[:100]}")
        logger.info(f"🖼️ [IMAGE_DESC] Page: {page_title}")
        
        # Vault chunks now fetched agentically by the LLM via personal_data_tool
        # inside run_Enterprise_or_Personal_tool below (cap=3, image-prompt is small).
        vault_context = ""
        _img_use_personal = bool(folder_ids) and len(folder_ids) > 0
        
        # --- Build system prompt for image description generation ---
        system_prompt = """You are an expert image prompt engineer. Your job is to take a user's image idea and convert it into a detailed, optimized prompt for an AI image generation model.

RULES:
1. Generate a vivid, detailed visual description (2-4 sentences) that an image generation AI can use directly.
2. Include specific details: colors, lighting, composition, mood, perspective, style.
3. If the user mentions something vague, make it concrete and visually compelling.
4. Use the page context to make the image relevant to the content.
5. LOCALE & CULTURAL AUTHENTICITY (CRITICAL): Infer the country, state, region, or city from the user request, page title, page snippet, and reference documents, then bake those cues into the description.
   - People & faces: When humans appear, specify ethnicity, skin tone, attire, and grooming consistent with the inferred locale (e.g., India → "Indian people"; Bihar → "Bihari adults in kurta-pajama / saree"; Tamil Nadu → "South Indian people in traditional Tamil attire"; Japan → "Japanese professionals"). NEVER default to generic Western/Caucasian faces unless the locale is explicitly Western. If no locale is implied, prefer a globally diverse cast.
   - Cities, buildings, streets: Use locally accurate architecture, vehicles, signage style (without rendering text), vegetation, and street life (e.g., Patna → Ganga ghats, low-rise plastered buildings, autorickshaws; Mumbai → Art Deco / Indo-Saracenic facades, BEST buses; rural Bihar → mud-and-thatch homes, paddy fields, neem trees).
   - Landscape, food, clothing, festivals, religious imagery: Reflect the inferred region authentically (e.g., Indian temples not generic cathedrals); use locally appropriate flora, fauna, weather, and lighting.
   - Preserve the no-text rule for "photo" type — describe culturally authentic visuals WITHOUT asking for any signage, captions, or written script in the image.
6. Classify the image into one of three types:
   - "photo": Realistic photograph, nature, people, objects, scenes
   - "infographic": Data visualization, charts, diagrams, process flows, comparisons with text labels
   - "photo_with_text": Image that requires embedded text, titles, quotes, branded content

RESPOND WITH VALID JSON ONLY (no markdown, no code fences):
{"image_description": "your detailed image prompt here", "image_type": "photo"}"""

        # --- Build user prompt with context ---
        user_prompt_parts = [f"USER REQUEST: {user_query}"]

        if page_title:
            user_prompt_parts.append(f"PAGE TITLE: {page_title}")

        if page_snippet:
            user_prompt_parts.append(f"PAGE CONTENT PREVIEW: {page_snippet[:300]}")

        if _img_use_personal:
            user_prompt_parts.append(
                f"DATA TOOL: `personal_data_tool` is available "
                f"(scoped to {len(folder_ids)} folder(s)). Call it ONCE with a focused "
                f"query for the locale/cultural cues you need (e.g. 'Bihar architecture', "
                f"'Tamil temple imagery') if the page topic suggests a specific region. "
                f"Otherwise skip the tool — image-prompt generation rarely needs vault chunks."
            )

        user_prompt = "\n\n".join(user_prompt_parts)

        # --- Call LLM (agentic when folders present, direct otherwise) ---
        if _img_use_personal:
            logger.info("🖼️ [IMAGE_DESC] Calling agentic tool-loop for image description...")
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
                max_results_cap=3,  # image-description: max 3 chunks per call
                expose_enterprise_tools=False,
                personal_tool_expand_subqueries=False,
                # No compute_fact / metadata prefetch here — image-prompt
                # generation rarely needs vault numerics or file listings.
            )
        else:
            from llm_oss import llm_call
            logger.info("🖼️ [IMAGE_DESC] Calling llm_oss for image description...")
            ai_response = await asyncio.to_thread(llm_call,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=None,
                user_id=user_id,
                max_tokens=16000,
                temperature=0.2,
                top_p=0.95,
                json_mode=True,
                tier="large",
            )
        
        # --- Parse JSON response ---
        if not ai_response:
            raise ValueError("Empty response from AI")
        
        # Clean response (remove markdown fences if present)
        cleaned = ai_response.strip()
        if cleaned.startswith('```'):
            cleaned = cleaned.split('\n', 1)[1] if '\n' in cleaned else cleaned[3:]
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        result = json.loads(cleaned)
        
        image_description = result.get('image_description', '')
        image_type = result.get('image_type', 'photo')
        
        # Validate image_type
        if image_type not in ('photo', 'infographic', 'photo_with_text'):
            image_type = 'photo'
        
        if not image_description:
            raise ValueError("No image_description in AI response")
        
        processing_time = time.time() - start_time
        logger.info(f"🖼️ [IMAGE_DESC] Generated in {processing_time:.2f}s - Type: {image_type}")
        logger.info(f"🖼️ [IMAGE_DESC] Description: {image_description[:100]}...")
        
        return JSONResponse(content={
            "success": True,
            "image_description": image_description,
            "image_type": image_type,
            "processing_time": round(processing_time, 3)
        })
        
    except HTTPException as he:
        raise
    except json.JSONDecodeError as je:
        logger.error(f"🖼️ [IMAGE_DESC] Failed to parse AI response as JSON: {je}")
        # Fallback: use the raw response as the description
        return JSONResponse(content={
            "success": True,
            "image_description": ai_response.strip() if ai_response else user_query,
            "image_type": "photo",
            "processing_time": round(time.time() - start_time, 3)
        })
    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = str(e)
        logger.error(f"🖼️ [IMAGE_DESC] Error: {error_msg}", exc_info=True)
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate image description: {error_msg}"
        )


# ==================== AI SVG DIAGRAM GENERATION ====================

@router.post("/composer/generate-svg-diagram")
async def generate_svg_diagram(request: Request, payload: Dict[str, Any]):
    """
    POST /composer/generate-svg-diagram - Generate an inline SVG diagram from a user prompt.

    Used by Presentation and Printable composers as the AI-powered replacement for
    the legacy "Insert Diagram" flow. Produces flowcharts, infographics, or org charts
    as standalone <svg> markup that the UI inserts as an `svg_diagram` element.

    Expected payload:
    {
        "user_query": "Steps for AI deployment lifecycle",
        "diagram_kind": "flowchart" | "infographic" | "org_chart",
        "page_title": "AI Deployment - Slide 3",      // optional
        "page_snippet": "First chunk of page text...", // optional
        "width": 920,    // optional, default 920
        "height": 440,   // optional, default 440
        "user_id": "user_device_id"
    }

    Returns:
    {
        "success": true,
        "svg": "<svg ...>...</svg>",
        "diagram_kind": "flowchart",
        "title": "AI Deployment Lifecycle",
        "prompt_used": "...",
        "processing_time": 4.21
    }
    """
    from svg_diagram_prompts import (
        ALLOWED_KINDS,
        build_system_prompt,
        build_user_prompt,
        normalize_kind,
        sanitize_svg,
    )

    start_time = time.time()
    ai_response = None

    try:
        user_id = get_secure_user_id(request)

        user_query = (payload.get("user_query") or "").strip()
        if not user_query:
            raise HTTPException(status_code=400, detail="user_query is required")

        diagram_kind = normalize_kind(payload.get("diagram_kind"))
        page_title = (payload.get("page_title") or "").strip()
        page_snippet = (payload.get("page_snippet") or "").strip()
        palette_hint = (payload.get("palette_hint") or "").strip()
        # Optional: existing SVG markup when the user is editing an existing
        # diagram. Sent to the LLM as edit context so it revises rather than
        # generating from scratch.
        current_svg = (payload.get("current_svg") or "").strip()

        # Clamp dimensions to sane bounds.
        try:
            width = int(payload.get("width") or 920)
            height = int(payload.get("height") or 440)
        except (TypeError, ValueError):
            width, height = 920, 440
        width = max(320, min(width, 2000))
        height = max(200, min(height, 1500))

        logger.info(f"📐 [SVG_DIAGRAM] Request from user: {user_id}")
        logger.info(f"📐 [SVG_DIAGRAM] Kind: {diagram_kind} | Size: {width}x{height}")
        logger.info(f"📐 [SVG_DIAGRAM] Query: {user_query[:120]}")

        system_prompt = build_system_prompt(diagram_kind, width=width, height=height)
        user_prompt = build_user_prompt(
            user_query, page_title, page_snippet,
            palette_hint=palette_hint,
            current_svg=current_svg,
        )

        from llm_oss import llm_call

        logger.info("📐 [SVG_DIAGRAM] Calling llm_oss (tier=large, json_mode=True)...")

        ai_response = await asyncio.to_thread(
            llm_call,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=None,
            user_id=user_id,
            max_tokens=8000,
            temperature=0.2,
            top_p=0.95,
            json_mode=True,
            tier="large",
        )

        if not ai_response:
            raise ValueError("Empty response from AI")

        # --- Parse JSON response ---
        cleaned = ai_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            # Last-ditch: try to extract the svg field with a regex.
            m = re.search(r'"svg"\s*:\s*"(.+?)"\s*[,}]', cleaned, re.DOTALL)
            if not m:
                raise
            result = {"svg": m.group(1).encode("utf-8").decode("unicode_escape"), "title": ""}

        raw_svg = (result.get("svg") or "").strip()
        title = (result.get("title") or "").strip()

        if not raw_svg:
            raise ValueError("LLM response missing 'svg' field")

        ok, cleaned_svg, err = sanitize_svg(raw_svg)
        if not ok:
            logger.error(f"📐 [SVG_DIAGRAM] Sanitizer rejected SVG: {err}")
            raise ValueError(f"Generated SVG failed sanitization: {err}")

        if diagram_kind not in ALLOWED_KINDS:
            diagram_kind = "flowchart"

        processing_time = time.time() - start_time
        logger.info(
            f"📐 [SVG_DIAGRAM] Generated in {processing_time:.2f}s "
            f"({len(cleaned_svg)} bytes, kind={diagram_kind})"
        )

        return JSONResponse(
            content={
                "success": True,
                "svg": cleaned_svg,
                "diagram_kind": diagram_kind,
                "title": title,
                "prompt_used": user_query,
                "processing_time": round(processing_time, 3),
            }
        )

    except HTTPException:
        raise
    except json.JSONDecodeError as je:
        logger.error(f"📐 [SVG_DIAGRAM] Failed to parse AI response as JSON: {je}")
        raise HTTPException(
            status_code=502,
            detail="AI returned malformed JSON. Please try again.",
        )
    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = str(e)
        logger.error(f"📐 [SVG_DIAGRAM] Error: {error_msg}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate SVG diagram: {error_msg}",
        )
