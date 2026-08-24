# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Unstructured File Listing
=========================

Sibling to ``services/structured_file_listing.py`` for unstructured uploads
(PDF / DOCX / TXT / MD / HTML / etc.). Reads the new
``unstructured_file_metadata`` collection produced at upload time by
``document_manager._capture_unstructured_file_metadata`` and joins it with
``files`` to resolve ``s3_key``.

Why this exists
---------------
The structured-vault pipeline (csv/excel/json) already mounts files into the
``execute_code`` sandbox so the LLM can run pandas etc. PDFs and Office
documents need the same treatment so the agent can convert / inspect /
extract them — without dragging full document text into context. This
listing returns an ``UnstructuredFileEntry`` per matched file: enough
metadata for the LLM to decide what to do, plus the ``s3_key`` for the
sandbox mount.

Relevance gating
----------------
This is the slow path: bringing a 50-MB PDF text into chat context every
turn would explode the token bill. We therefore **only** include files that
either (a) match ``attached_document_ids`` for this turn, or (b) are scored
≥ threshold by the large-LLM-based ``services.file_relevance_scorer``.
Falls back to recency when the user query has explicit "this/uploaded/
recent" cues but the scorer returned nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Soft caps — tighter than structured because PDFs are typically larger and
# the agent rarely needs more than 1–2 unstructured files per turn.
MAX_FILES = 3
MAX_TOTAL_BYTES = 30 * 1024 * 1024  # 30 MB

# Cues that justify a recency fallback when the relevance scorer matches nothing.
_RECENCY_CUES = (
    "this file", "the file", "this document", "the document",
    "this pdf", "the pdf", "this doc", "the doc",
    "uploaded", "just attached", "i shared", "i uploaded",
    "recent", "latest", "above",
)


def _resolve_s3_key(file_doc: Dict[str, Any]) -> Optional[str]:
    """Same s3_url → s3_key derivation used by structured_file_listing."""
    s3_key = file_doc.get("s3_key")
    if s3_key:
        return s3_key
    s3_url = file_doc.get("s3_url")
    if not s3_url:
        return None
    if ".amazonaws.com/" in s3_url:
        return s3_url.split(".amazonaws.com/", 1)[-1]
    if s3_url.startswith("s3://"):
        without_scheme = s3_url[len("s3://"):]
        return without_scheme.split("/", 1)[-1] if "/" in without_scheme else None
    return s3_url


@dataclass
class UnstructuredFileEntry:
    document_id: str
    filename: str
    s3_key: str
    file_type: str = ""
    summary: str = ""
    doc_type: str = ""
    semantic_tags: List[str] = field(default_factory=list)
    key_entities: List[str] = field(default_factory=list)
    folder_id: Optional[str] = None
    file_size: Optional[int] = None
    text_length: int = 0
    relevance_score: float = 0.0
    relevance_reason: str = ""

    def to_sandbox_file(self) -> Dict[str, str]:
        return {"filename": self.filename, "s3_key": self.s3_key}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _has_recency_cue(query: str) -> bool:
    if not query:
        return False
    q = query.lower()
    return any(cue in q for cue in _RECENCY_CUES)


