# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Context Merger for Agentic RAG System
=====================================

This module implements intelligent context merging and ranking using LLM
to combine and prioritize contexts from different sources.
"""

import json
import logging
import re
import time
from collections import OrderedDict
from typing import List, Dict, Any, Optional
import os
import asyncio

logger = logging.getLogger(__name__)

class ContextMerger:
    """Smart context merger using LLM for ranking and synthesis"""
    
    def __init__(self):
        logger.info("🔄 ContextMerger initialized with LLM")
    
    async def merge_and_rank_contexts(
        self,
        query: str,
        contexts_by_source: Dict[str, List[Dict[str, Any]]],
        max_contexts: int = 10,
        prioritize_sources: Optional[List[str]] = None,
        user_id: str = None,
        user_email: str = None
    ) -> Dict[str, Any]:
        """
        Merge and rank contexts from multiple sources
        
        Args:
            query: Original user query
            contexts_by_source: Dict mapping source names to context lists
            max_contexts: Maximum number of contexts to return
            prioritize_sources: Optional list of sources to prioritize
            user_id: Optional user ID for token tracking
            user_email: Optional user email for token tracking
            
        Returns:
            Dict with merged_contexts and metadata
        """
        try:
            t_merge = time.time()
            logger.info(f"🔄 Merging contexts for query: '{query[:50]}...'")
            
            # Collect all contexts with source labels and deduplicate
            all_contexts = []
            source_counts = {}
            seen_ids = set()  # Track unique chunk IDs for deduplication
            duplicate_count = 0
            
            for source, contexts in contexts_by_source.items():
                source_counts[source] = len(contexts)
                for ctx in contexts:
                    # Generate unique ID for deduplication
                    # Priority: node_id > id > chunk_id > text hash
                    chunk_id = (
                        ctx.get('node_id') or 
                        ctx.get('id') or 
                        ctx.get('chunk_id') or 
                        ctx.get('metadata', {}).get('chunk_id') or
                        ctx.get('metadata', {}).get('node_id')
                    )
                    
                    if not chunk_id:
                        # Fallback: use hash of text content for deduplication
                        text_for_hash = ctx.get('text', '')[:500]  # Use first 500 chars
                        if text_for_hash:
                            chunk_id = f"hash_{hash(text_for_hash)}"
                    
                    # Skip duplicates
                    if chunk_id and chunk_id in seen_ids:
                        duplicate_count += 1
                        logger.debug(f"   🔄 Skipping duplicate chunk: {chunk_id}")
                        continue
                    
                    if chunk_id:
                        seen_ids.add(chunk_id)
                    ctx_copy = ctx.copy()
                    ctx_copy['source'] = source
                    all_contexts.append(ctx_copy)
            
            if duplicate_count > 0:
                logger.info(f"� Deduplicated {duplicate_count} duplicate chunks")
            
            logger.info(f"�📊 Source distribution: {source_counts}")
            logger.info(f"📊 Unique contexts after deduplication: {len(all_contexts)}")
            
            if not all_contexts:
                logger.info("ℹ️ No contexts to merge")
                return {
                    "merged_contexts": [],
                    "source_distribution": source_counts,
                    "total_contexts": 0
                }
            
            # Check if LLM-based ranking is enabled
            enable_context_ranking = os.getenv('ENABLE_CONTEXT_RANKING', 'false').lower() == 'true'
            
            # Check ranking method: "reranker" | "llm" | "score" (default: reranker)
            ranking_method = os.getenv('CONTEXT_RANKING_METHOD', 'reranker').lower().strip()
            
            # Separate structured/analytics contexts (sandbox-computed) from
            # regular vector-search chunks.  Structured contexts are exact SQL
            # query results and must ALWAYS be sent to the LLM in full — they
            # should never be dropped or reranked.
            #
            # Vault file-listing chunks (`structured_vault` / `unstructured_vault`)
            # are ALSO exempt: they are sentinel records emitted by SaaSDataTool
            # carrying {filename, s3_key, schema/summary} for files the LLM-based
            # `file_relevance_scorer` already approved for this query. The
            # streaming layer reads these to mount /workspace/input/<filename>
            # into the execute_code sandbox. If the cross-encoder drops them in
            # favor of higher-scoring data chunks of the SAME file, the LLM is
            # told `files=False` and ends up hardcoding inline data from chunk
            # previews — which breaks tool-call JSON encoding and triggers
            # retry loops.
            _EXEMPT_FROM_RANKING = {'structured_sql', 'structured_vault', 'unstructured_vault'}
            structured_contexts = []
            rankable_contexts = []
            for ctx in all_contexts:
                src_type = ctx.get('metadata', {}).get('source_type', '')
                if src_type in _EXEMPT_FROM_RANKING:
                    structured_contexts.append(ctx)
                else:
                    rankable_contexts.append(ctx)
            
            if structured_contexts:
                logger.info(f"📊 Preserved {len(structured_contexts)} structured/vault context(s) — exempt from ranking")
            
            # Adjust max_contexts for the rankable pool (reserve room for structured)
            rankable_max = max(max_contexts - len(structured_contexts), 0)
            
            # If we have too many rankable contexts, use ranking
            if len(rankable_contexts) > rankable_max and rankable_max > 0:
                if ranking_method == 'reranker':
                    try:
                        from reranker import is_reranker_enabled, rerank as rerank_chunks
                        if is_reranker_enabled():
                            # Filter chunks with text for reranking
                            chunks_with_text = [c for c in rankable_contexts if c.get('text', '').strip()]
                            if chunks_with_text:
                                logger.info(f"🔁 Using cross-encoder reranker for context ranking ({len(chunks_with_text)} chunks)")
                                ranked_contexts = rerank_chunks(query, chunks_with_text, rankable_max)
                            else:
                                logger.info("📊 No chunks with text — falling back to score-based ranking")
                                ranked_contexts = self._fallback_ranking(rankable_contexts, rankable_max)
                        else:
                            logger.info("📊 Reranker disabled — falling back to score-based ranking")
                            ranked_contexts = self._fallback_ranking(rankable_contexts, rankable_max)
                    except Exception as e:
                        logger.warning(f"⚠️ Reranker failed in context merger: {e} — falling back")
                        ranked_contexts = self._fallback_ranking(rankable_contexts, rankable_max)
                elif enable_context_ranking or ranking_method == 'llm':
                    logger.info("🎯 Using LLM-based context ranking with LLM")
                    ranked_contexts = await self._rank_contexts_with_llm(
                        query, rankable_contexts, rankable_max, prioritize_sources,
                        user_id, user_email
                    )
                else:
                    logger.info("📊 LLM ranking disabled - using score-based ranking")
                    ranked_contexts = self._fallback_ranking(rankable_contexts, rankable_max)
            else:
                ranked_contexts = rankable_contexts
            
            # Prepend structured contexts — they always come first for the LLM
            ranked_contexts = structured_contexts + ranked_contexts
            
            logger.info(f"⏱️ [Merger] Context merging: {time.time() - t_merge:.3f}s ({len(ranked_contexts)} contexts selected)")
            
            return {
                "merged_contexts": ranked_contexts,
                "source_distribution": source_counts,
                "total_contexts": len(ranked_contexts)
            }
            
        except Exception as e:
            logger.error(f"❌ Context merging failed: {e}")
            # Return empty result on error
            return {
                "merged_contexts": [],
                "source_distribution": {},
                "total_contexts": 0
            }
    
    async def _rank_contexts_with_llm(
        self,
        query: str,
        contexts: List[Dict[str, Any]],
        max_contexts: int,
        prioritize_sources: Optional[List[str]] = None,
        user_id: str = None,
        user_email: str = None
    ) -> List[Dict[str, Any]]:
        """Use LLM model to intelligently filter and rank contexts based on query relevance"""
        
        # Prepare context data for ranking with more context
        context_data = []
        for i, ctx in enumerate(contexts):
            # Get more text for better relevance assessment (500 chars instead of 200)
            text = ctx.get('text', '')
            text_preview = text[:500] + "..." if len(text) > 500 else text
            
            # Extract basic document info
            metadata = ctx.get('metadata', {})
            topic = metadata.get('topic_or_filename', ctx.get('topic', 'Unknown'))
            
            context_data.append({
                "id": i,
                "source": ctx.get('source', 'unknown'),
                "text_preview": text_preview,
                "score": ctx.get('score', 0.0),
                "document": topic
            })
        
        # Enhanced prompt for relevance filtering and ranking
        ranking_prompt = f"""You are a legal document relevance filter. Your task is to identify which chunks are RELEVANT to the user's query and filter out IRRELEVANT chunks.

