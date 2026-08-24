# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
internet_prefetch.py

Shared helper for prefetching research and embedding it into the user's
vault BEFORE outline / page / slide generation.

Why this exists:
- Previously, printable / presentation / report outline-stream endpoints called
  `llm_call_with_internet()`, which lets the LLM decide when to invoke the
  `internet_search` tool. In practice the orchestrator LLM made many tool-call
  rounds (5+) but only its short final summary was embedded in vault — the rich
  raw search bodies were thrown away. That short summary then bloated the
  outline prompt and degraded outline quality (e.g. 1 page produced instead of
  the requested 5).

- This module replaces that flow with a deterministic, single-call (or small
  fixed-N call) prefetch that:
    1. Calls `execute_internet_search()` directly (Grok web_search etc.).
    2. Embeds the FULL raw search answer into the user's vault as its own doc.
    3. Returns metadata so the caller can stream SSE `internet_research`
       events.
- After this prefetch runs, normal Milvus retrieval (`retrieve_vault_context`)
  picks up the freshly embedded doc for outline + page/slide generation. There
  is no need to inline the giant blob into the outline prompt.

Two entry points share the same embed path (`_embed_text_into_vault`):
  * `prefetch_internet_research` — this module runs the internet searches.
  * `prefetch_corpus` — the caller (e.g. quick / main chat, which already did
    a fast search) supplies the research corpus; we just embed it. This is how
    a chat surface hands its findings to the presentation / report builder
    without spawning a deep-research sandbox: same vault-grounded pipeline,
    the research is just sourced upstream.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _build_queries(goal: str, doc_type: str, num_queries: int) -> List[str]:
    """
    Produce up to `num_queries` search queries from the user's goal.

    - num_queries=1 → single comprehensive query (recommended default; Grok
      web_search is broad enough on its own).
    - num_queries=2 → base query + a recent-news/outlook variant.
    - num_queries>=3 → adds a financials/data-focused variant.
    """
    base = goal.strip()
    if num_queries <= 1:
        return [base]

    queries = [base]
    if num_queries >= 2:
        queries.append(f"{base} latest news 2025 2026 outlook")
    if num_queries >= 3:
        queries.append(f"{base} financial data statistics recent figures")
    return queries[:num_queries]


async def _embed_text_into_vault(
    *,
    text: str,
    filename: str,
    user_id: str,
    folder_id: str,
    source: str,
    id_prefix: str,
    source_meta: Optional[Dict] = None,
) -> Optional[Dict]:
    """Embed one raw text blob into the user's vault so normal Milvus
    retrieval picks it up.

    S3 upload + chunk/embed into Milvus + register in the central files
    collection — identical to how any uploaded vault document is stored,
    so reader / citation / delete paths treat it the same.

    Shared by `prefetch_internet_research` and `prefetch_corpus`.

    Returns ``{document_id, word_count}`` on success, ``None`` if the
    embed step failed (caller skips that item).
    """
    from document_manager import create_embeddings_and_store_milvus, save_file_to_s3_storage
    from citra_mongo import MONGODB_DATABASE, get_async_mongo_client
    from services.files_service import FilesService
    from utils import get_user_id

    if not text or not text.strip():
        return None

    doc_id = f"{id_prefix}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    text_bytes = text.encode("utf-8")
    file_size_bytes = len(text_bytes)
    now_iso = datetime.utcnow().isoformat()

    # 1) Upload raw text to S3 so the doc is retrievable like any other vault file.
    s3_url: Optional[str] = None
    try:
        s3_url = await asyncio.to_thread(
            save_file_to_s3_storage,
            text_bytes,
            doc_id,
            ".txt",
            get_user_id(user_id),
            filename,
            False,           # is_enterprise
            None,            # entity_id
            folder_id,
        )
    except Exception as e:
        logger.warning(f"🌐 [PREFETCH] S3 upload failed for {doc_id}: {e}")

    # 2) Create chunks + embeddings (MongoDB documents collection + Milvus).
    try:
        embed_result: Dict = await create_embeddings_and_store_milvus(
            document_id=doc_id,
            topic=filename,
            text=text,
            user_id=user_id,
            event_epoch=int(time.time()),
            utc_date=now_iso,
            folder_id=folder_id,
            file_metadata={"file_type": "txt", "filename": filename},
        ) or {}
    except Exception as e:
        logger.error(f"🌐 [PREFETCH] Failed to embed doc {doc_id}: {e}")
        return None

    # 3) Register in the central files collection so reader / citations /
    #    delete paths treat it like any other vault document.
    try:
        files_service = FilesService(get_async_mongo_client(), MONGODB_DATABASE)
        file_metadata_doc = {
            "_id": doc_id,
            "user_id": user_id,
            "filename": filename,
            "original_filename": filename,
            "file_extension": "txt",
            "file_type_category": "document",
            "topic_or_filename": filename,
            "created_at": now_iso,
            "updated_at": now_iso,
            "folder_id": folder_id,
            "is_enterprise": False,
            "entity_id": None,
            "file_size_bytes": file_size_bytes,
            "db_size_bytes": file_size_bytes,
            "content_type": "text/plain",
            "s3_url": s3_url,
            "storage_location": "s3" if s3_url and not s3_url.startswith("local://") else "mongodb",
            "source": source,
            "milvus_primary_keys": embed_result.get("vector_ids", []) or [],
            "mongodb_collections": {
                "document_chunked_ids": doc_id,
                "milvus_chunks_id": None,
                "transcripts_id": None,
                "video_transcripts_id": None,
                "notes_id": None,
            },
        }
        if source_meta:
            file_metadata_doc.update(source_meta)
        await files_service.register_file(file_metadata_doc)
    except Exception as reg_err:
        # Non-fatal — embedding succeeded; delete will fall back to path
        # reconstruction as before.
        logger.warning(
            f"🌐 [PREFETCH] Files-registry registration failed for {doc_id}: {reg_err}"
        )

    return {"document_id": doc_id, "word_count": len(text.split())}