async def list_unstructured_files(
    user_id: str,
    folder_ids: Optional[List[str]] = None,
    *,
    query: Optional[str] = None,
    attached_document_ids: Optional[List[str]] = None,
    max_files: int = MAX_FILES,
    max_total_bytes: int = MAX_TOTAL_BYTES,
) -> Dict[str, Any]:
    """
    Resolve the unstructured (PDF/DOCX/TXT/...) files in scope that are
    relevant to ``query`` (or explicitly attached this turn) and return a
    list ready for prompt injection + sandbox mount.

    Selection tiers (in order):
      1. If ``attached_document_ids`` provided → return ONLY those (deterministic).
      2. Else if ``query`` provided → run ``score_files_against_query`` and
         keep entries above the threshold.
      3. Else if recency cues in query and Tier-2 returned nothing → return
         single most-recent file.
      4. Else → return [] (do NOT mount everything).

    Returns
    -------
    dict::

        {
            "entries":          List[UnstructuredFileEntry],
            "truncated_files":  List[str],
            "total_available":  int,
            "total_bytes":      int,
        }
    """
    if not user_id:
        return {"entries": [], "truncated_files": [], "total_available": 0, "total_bytes": 0}

    try:
        from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
    except ImportError:
        logger.exception("unstructured_file_listing: cannot import citra_mongo as mongodb_manager")
        return {"entries": [], "truncated_files": [], "total_available": 0, "total_bytes": 0}

    client = get_async_mongo_client()
    db = client[MONGODB_DATABASE]

    metadata_filter: Dict[str, Any] = {"user_id": user_id}
    if folder_ids:
        metadata_filter["folder_id"] = {"$in": folder_ids}

    try:
        cursor = db["unstructured_file_metadata"].find(metadata_filter).sort("updated_at", -1)
        metadata_docs = await cursor.to_list(length=200)
    except Exception:
        logger.exception("unstructured_file_listing: metadata query failed")
        return {"entries": [], "truncated_files": [], "total_available": 0, "total_bytes": 0}

    if not metadata_docs:
        return {"entries": [], "truncated_files": [], "total_available": 0, "total_bytes": 0}

    total_available = len(metadata_docs)

    # ── Tier 1: explicit attached document IDs override everything. ──
    if attached_document_ids:
        wanted = set(attached_document_ids)
        metadata_docs = [m for m in metadata_docs if m.get("document_id") in wanted]
        relevance_by_id: Dict[str, Dict[str, Any]] = {
            d.get("document_id"): {"score": 1.0, "reason": "attached this turn"}
            for d in metadata_docs
        }
    elif query:
        # ── Tier 2: large-LLM relevance scoring against the query. ──
        relevance_by_id = {}
        try:
            from services.file_relevance_scorer import (
                score_files_against_query,
                CandidateFile,
                ScorerUnavailable,
            )

            candidates = [
                CandidateFile(
                    document_id=m.get("document_id"),
                    filename=m.get("filename", ""),
                    file_type=m.get("file_type", ""),
                    summary=m.get("summary", ""),
                    doc_type=m.get("doc_type", ""),
                    semantic_tags=m.get("semantic_tags", []) or [],
                    key_entities=m.get("key_entities", []) or [],
                )
                for m in metadata_docs if m.get("document_id")
            ]
            try:
                scored = await score_files_against_query(
                    query=query,
                    candidates=candidates,
                    user_id=user_id,
                    folder_ids=folder_ids,
                )
                relevance_by_id = {
                    s.document_id: {"score": s.score, "reason": s.reason}
                    for s in scored
                }
                metadata_docs = [m for m in metadata_docs if m.get("document_id") in relevance_by_id]
            except ScorerUnavailable as e:
                # Scorer unreachable — fall back to a single most-recent file
                # so the user's vault PDF is still mounted into the sandbox
                # rather than silently dropped.
                logger.warning(
                    "unstructured_file_listing: scorer unavailable (%s); falling back to most-recent file",
                    e,
                )
                metadata_docs.sort(
                    key=lambda m: m.get("updated_at") or m.get("created_at") or 0,
                    reverse=True,
                )
                metadata_docs = metadata_docs[:1]
                for m in metadata_docs:
                    relevance_by_id[m.get("document_id")] = {
                        "score": 0.5,
                        "reason": "scorer unavailable; using most recently uploaded file",
                    }
        except Exception:
            logger.exception("unstructured_file_listing: relevance scoring failed")
            metadata_docs = []

        # ── Tier 3: recency fallback only on explicit cues. ──
        if not metadata_docs and _has_recency_cue(query):
            try:
                cursor = db["unstructured_file_metadata"].find(
                    {"user_id": user_id, **({"folder_id": {"$in": folder_ids}} if folder_ids else {})}
                ).sort("updated_at", -1).limit(1)
                metadata_docs = await cursor.to_list(length=1)
                for m in metadata_docs:
                    relevance_by_id[m.get("document_id")] = {
                        "score": 0.5, "reason": "most recently uploaded (recency cue in query)"
                    }
                logger.info("unstructured_file_listing: recency fallback returned %d", len(metadata_docs))
            except Exception:
                logger.exception("unstructured_file_listing: recency fallback failed")
    else:
        # ── Tier 4 (no signal): return nothing. We refuse to mount the
        #    user's whole vault on a no-context turn — that is exactly the
        #    context-bloat case we're trying to avoid. The agent can still
        #    discover files via personal-data RAG (Milvus), and the user
        #    can opt-in by attaching or asking about a file by name.
        return {"entries": [], "truncated_files": [], "total_available": total_available, "total_bytes": 0}

    if not metadata_docs:
        return {"entries": [], "truncated_files": [], "total_available": total_available, "total_bytes": 0}

    document_ids = [m.get("document_id") for m in metadata_docs if m.get("document_id")]
    try:
        files_cursor = db["files"].find(
            {"_id": {"$in": document_ids}},
            {
                "_id": 1,
                "s3_url": 1,
                "s3_key": 1,
                "file_size_bytes": 1,
                "size": 1,
                "file_size": 1,
                "filename": 1,
            },
        )
        files_docs = await files_cursor.to_list(length=len(document_ids))
    except Exception:
        logger.exception("unstructured_file_listing: files lookup failed")
        files_docs = []

    files_by_id = {f.get("_id"): f for f in files_docs}

    # Sort by relevance score descending, then by updated_at desc as tiebreak.
    def _sort_key(meta: Dict[str, Any]):
        score = relevance_by_id.get(meta.get("document_id"), {}).get("score", 0.0)
        ts = meta.get("updated_at") or datetime.min
        return (-score, -ts.timestamp() if isinstance(ts, datetime) else 0)

    metadata_docs.sort(key=_sort_key)

    entries: List[UnstructuredFileEntry] = []
    truncated: List[str] = []
    total_bytes = 0

    for meta in metadata_docs:
        doc_id = meta.get("document_id")
        file_doc = files_by_id.get(doc_id)
        if not file_doc:
            logger.warning(
                "unstructured_file_listing: orphan metadata for document_id=%s", doc_id,
            )
            continue
        s3_key = _resolve_s3_key(file_doc)
        if not s3_key:
            continue

        size = (
            file_doc.get("file_size_bytes")
            or file_doc.get("size")
            or file_doc.get("file_size")
            or 0
        )
        filename = meta.get("filename") or file_doc.get("filename") or "document"

        if len(entries) >= max_files or (size and total_bytes + size > max_total_bytes):
            truncated.append(filename)
            continue

        relevance = relevance_by_id.get(doc_id, {})
        entries.append(UnstructuredFileEntry(
            document_id=doc_id,
            filename=filename,
            s3_key=s3_key,
            file_type=meta.get("file_type", ""),
            summary=meta.get("summary", ""),
            doc_type=meta.get("doc_type", ""),
            semantic_tags=meta.get("semantic_tags", []) or [],
            key_entities=meta.get("key_entities", []) or [],
            folder_id=meta.get("folder_id"),
            file_size=size or None,
            text_length=meta.get("text_length", 0) or 0,
            relevance_score=float(relevance.get("score", 0.0)),
            relevance_reason=relevance.get("reason", "") or "",
        ))
        if size:
            total_bytes += size

    logger.info(
        "unstructured_file_listing: user=%s folders=%s available=%d included=%d truncated=%d bytes=%d",
        user_id[:8] if user_id else "?",
        folder_ids or "*",
        total_available,
        len(entries),
        len(truncated),
        total_bytes,
    )

    return {
        "entries": entries,
        "truncated_files": truncated,
        "total_available": total_available,
        "total_bytes": total_bytes,
    }