USER QUERY: "{query}"

AVAILABLE CONTEXTS ({len(context_data)} total):
{json.dumps(context_data, indent=2)}

INSTRUCTIONS:
1. **FILTER FOR RELEVANCE**: Only include chunks that are DIRECTLY relevant to the query topic, case, or legal issue
2. **REJECT IRRELEVANT CHUNKS**: Exclude chunks from:
   - Different cases/documents (wrong case numbers, parties, or topics)
   - Unrelated legal issues or domains
   - Generic procedural text not answering the query
3. **RANK BY RELEVANCE**: Order remaining chunks by:
   - Direct answer to query (highest priority)
   - Supporting context and background
   - Related legal principles or citations
4. **MAXIMUM**: Return up to {max_contexts} most relevant chunks
5. **MINIMUM**: If fewer than {max_contexts} chunks are relevant, return only the relevant ones

**CRITICAL OUTPUT FORMAT:**
Return ONLY a valid JSON array. No explanations, no markdown, no extra text.
Just the array: [0, 5, 12, 3, ...]
If NO chunks are relevant, return: []

Your response must be ONLY the JSON array, nothing else.
"""
        
        try:

            from llm_oss import llm_call
            logger.info(f"🤖 Invoking llm_oss model for relevance filtering on {len(contexts)} chunks...")
            response = await asyncio.to_thread(lambda: llm_call(system_prompt="", user_prompt=ranking_prompt, max_tokens=16000, user_id=user_id, user_email=user_email, tier="large"))
            
            # Parse response - handle markdown code blocks if present
            response_clean = response.strip()
            if response_clean.startswith('```'):
                # Extract JSON from markdown code block
                lines = response_clean.split('\n')
                json_lines = [line for line in lines if not line.startswith('```')]
                response_clean = '\n'.join(json_lines).strip()
            
            ranked_ids = json.loads(response_clean)
            
            # Validate and return ranked contexts
            ranked_contexts = []
            for ctx_id in ranked_ids[:max_contexts]:
                if 0 <= ctx_id < len(contexts):
                    ranked_contexts.append(contexts[ctx_id])
            
            filtered_count = len(contexts) - len(ranked_contexts)
            logger.info(f"✅ LLM filtered and ranked {len(ranked_contexts)} relevant contexts (filtered out {filtered_count} irrelevant chunks)")
            
            if filtered_count > 0:
                logger.info(f"🚫 Filtered out {filtered_count} irrelevant chunks based on query relevance")
            
            return ranked_contexts
            
        except Exception as e:
            logger.error(f"❌ LLM relevance filtering failed: {e}, falling back to score-based ranking")
            return self._fallback_ranking(contexts, max_contexts)
    
    def _fallback_ranking(self, contexts: List[Dict], max_contexts: int) -> List[Dict]:
        """Fallback ranking based on scores"""
        sorted_contexts = sorted(
            contexts,
            key=lambda x: x.get('score', 0.0),
            reverse=True
        )
        return sorted_contexts[:max_contexts]

    # ------------------------------------------------------------------
    # SaaS file-upload record compaction
    # ------------------------------------------------------------------
    def _compact_file_upload_contexts(
        self,
        contexts: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Compact SaaS file_upload contexts (excel_row / json_record) into
        one tabular block per source file, drastically cutting token usage.

        Records from the same file share identical column headers, so we
        emit the header once and list rows in compact pipe-delimited format.

        Non-file-upload contexts are passed through unchanged.

        Returns a NEW list of context dicts (order preserved).
        """
        FILE_OBJECT_TYPES = {"excel_row", "json_record"}

        # Separate file-upload records from everything else
        file_groups: Dict[str, List[Dict[str, Any]]] = OrderedDict()
        other_contexts: List[Dict[str, Any]] = []

        for ctx in contexts:
            meta = ctx.get("metadata", {})
            provider = (meta.get("provider") or "").lower()
            obj_type = (meta.get("object_type") or "").lower()

            if provider == "file_upload" and obj_type in FILE_OBJECT_TYPES:
                # Group by nango_connection_id (= "file_{document_id}") — legacy field name
                group_key = meta.get("nango_connection_id") or "unknown_file"
                file_groups.setdefault(group_key, []).append(ctx)
            else:
                other_contexts.append(ctx)

        if not file_groups:
            return contexts  # Nothing to compact

        compacted: List[Dict[str, Any]] = []

        for group_key, group_ctxs in file_groups.items():
            # --- Extract filename / sheet from the first record's text ---
            first_text = group_ctxs[0].get("text", "")
            file_match = re.search(r'\[File:\s*(.+?)(?:\s*\|\s*Sheet:\s*(.+?))?\]', first_text)
            filename = file_match.group(1).strip() if file_match else group_key
            sheet = file_match.group(2).strip() if file_match and file_match.group(2) else None

            # --- Collect raw_data dicts and determine column order ---
            raw_rows: List[Dict[str, Any]] = []
            columns: List[str] = []
            seen_cols: set = set()
            best_score = 0.0

            for ctx in group_ctxs:
                score = ctx.get("score", 0.0)
                if score > best_score:
                    best_score = score

                citations = ctx.get("citations", [])
                raw_data = citations[0].get("raw_data", {}) if citations else {}

                if not raw_data:
                    # Fallback: parse key-value pairs from text
                    raw_data = {}
                    for line in ctx.get("text", "").splitlines():
                        line = line.strip()
                        if line.startswith("[") or line.startswith("Type:") or \
                           line.startswith("Columns:") or line.startswith("Keywords:") or \
                           line.startswith("Row "):
                            continue
                        if ": " in line:
                            k, v = line.split(": ", 1)
                            raw_data[k.strip()] = v.strip()

                if raw_data:
                    raw_rows.append(raw_data)
                    # Preserve column order from first occurrence
                    for col in raw_data.keys():
                        if col not in seen_cols:
                            seen_cols.add(col)
                            columns.append(col)

            if not raw_rows or not columns:
                # Can't compact — keep originals
                compacted.extend(group_ctxs)
                continue

            # --- Build compact tabular text ---
            header = f"Source: {filename}"
            if sheet:
                header += f" (Sheet: {sheet})"
            header += f" — {len(raw_rows)} rows"

            lines = [header]
            lines.append(f"Columns: {' | '.join(columns)}")
            lines.append("")  # blank separator

            for raw in raw_rows:
                values = []
                for col in columns:
                    val = raw.get(col)
                    if val is None or val == "":
                        values.append("")
                    elif isinstance(val, float):
                        values.append(str(int(val)) if val == int(val) else f"{val:,.2f}")
                    elif isinstance(val, int):
                        values.append(f"{val:,}")
                    else:
                        values.append(str(val)[:200])
                lines.append(" | ".join(values))

            compact_text = "\n".join(lines)

            # Use the first context as the template, replace text
            template = group_ctxs[0].copy()
            template["text"] = compact_text
            template["score"] = best_score
            # Tag so downstream knows this was compacted
            template.setdefault("metadata", {})["compacted_rows"] = len(raw_rows)
            compacted.append(template)

            logger.info(
                f"📊 Compacted {len(group_ctxs)} file-upload contexts for "
                f"'{filename}' into 1 tabular block ({len(raw_rows)} rows, "
                f"{len(columns)} cols)"
            )

        # Merge: compacted file blocks first, then other contexts
        result = compacted + other_contexts
        if len(result) < len(contexts):
            logger.info(
                f"📊 SaaS compaction: {len(contexts)} contexts → {len(result)} "
                f"(saved {len(contexts) - len(result)} context slots)"
            )
        return result

    async def create_response_context(
        self,
        query: str,
        merged_contexts: List[Dict[str, Any]],
        query_decomposition: Optional[List[str]] = None,
        sort_for_caching: bool = False,  # Disabled - chunks now sent as individual messages
        profession: Optional[str] = None  # Deprecated - kept for backward compatibility
    ) -> str:
        """
        Create a well-formatted context string for LLM response generation
        
        ⚠️ CACHING NOTE: Sorting disabled by default since chunks are now sent as
        individual messages in query.py, which provides better cache stability.
        
        Args:
            query: Original user query
            merged_contexts: Ranked and merged contexts
            query_decomposition: Optional query breakdown
            sort_for_caching: Whether to sort chunks by ID (deprecated, default: False)
            profession: Deprecated parameter kept for backward compatibility
            
        Returns:
            Formatted context string for LLM
        """
        if not merged_contexts:
            return ""
        
        # Sorting disabled - chunks sent as individual messages for better caching
        # Each chunk message can be cached independently
        
        context_parts = []
        
        # Add header
        context_parts.append("=== RELEVANT INFORMATION ===")
        context_parts.append("")
        
        # Group contexts by source for better organization
        contexts_by_source = {}
        for ctx in merged_contexts:
            source = ctx.get('source', 'unknown')
            if source not in contexts_by_source:
                contexts_by_source[source] = []
            contexts_by_source[source].append(ctx)

        # Compact SaaS file-upload records (deduplicate headers, tabular rows)
        if 'saas' in contexts_by_source:
            contexts_by_source['saas'] = self._compact_file_upload_contexts(
                contexts_by_source['saas']
            )

        # Citations are controlled by persona system prompt, not by profession here
        include_citations = True  # Always include citation references
        
        # Add contexts organized by source with citation instructions
        citation_references = []  # Collect citation references for instructions

        for source, contexts in contexts_by_source.items():
            source_label = source.replace('_', ' ').title()
            context_parts.append(f"--- {source_label} Information ---")

            for i, ctx in enumerate(contexts, 1):
                text = ctx.get('text', '')
                score = ctx.get('score', 0.0) if include_citations else None
                document_id = ctx.get('document_id', '')
                topic = ctx.get('topic', 'Unknown Document')
                metadata = ctx.get('metadata', {})

                if include_citations:
                    # Collect citation references for instructions (both document and chunk)
                    document_citation = ctx.get('document_citation', '')
                    chunk_citation = ctx.get('chunk_citation', '')

                    if document_citation:
                        citation_references.append(document_citation)
                    if chunk_citation:
                        citation_references.append(chunk_citation)

                # Add context header with basic info
                if include_citations and score is not None:
                    context_parts.append(f"[{source_label} {i}] (Relevance: {score:.2f})")
                else:
                    context_parts.append(f"[{source_label} {i}]")
                    
                # 🆕 Add source tag for AI to understand data freshness
                # Simplified: Use pre-set tag or lookup by source_type
                source_type = ctx.get('source_type', 'personal')
                source_tag = ctx.get('source_tag', '')  # Pre-set for supplementary sources
                
                # Source type → tag mapping (single lookup, no if-else chain)
                SOURCE_TAG_MAP = {
                    'personal': f"[VAULT: {topic if topic != 'Unknown Document' else document_id or 'document'}]",
                    'knowledge_graph': f"[VAULT: {topic if topic != 'Unknown Document' else document_id or 'document'}]",
                    'project_management': f"[VAULT: {topic if topic != 'Unknown Document' else document_id or 'document'}]",
                    'live_data': "[LIVE-DATABASE: Connected Database]",
                }
                
                # Use pre-set tag, or lookup, or skip (saas/sql tagged at source)
                tag_to_display = source_tag or SOURCE_TAG_MAP.get(source_type)
                if tag_to_display:
                    context_parts.append(f"🏷️ {tag_to_display}")
                    
                # Always include document info to help LLM correlate chunks from same document
                if document_id or topic != 'Unknown Document':
                    # Use separate lines to make it unambiguous for LLM
                    context_parts.append(f"📄 Document Name: {topic}")
                    context_parts.append(f"📄 Document ID: {document_id}")

                folder_id = metadata.get('folder_id') or ctx.get('folder_id')
                is_enterprise = metadata.get('is_enterprise')
                entity_id = metadata.get('entity_id') or ctx.get('entity_id')

                scope_label = "PERSONAL"
                scope_details = "Unassigned personal note"

                if folder_id:
                    scope_label = "CASE_FOLDER"
                    scope_details = f"Folder ID '{folder_id}'"
                elif is_enterprise:
                    normalized = (entity_id or "").strip().lower() if isinstance(entity_id, str) else ""
                    if normalized and normalized not in ("none", "null"):
                        scope_label = "ENTERPRISE_ENTITY"
                        scope_details = f"Entity '{entity_id}'"
                    else:
                        scope_label = "ENTERPRISE_GENERAL"
                        scope_details = "Shared enterprise reference"

                context_parts.append(f"🔖 Context Type: {scope_label} | {scope_details}")
                
                # Add chunk text content
                context_parts.append(f"\n{text}")
                context_parts.append("")
        
        # Add query breakdown if provided
        if query_decomposition and len(query_decomposition) > 1:
            context_parts.append("=== QUERY BREAKDOWN ===")
            for i, sub_query in enumerate(query_decomposition, 1):
                context_parts.append(f"{i}. {sub_query}")
            context_parts.append("")

        # Add available citation references (instructions are in system prompt)
        # Citation format and display controlled by persona system prompt
        if include_citations and citation_references:
            context_parts.append("=== AVAILABLE CITATIONS ===")
            for citation_ref in citation_references:
                if citation_ref.startswith("DOC::"):
                    parts = citation_ref.replace("DOC::", "").split("--")
                    if len(parts) == 2:
                        topic, doc_id = parts
                        context_parts.append(f"DOC: {topic} (ID: {doc_id})")
                elif citation_ref.startswith("CHUNK::"):
                    parts = citation_ref.replace("CHUNK::", "").split("--")
                    if len(parts) == 2:
                        topic, vector_id = parts
                        context_parts.append(f"CHUNK: {topic} (ID: {vector_id})")
            context_parts.append("")

        return "\n".join(context_parts)
