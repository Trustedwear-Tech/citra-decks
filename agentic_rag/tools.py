# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
LangGraph Tools for Data Retrieval
==================================

This module contains simple tools that retrieve data without making decisions.
These replace the agent classes for data retrieval operations.
"""

import logging
from typing import List, Dict, Any, Optional
import asyncio
import sys
import os

# Add parent directory to path so we can import from parent directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from llamaindex_query_engine import UnifiedQueryEngine
from config.milvus_config import milvus_config

logger = logging.getLogger(__name__)


class SaaSDataTool:
    """Tool for surfacing structured-vault files (Excel/CSV/JSON) to the chat LLM.

    No more per-row Milvus search. We list the user's structured files and
    return one **schema-only** context per file. Each context carries the
    ``s3_key`` so ``streaming_response.py`` can mount the raw file into the
    sandbox; the LLM is expected to call the ``execute_code`` tool against
    those files for any aggregation / FIFO / P&L / chart-data computation.
    """

    def __init__(self):
        logger.info("✅ SaaSDataTool initialized (schema-only, sandbox-driven)")

    async def retrieve(
        self,
        query: str,
        user_id: str,
        max_results: int = 20,
        similarity_threshold: Optional[float] = None,
        folder_ids: Optional[List[str]] = None,
        attached_document_ids: Optional[List[str]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Return one context per relevant vault file in scope.

        Now covers BOTH structured (Excel/CSV/JSON) and unstructured
        (PDF/DOCX/TXT/MD/HTML) uploads. Each context's ``text`` is a compact
        preview (schema for structured, summary+tags for unstructured).
        ``metadata.source_type`` is either ``structured_vault`` or
        ``unstructured_vault`` so ``streaming_response.py`` can mount the
        raw bytes into the sandbox for ``execute_code``.

        Relevance gating
        ----------------
        ``query`` is forwarded to both listings: structured falls back to
        full-list when scoring fails (back-compat); unstructured strictly
        requires either ``attached_document_ids`` or a positive scorer
        match (with a recency fallback for "this/uploaded" cues).
        """
        try:
            from services.structured_file_listing import (
                list_structured_files,
                format_schema_preview_for_prompt,
            )
            from services.unstructured_file_listing import (
                list_unstructured_files,
                format_unstructured_preview_for_prompt,
            )

            structured_listing, unstructured_listing = await asyncio.gather(
                list_structured_files(
                    user_id=user_id,
                    folder_ids=folder_ids,
                    query=query,
                    attached_document_ids=attached_document_ids,
                ),
                list_unstructured_files(
                    user_id=user_id,
                    folder_ids=folder_ids,
                    query=query,
                    attached_document_ids=attached_document_ids,
                ),
                return_exceptions=True,
            )

            if isinstance(structured_listing, Exception):
                logger.warning("SaaSDataTool: structured listing failed: %s", structured_listing)
                structured_listing = {"entries": [], "truncated_files": []}
            if isinstance(unstructured_listing, Exception):
                logger.warning("SaaSDataTool: unstructured listing failed: %s", unstructured_listing)
                unstructured_listing = {"entries": [], "truncated_files": []}

            structured_entries = structured_listing.get("entries", [])
            structured_truncated = structured_listing.get("truncated_files", [])
            unstructured_entries = unstructured_listing.get("entries", [])
            unstructured_truncated = unstructured_listing.get("truncated_files", [])

            if not structured_entries and not unstructured_entries:
                logger.info(
                    "⏭️ SaaSDataTool: no relevant vault files for user %s folder_ids=%s",
                    (user_id or "?")[:8], folder_ids,
                )
                return []

            logger.info(
                "🔍 SaaSDataTool: %d structured + %d unstructured files (user=%s folders=%s, query='%s')",
                len(structured_entries), len(unstructured_entries),
                (user_id or "?")[:8], folder_ids, (query or "")[:80],
            )

            contexts: List[Dict[str, Any]] = []

            for idx, entry in enumerate(structured_entries):
                file_preview = format_schema_preview_for_prompt(
                    [entry],
                    truncated_files=structured_truncated if idx == 0 else None,
                )
                contexts.append({
                    "text": file_preview,
                    "score": 1.0,
                    "metadata": {
                        "source_type": "structured_vault",
                        "data_source": "structured_file_metadata",
                        "filename": entry.filename,
                        "document_id": entry.document_id,
                        "s3_key": entry.s3_key,
                        "total_rows": entry.total_rows,
                        "folder_id": entry.folder_id,
                        "truncated_files": structured_truncated if idx == 0 else [],
                    },
                    "source": "saas",
                    "citations": [{
                        "document_id": entry.document_id,
                        "topic": entry.filename,
                    }] if entry.document_id else [],
                })

            for idx, entry in enumerate(unstructured_entries):
                file_preview = format_unstructured_preview_for_prompt(
                    [entry],
                    truncated_files=unstructured_truncated if idx == 0 else None,
                )
                contexts.append({
                    "text": file_preview,
                    "score": float(entry.relevance_score) or 1.0,
                    "metadata": {
                        "source_type": "unstructured_vault",
                        "data_source": "unstructured_file_metadata",
                        "filename": entry.filename,
                        "document_id": entry.document_id,
                        "s3_key": entry.s3_key,
                        "doc_type": entry.doc_type,
                        "folder_id": entry.folder_id,
                        "relevance_reason": entry.relevance_reason,
                        "truncated_files": unstructured_truncated if idx == 0 else [],
                    },
                    "source": "saas",
                    "citations": [{
                        "document_id": entry.document_id,
                        "topic": entry.filename,
                    }] if entry.document_id else [],
                })

            return contexts

        except Exception as e:
            logger.error(f"❌ SaaSDataTool retrieval failed: {e}", exc_info=True)
            return []


