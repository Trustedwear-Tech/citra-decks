"""
Structured File Listing
=======================
Helper for the new (post-DuckDB, post-saas-collection) structured-data
pipeline. Replaces ``services/structured_data_retriever.py``.

Architecture
------------
We no longer embed CSV/Excel/JSON rows into Milvus or store them in the
``saas_records`` Mongo collection. Instead, every chat / chart / report flow
follows the quick_chat-style pattern:

1. List the structured files in scope (joining ``structured_file_metadata``
   with the ``files`` collection so we have ``s3_key`` for the sandbox).
2. Inject a compact **schema-only** preview into the LLM prompt — filename,
   row count, and each column's name/type/3 sample values.
3. Mount the raw file bytes into the sandbox (``execute_code`` tool) so the
   LLM can run pandas / openpyxl / json for any aggregation, FIFO, P&L, etc.

Limits
------
We cap the number of files / total bytes to keep the prompt small and the
sandbox transfer fast. Anything dropped is surfaced via ``truncated_files``
so the prompt can tell the LLM about it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Soft caps — tuned for a single chat turn / single LLM call. Configurable
# via env if real-world use exceeds these.
MAX_FILES = 5
MAX_TOTAL_BYTES = 50 * 1024 * 1024  # 50 MB

# Sample values per column to surface to the LLM (matches what
# document_manager._store_structured_file_metadata stores).
SAMPLES_PER_COLUMN = 3


def _resolve_s3_key(file_doc: Dict[str, Any]) -> Optional[str]:
    """
    Derive an S3 key from a row in the ``files`` collection.

    Historically the upload pipeline writes ``s3_url`` (full URL, env prefix
    already baked in) to ``files`` — see ``document_manager`` and
    ``api/chunked_documents``. Some legacy rows / quick-chat rows store
    ``s3_key`` directly. Accept either.
    """
    s3_key = file_doc.get("s3_key")
    if s3_key:
        return s3_key

    s3_url = file_doc.get("s3_url")
    if not s3_url:
        return None

    # Same parsing logic as api/chunked_documents.py::_generate_download_url.
    if ".amazonaws.com/" in s3_url:
        return s3_url.split(".amazonaws.com/", 1)[-1]
    if s3_url.startswith("s3://"):
        # s3://bucket/key/path -> key/path
        without_scheme = s3_url[len("s3://"):]
        return without_scheme.split("/", 1)[-1] if "/" in without_scheme else None
    return s3_url  # already a bare key


@dataclass
class StructuredFileEntry:
    """One structured file ready for prompt injection + sandbox mount."""

    document_id: str
    filename: str
    s3_key: str
    columns: List[Dict[str, Any]] = field(default_factory=list)
    total_rows: int = 0
    file_hash: Optional[str] = None
    folder_id: Optional[str] = None
    file_size: Optional[int] = None  # bytes, if known via files collection
    source_type: Optional[str] = None  # 'excel', 'csv', 'json'

    def to_sandbox_file(self) -> Dict[str, str]:
        """Shape consumed by ``services.code_executor`` / ``files_for_docker``."""
        return {"filename": self.filename, "s3_key": self.s3_key}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


async def list_structured_files(
    user_id: str,
    folder_ids: Optional[List[str]] = None,
    *,
    query: Optional[str] = None,
    attached_document_ids: Optional[List[str]] = None,
    max_files: int = MAX_FILES,
    max_total_bytes: int = MAX_TOTAL_BYTES,
) -> Dict[str, Any]:
    """
    Resolve every structured file (Excel/CSV/JSON) in ``folder_ids`` (or all
    of the user's vault if ``folder_ids`` is empty) and return a list ready
    for prompt injection + sandbox mount.

    Optional relevance gating
    -------------------------
    If ``attached_document_ids`` is provided, only those files are returned.
    Else if ``query`` is provided, the large-LLM relevance scorer is used
    to filter to files semantically matching the query. If neither is
    provided (legacy callers), behaviour is unchanged: every file is
    returned subject to the size/count caps.

    Returns
    -------
    dict with keys::

        {
            "entries":          List[StructuredFileEntry],   # within caps
            "truncated_files":  List[str],                   # filenames dropped
            "total_available":  int,                         # raw count before caps
            "total_bytes":      int,                         # bytes within caps
        }
    """
    if not user_id:
        return {"entries": [], "truncated_files": [], "total_available": 0, "total_bytes": 0}

    try:
        from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
    except ImportError:
        logger.exception("structured_file_listing: cannot import citra_mongo as mongodb_manager")
        return {"entries": [], "truncated_files": [], "total_available": 0, "total_bytes": 0}

    client = get_async_mongo_client()
    db = client[MONGODB_DATABASE]

    metadata_filter: Dict[str, Any] = {"user_id": user_id}
    if folder_ids:
        metadata_filter["folder_id"] = {"$in": folder_ids}

    try:
        cursor = db["structured_file_metadata"].find(metadata_filter)
        metadata_docs = await cursor.to_list(length=200)
    except Exception:
        logger.exception("structured_file_listing: metadata query failed")
        return {"entries": [], "truncated_files": [], "total_available": 0, "total_bytes": 0}

    if not metadata_docs:
        return {"entries": [], "truncated_files": [], "total_available": 0, "total_bytes": 0}

    total_available = len(metadata_docs)

    # ── Optional relevance gating ─────────────────────────────────────────
    # When the caller passes ``attached_document_ids`` or ``query``, narrow
    # the result set to only files actually relevant to this turn — avoids
    # context bloat. When neither is passed, behaviour is unchanged
    # (legacy callers still receive the full list).
    if attached_document_ids:
        wanted = set(attached_document_ids)
        metadata_docs = [m for m in metadata_docs if m.get("document_id") in wanted]
    elif query:
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
                    file_type=m.get("source_type", ""),
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
                kept = {s.document_id for s in scored}
                metadata_docs = [m for m in metadata_docs if m.get("document_id") in kept]
                logger.info(
                    "structured_file_listing: relevance gating kept %d/%d files",
                    len(metadata_docs), total_available,
                )
            except ScorerUnavailable as e:
                # Scorer unreachable — fall back to most-recent files so the
                # user's structured data is still mounted into the sandbox.
                # MAX_FILES + MAX_TOTAL_BYTES below cap the prompt size.
                logger.warning(
                    "structured_file_listing: scorer unavailable (%s); falling back to recency",
                    e,
                )
                metadata_docs.sort(
                    key=lambda m: m.get("updated_at") or m.get("created_at") or 0,
                    reverse=True,
                )
                metadata_docs = metadata_docs[:max_files]
        except Exception:
            logger.exception("structured_file_listing: relevance gating failed (using full list)")

    if not metadata_docs:
        return {"entries": [], "truncated_files": [], "total_available": total_available, "total_bytes": 0}

    document_ids = [m.get("document_id") for m in metadata_docs if m.get("document_id")]
    if not document_ids:
        return {"entries": [], "truncated_files": [], "total_available": 0, "total_bytes": 0}

    # Resolve s3 location + size from the files collection.
    # NOTE: the ``files`` collection stores ``s3_url`` (full URL, includes the
    # env prefix) and ``file_size_bytes`` — NOT ``s3_key`` / ``size``. We derive
    # the s3 key from the URL the same way ``api/chunked_documents`` does.
    try:
        files_cursor = db["files"].find(
            {"_id": {"$in": document_ids}},
            {
                "_id": 1,
                "s3_url": 1,
                "s3_key": 1,  # tolerate legacy rows
                "file_size_bytes": 1,
                "size": 1,
                "file_size": 1,
                "filename": 1,
            },
        )
        files_docs = await files_cursor.to_list(length=len(document_ids))
    except Exception:
        logger.exception("structured_file_listing: files lookup failed")
        files_docs = []

    files_by_id = {f.get("_id"): f for f in files_docs}

    entries: List[StructuredFileEntry] = []
    truncated: List[str] = []
    total_bytes = 0
    orphans_skipped = 0
    missing_key_skipped = 0

    for meta in metadata_docs:
        doc_id = meta.get("document_id")
        file_doc = files_by_id.get(doc_id)
        if not file_doc:
            # Metadata exists but no row in the ``files`` collection — usually
            # a stale row left behind by an incomplete delete. Surface this so
            # ops can clean it up; do NOT silently treat it as success.
            orphans_skipped += 1
            logger.warning(
                "structured_file_listing: orphan metadata for document_id=%s user=%s "
                "(no row in files collection)",
                doc_id,
                user_id[:8] if user_id else "?",
            )
            continue

        s3_key = _resolve_s3_key(file_doc)
        if not s3_key:
            missing_key_skipped += 1
            logger.warning(
                "structured_file_listing: files row for document_id=%s has no s3_url/s3_key",
                doc_id,
            )
            continue

        size = (
            file_doc.get("file_size_bytes")
            or file_doc.get("size")
            or file_doc.get("file_size")
            or 0
        )
        filename = meta.get("filename") or file_doc.get("filename") or "structured_file"

        if len(entries) >= max_files or (size and total_bytes + size > max_total_bytes):
            truncated.append(filename)
            continue

        entries.append(StructuredFileEntry(
            document_id=doc_id,
            filename=filename,
            s3_key=s3_key,
            columns=meta.get("columns", []) or [],
            total_rows=meta.get("total_rows", 0) or 0,
            file_hash=meta.get("file_hash"),
            folder_id=meta.get("folder_id"),
            file_size=size or None,
            source_type=meta.get("source_type"),
        ))
        if size:
            total_bytes += size

    logger.info(
        "structured_file_listing: user=%s folders=%s available=%d included=%d "
        "truncated=%d orphans=%d missing_key=%d bytes=%d",
        user_id[:8] if user_id else "?",
        folder_ids or "*",
        len(metadata_docs),
        len(entries),
        len(truncated),
        orphans_skipped,
        missing_key_skipped,
        total_bytes,
    )

    return {
        "entries": entries,
        "truncated_files": truncated,
        "total_available": total_available,
        "total_bytes": total_bytes,
    }


def format_schema_preview_for_prompt(
    entries: List[StructuredFileEntry],
    truncated_files: Optional[List[str]] = None,
) -> str:
    """
    Render a compact schema preview for the LLM. No row data — just the
    schema + 3 sample values per column. The LLM is expected to call the
    ``execute_code`` tool to compute against the mounted files.
    """
    if not entries:
        return ""

    lines: List[str] = []
    lines.append("=== STRUCTURED FILES MOUNTED AT /workspace/input/ ===")
    lines.append(
        "These files are available to the `execute_code` tool. Read them with "
        "pandas/openpyxl/json from the paths shown. Do NOT guess values — run "
        "code to compute aggregates, filters, FIFO, P&L, etc."
    )

    for i, entry in enumerate(entries, start=1):
        lines.append("")
        lines.append(f"[{i}] {entry.filename}")
        lines.append(f"    path: /workspace/input/{entry.filename}")
        if entry.total_rows:
            lines.append(f"    rows: {entry.total_rows}")
        if entry.source_type:
            lines.append(f"    type: {entry.source_type}")

        # LLM-generated metadata from upload-time enrichment (mirrors the
        # unstructured preview). Gives the chat LLM enough signal to decide
        # whether to invoke execute_code on this file before scanning columns.
        if getattr(entry, "doc_type", ""):
            lines.append(f"    doc_type: {entry.doc_type}")
        if getattr(entry, "summary", ""):
            lines.append(f"    summary: {entry.summary}")
        if getattr(entry, "semantic_tags", None):
            lines.append(f"    tags: {', '.join(entry.semantic_tags[:12])}")
        if getattr(entry, "key_entities", None):
            lines.append(f"    entities: {', '.join(entry.key_entities[:12])}")

        if entry.columns:
            lines.append("    columns:")
            for col in entry.columns:
                name = col.get("name", "?")
                col_type = col.get("type", "?")
                samples = col.get("samples", [])[:SAMPLES_PER_COLUMN]
                sample_str = ", ".join(repr(s) for s in samples) if samples else "—"
                lines.append(f"      • {name} ({col_type}) e.g. {sample_str}")

    if truncated_files:
        lines.append("")
        lines.append(
            "NOTE: the following files were NOT mounted (file/size cap reached): "
            + ", ".join(truncated_files)
        )

    return "\n".join(lines)


def entries_to_sandbox_files(entries: List[StructuredFileEntry]) -> List[Dict[str, str]]:
    """Convenience: shape consumed by ``services.code_executor.execute_code``."""
    return [e.to_sandbox_file() for e in entries]