def format_unstructured_preview_for_prompt(
    entries: List[UnstructuredFileEntry],
    truncated_files: Optional[List[str]] = None,
) -> str:
    """
    Render a compact preview for the LLM: filename, doc_type, summary,
    tags, entities. Includes the sandbox path so the LLM can call
    ``execute_code`` to read / convert / extract from the file.
    """
    if not entries:
        return ""
    lines: List[str] = []
    lines.append("=== UNSTRUCTURED FILES MOUNTED AT /workspace/input/ ===")
    lines.append(
        "These files (PDF / DOCX / TXT / etc.) are available to the "
        "`execute_code` tool. Use pdfplumber / python-docx / open() in the "
        "sandbox to read or convert them. Do NOT guess content — read the "
        "file in code."
    )

    for i, e in enumerate(entries, start=1):
        lines.append("")
        lines.append(f"[{i}] {e.filename}")
        lines.append(f"    path: /workspace/input/{e.filename}")
        if e.doc_type:
            lines.append(f"    type: {e.doc_type}")
        if e.summary:
            lines.append(f"    summary: {e.summary}")
        if e.semantic_tags:
            lines.append(f"    tags: {', '.join(e.semantic_tags[:12])}")
        if e.key_entities:
            lines.append(f"    entities: {', '.join(e.key_entities[:12])}")
        if e.relevance_reason:
            lines.append(f"    matched because: {e.relevance_reason}")

    if truncated_files:
        lines.append("")
        lines.append(
            "NOTE: the following files were NOT mounted (file/size cap reached): "
            + ", ".join(truncated_files)
        )

    return "\n".join(lines)