async def prefetch_internet_research(
    *,
    goal: str,
    doc_type: str,
    target_audience: Optional[str],
    user_id: str,
    folder_id: Optional[str],
    user_email: Optional[str] = None,
    num_queries: int = 1,
    max_tokens_per_query: int = 8000,
) -> List[Dict]:
    """
    Run N direct internet searches and embed each raw answer into the vault.

    Args:
        goal: User's original document goal/topic.
        doc_type: "presentation" | "printable" | "report" (used in filename).
        target_audience: Free-text audience descriptor (currently unused by
            search providers but kept for future query enrichment).
        user_id: Vault owner.
        folder_id: Folder to embed into. Falls back to "documents" if None.
        user_email: For billing tracking.
        num_queries: 1–3. See `_build_queries`.
        max_tokens_per_query: Cap on Grok response size per search.

    Returns:
        List of dicts: {document_id, query, folder_id, word_count, text}.
        Empty list on total failure (caller continues without internet data).
    """
    from citra_internet_service import execute_internet_search

    effective_folder = folder_id or "documents"
    queries = _build_queries(goal, doc_type, max(1, min(3, int(num_queries))))
    results: List[Dict] = []

    for query in queries:
        try:
            # execute_internet_search is sync (Grok responses API blocking).
            internet_text = await asyncio.to_thread(
                execute_internet_search,
                query,
                f"Research for a {doc_type}. Audience: {target_audience or 'General professional audience'}.",
                user_id,
                user_email,
                None,                  # model: provider default
                max_tokens_per_query,  # max_tokens
                0.2,                   # temperature
            )
        except Exception as e:
            logger.warning(f"🌐 [INTERNET_PREFETCH] Search failed for query '{query[:80]}': {e}")
            continue

        if not internet_text or not internet_text.strip():
            logger.info(f"🌐 [INTERNET_PREFETCH] Empty result for query '{query[:80]}'")
            continue

        embedded = await _embed_text_into_vault(
            text=internet_text,
            filename=f"Internet Research: {query[:100]}",
            user_id=user_id,
            folder_id=effective_folder,
            source="internet_research",
            id_prefix="internet",
            source_meta={"internet_query": query},
        )
        if not embedded:
            continue

        logger.info(
            f"🌐 [INTERNET_PREFETCH] Embedded {embedded['word_count']} words into vault "
            f"(doc={embedded['document_id']}, folder={effective_folder}, query='{query[:80]}')"
        )
        results.append({
            "document_id": embedded["document_id"],
            "query": query,
            "folder_id": effective_folder,
            "word_count": embedded["word_count"],
            "text": internet_text,
        })

    return results


async def prefetch_corpus(
    *,
    corpus: List[Dict],
    doc_type: str,
    user_id: str,
    folder_id: Optional[str],
    user_email: Optional[str] = None,
) -> List[Dict]:
    """Embed a caller-supplied research corpus into the vault.

    Same vault-embed path as `prefetch_internet_research`, but the text is
    provided by the caller instead of being searched here. This is how a
    fast chat surface (quick chat / main chat) hands its already-gathered
    research to the presentation / report builder: the surface does the
    fast search, passes the findings as `corpus`, and the normal
    outline + per-slide Milvus retrieval grounds the deck on it — no deep-
    research sandbox spawn, no separate retrieval source, no temp Milvus
    collection (the docs are normal vault docs, tagged ``source`` so they
    can be cleaned up afterwards if desired).

    Args:
        corpus: list of ``{"text": str, "title"?: str, "source"?: str}``.
            One vault document is created per non-empty entry.
        doc_type: "presentation" | "printable" | "report".
        user_id: Vault owner.
        folder_id: Folder to embed into. Falls back to "documents" if None.
        user_email: For billing tracking (reserved).

    Returns:
        List of ``{document_id, folder_id, word_count}`` — one per embedded
        entry. Empty list if nothing embedded (caller continues without it).
    """
    effective_folder = folder_id or "documents"
    results: List[Dict] = []

    for i, item in enumerate(corpus or []):
        text = ((item or {}).get("text") or "").strip()
        if not text:
            continue
        title = ((item or {}).get("title") or "").strip() or f"Research Note {i + 1}"
        src_url = ((item or {}).get("source") or "").strip()

        embedded = await _embed_text_into_vault(
            text=text,
            filename=f"Research: {title[:100]}",
            user_id=user_id,
            folder_id=effective_folder,
            source="chat_research",
            id_prefix="research",
            source_meta={"research_source_url": src_url} if src_url else None,
        )
        if not embedded:
            continue
        results.append({
            "document_id": embedded["document_id"],
            "folder_id": effective_folder,
            "word_count": embedded["word_count"],
        })

    logger.info(
        f"🌐 [CORPUS_PREFETCH] embedded {len(results)}/{len(corpus or [])} "
        f"research note(s) into vault (folder={effective_folder}, doc_type={doc_type})"
    )
    return results