class PersonalDataTool:
    """Tool for retrieving personal data from Milvus using UnifiedQueryEngine"""
    
    def __init__(self):
        self.query_engine = UnifiedQueryEngine()
        logger.info("✅ PersonalDataTool initialized with UnifiedQueryEngine")
    
    async def retrieve(
        self,
        query: str,
        user_id: str,
        max_results: int = 10,
        selected_folder_ids: Optional[List[str]] = None,
        folder_search_enabled: bool = False,
        similarity_threshold: Optional[float] = None,
        skip_rerank: bool = False,
        **kwargs  # Accept additional parameters for multi-hop compatibility
    ) -> List[Dict[str, Any]]:
        """
        Retrieve personal data contexts

        Args:
            query: Search query
            user_id: User identifier for namespace
            max_results: Maximum number of results to return
            selected_folder_ids: List of folder IDs to filter by
            folder_search_enabled: Whether folder filtering is enabled
            similarity_threshold: Similarity threshold for vector search (default: None, uses PERSONAL_SIMILARITY_THRESHOLD from milvus_config)
            skip_rerank: When True, skip the cross-encoder reranker and Milvus
                over-fetch — used by lite-mode callers (per-slide/page/section)
                to avoid the 10-30 s reranker round-trip when the query is
                already focused enough that Milvus top-k is good enough.

        Returns:
            List of context dictionaries with text, metadata, and citations
        """
        try:
            # Extract user_email from kwargs for embedding tracking
            user_email = kwargs.get('user_email')
            # Batch-prefetch callers supply a precomputed embedding so we skip
            # the per-query /embeddings RTT (and its rate-limit retry).
            precomputed_embedding = kwargs.get('precomputed_embedding')
            # Outline retrievers opt in to adaptive backfill (vague query /
            # narrow score band / under-floor → take top-K of raw results
            # instead of starving the outline LLM of context).
            adaptive_threshold = kwargs.get('adaptive_threshold', False)
            adaptive_floor = kwargs.get('adaptive_floor', 5)

            logger.info(f"🔍 PersonalDataTool retrieving for user {user_id}: '{query[:100]}...'")
            logger.info(f"   📁 Folder filtering enabled: {folder_search_enabled}")
            logger.info(f"   📂 Selected folders: {selected_folder_ids}")

            contexts = await self.query_engine.retrieve_personal_context(
                query=query,
                user_id=user_id,
                max_results=max_results,
                selected_folder_ids=selected_folder_ids,
                folder_search_enabled=folder_search_enabled,
                similarity_threshold=similarity_threshold,
                user_email=user_email,
                skip_rerank=skip_rerank,
                precomputed_embedding=precomputed_embedding,
                adaptive_threshold=adaptive_threshold,
                adaptive_floor=adaptive_floor,
            )
            
            logger.info(f"✅ PersonalDataTool retrieved {len(contexts)} contexts")
            return contexts
            
        except Exception as e:
            logger.error(f"❌ PersonalDataTool retrieval failed: {e}")
            return []

# EnterpriseDataTool (Milvus-backed enterprise retrieval) was retired.
# Enterprise data is now fetched exclusively via the `dept_*` MCP tools
# in services/enterprise_tools.py + services/enterprise_mcp_client.py.

# ═══════════════════════════════════════════════════════════════════
# Tool Registry
# ═══════════════════════════════════════════════════════════════════
RETRIEVAL_TOOLS = {
    'personal': PersonalDataTool(),
    'saas': SaaSDataTool(),
}

def get_retrieval_tool(tool_name: str):
    """Get a retrieval tool by name"""
    return RETRIEVAL_TOOLS.get(tool_name)