def entries_to_sandbox_files(entries: List[UnstructuredFileEntry]) -> List[Dict[str, str]]:
    return [e.to_sandbox_file() for e in entries]


def format_unstructured_for_personal_data_tool(
    entries: List[UnstructuredFileEntry],
    truncated_files: Optional[List[str]] = None,
    *,
    max_results_per_call: int = 5,
) -> str:
    """
    Render an unstructured-file metadata block tailored for flows whose
    primary content-fetch path is ``personal_data_tool`` (NOT
    ``execute_code``). Used by presentation / printable / composer outline
    + per-page generation, where files live in the vault index (Milvus) and
    chunks are fetched on demand rather than mounted into a sandbox.

    The formatter emits filenames + summaries + tags + entities so the LLM
    can decide whether the user's goal matches any vault document, and
    nudges it to call ``personal_data_tool`` for those that match.
    """
    if not entries:
        return ""

    lines: List[str] = []
    lines.append("=== UNSTRUCTURED VAULT FILES (metadata only) ===")
    lines.append(
        "These PDF / DOCX / TXT files live in the user's vault index. The "
        "summaries and tags below are pre-computed. The full text is NOT "
        "loaded into this prompt. To pull passages, call "
        f"`personal_data_tool(query=..., max_results={max_results_per_call})` "
        "with a focused query for whichever file(s) match the user's goal. "
        "Do NOT call `execute_code` to read these files — chunks already "
        "live in Milvus and the vault tool returns reranked passages."
    )

    for i, e in enumerate(entries, start=1):
        lines.append("")
        lines.append(f"[{i}] {e.filename}")
        if e.doc_type:
            lines.append(f"    type: {e.doc_type}")
        if e.summary:
            lines.append(f"    summary: {e.summary}")
        if e.semantic_tags:
            lines.append(f"    tags: {', '.join(e.semantic_tags[:12])}")
        if e.key_entities:
            lines.append(f"    entities: {', '.join(e.key_entities[:12])}")
        if e.relevance_reason:
            lines.append(f"    matched because: {e.relevance_reason}")

    if truncated_files:
        lines.append("")
        lines.append(
            "NOTE: the following files matched the goal but were dropped for "
            "size: " + ", ".join(truncated_files)
        )

    lines.append("")
    lines.append(
        "ROUTING: If a goal / slide topic matches one of these files, your "
        "FIRST tool call should be `personal_data_tool` against that topic. "
        "If nothing here matches, do not call the tool — answer from "
        "training knowledge or whatever other context is provided."
    )

    return "\n".join(lines)


async def prefetch_unstructured_metadata_for_outline(
    user_id: str,
    folder_ids: Optional[List[str]],
    query: str,
    *,
    max_files: int = 10,
    max_results_per_call: int = 5,
) -> Optional[str]:
    """
    Fetch unstructured-file metadata relevant to ``query`` and return a
    prompt-ready block for outline / slide / page generators.

    The block lists each matching file's summary, tags, and entities so the
    LLM can decide whether to call ``personal_data_tool`` to pull chunks.

    Returns ``None`` if the user has no folders selected, no unstructured
    files in those folders, or none match the query.
    """
    if not folder_ids:
        return None

    try:
        listing = await list_unstructured_files(
            user_id=user_id,
            folder_ids=folder_ids,
            query=query,
            max_files=max_files,
        )
    except Exception:
        logger.exception("prefetch_unstructured_metadata_for_outline: listing failed")
        return None

    entries = listing.get("entries") or []
    if not entries:
        return None

    return format_unstructured_for_personal_data_tool(
        entries,
        truncated_files=listing.get("truncated_files"),
        max_results_per_call=max_results_per_call,
    )
