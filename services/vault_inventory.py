# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""
Vault Inventory — agentic, pre-filter-free vault file access.
====================================================================

Pure-agentic main chat does NOT pre-fetch or LLM-pre-filter the user's files.
The kickstart prompt only hands the agent a POINTER ("you have N vault files —
look them up"), and the chat LLM decides what to look at via tools:

  • count_vault_files()  — cheap count for the kickstart pointer (no listing, no LLM)
  • list_vault_files()   — the agent's discovery tool: full inventory, NO scorer
  • resolve_vault_files()— filename → s3_key, so execute_code can mount on demand

Contrast with services/file_relevance_scorer.py + SaaSDataTool, which ran an LLM
to PICK files during prefetch. Here there is no scorer and no prefetch — the
agent searches what it needs.

Folder scope is bound by the caller (the request's selected_folder_ids); the
LLM cannot widen it.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_STRUCTURED_COLL = "structured_file_metadata"
_UNSTRUCTURED_COLL = "unstructured_file_metadata"

# Cap how many files we enumerate to the LLM in one listing call (token budget).
# If a user has more, the agent narrows with the optional `query` substring or by
# selecting folders. Surfaced via `truncated` so nothing is hidden silently.
_MAX_LIST = 60


def _db():
    from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
    return get_async_mongo_client()[MONGODB_DATABASE]


def _scope_filter(user_id: str, folder_ids: Optional[List[str]]) -> Dict[str, Any]:
    f: Dict[str, Any] = {"user_id": user_id}
    if folder_ids:
        f["folder_id"] = {"$in": folder_ids}
    return f


async def count_vault_files(user_id: str, folder_ids: Optional[List[str]] = None) -> Dict[str, int]:
    """Cheap count for the kickstart pointer. Two indexed count_documents — no
    document fetch, no LLM. Returns {structured, unstructured, total}."""
    if not user_id:
        return {"structured": 0, "unstructured": 0, "total": 0}
    try:
        db = _db()
        flt = _scope_filter(user_id, folder_ids)
        structured = await db[_STRUCTURED_COLL].count_documents(flt)
        unstructured = await db[_UNSTRUCTURED_COLL].count_documents(flt)
        return {"structured": int(structured), "unstructured": int(unstructured),
                "total": int(structured) + int(unstructured)}
    except Exception as exc:  # noqa: BLE001 — never block the stream on a count
        logger.warning(f"[VAULT_INVENTORY] count failed (non-fatal): {exc}")
        return {"structured": 0, "unstructured": 0, "total": 0}


def _column_names(doc: Dict[str, Any]) -> List[str]:
    cols = doc.get("columns") or doc.get("schema") or []
    out: List[str] = []
    for c in cols:
        if isinstance(c, dict):
            n = c.get("name") or c.get("column")
            if n:
                out.append(str(n))
        elif isinstance(c, str):
            out.append(c)
    return out[:40]


async def list_vault_files(
    user_id: str,
    folder_ids: Optional[List[str]] = None,
    kind: Optional[str] = None,          # 'structured' | 'unstructured' | None (both)
    query: Optional[str] = None,         # optional cheap substring filter (NOT an LLM scorer)
) -> Dict[str, Any]:
    """The agent's discovery primitive. Returns the inventory the agent reasons
    over to decide what to fetch. NO LLM scoring — the full list (within a cap),
    optionally narrowed by a literal substring match on filename/summary/tags."""
    if not user_id:
        return {"structured": [], "unstructured": [], "truncated": False, "total": 0}

    q = (query or "").strip().lower()

    def _match(doc: Dict[str, Any]) -> bool:
        if not q:
            return True
        hay = " ".join([
            str(doc.get("filename", "")),
            str(doc.get("summary", "")),
            " ".join(str(t) for t in (doc.get("semantic_tags") or [])),
        ]).lower()
        return q in hay

    try:
        db = _db()
        flt = _scope_filter(user_id, folder_ids)
        structured: List[Dict[str, Any]] = []
        unstructured: List[Dict[str, Any]] = []
        truncated = False

        if kind in (None, "structured"):
            docs = await db[_STRUCTURED_COLL].find(flt).to_list(length=200)
            picked = [d for d in docs if _match(d)]
            if len(picked) > _MAX_LIST:
                truncated = True
                picked = picked[:_MAX_LIST]
            for d in picked:
                structured.append({
                    "filename": d.get("filename"),
                    "kind": "structured",
                    "rows": d.get("total_rows"),
                    "columns": _column_names(d),
                    "summary": (d.get("summary") or "")[:300],
                })

        if kind in (None, "unstructured"):
            docs = await db[_UNSTRUCTURED_COLL].find(flt).to_list(length=200)
            picked = [d for d in docs if _match(d)]
            if len(picked) > _MAX_LIST:
                truncated = True
                picked = picked[:_MAX_LIST]
            for d in picked:
                unstructured.append({
                    "filename": d.get("filename"),
                    "kind": "unstructured",
                    "doc_type": d.get("doc_type") or d.get("file_type"),
                    "summary": (d.get("summary") or "")[:300],
                    "tags": (d.get("semantic_tags") or [])[:8],
                })

        return {
            "structured": structured,
            "unstructured": unstructured,
            "truncated": truncated,
            "total": len(structured) + len(unstructured),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[VAULT_INVENTORY] list failed: {exc}")
        return {"structured": [], "unstructured": [], "truncated": False, "total": 0,
                "error": str(exc)}


async def resolve_vault_files(
    user_id: str,
    folder_ids: Optional[List[str]],
    filenames: List[str],
) -> List[Dict[str, str]]:
    """Map agent-supplied filenames → ``{filename, s3_key}`` for sandbox mount.
    Looks ONLY in the user's scoped vault (structured files — those are the ones
    execute_code reads). Unknown names are skipped (the agent gets told which
    mounted via the execute_code result)."""
    if not user_id or not filenames:
        return []
    wanted = {str(f).strip() for f in filenames if str(f).strip()}
    if not wanted:
        return []
    try:
        from services.structured_file_listing import _resolve_s3_key
    except Exception:  # noqa: BLE001
        def _resolve_s3_key(d):  # minimal fallback mirroring the real resolver
            return d.get("s3_key") or d.get("s3_url")

    out: List[Dict[str, str]] = []
    seen: set = set()
    try:
        db = _db()
        flt = _scope_filter(user_id, folder_ids)
        flt["filename"] = {"$in": list(wanted)}
        metas = await db[_STRUCTURED_COLL].find(flt).to_list(length=200)
        # s3_key lives on the `files` collection, joined by files._id ==
        # metadata.document_id (same join as structured_file_listing). The
        # metadata doc itself does NOT carry s3_key.
        doc_ids = [m.get("document_id") for m in metas if m.get("document_id")]
        files_by_id: Dict[Any, Dict[str, Any]] = {}
        if doc_ids:
            files_docs = await db["files"].find(
                {"_id": {"$in": doc_ids}},
                {"_id": 1, "s3_url": 1, "s3_key": 1, "filename": 1},
            ).to_list(length=len(doc_ids))
            files_by_id = {f.get("_id"): f for f in files_docs}
        for m in metas:
            fname = m.get("filename")
            if not fname or fname in seen:
                continue
            fdoc = files_by_id.get(m.get("document_id"))
            if not fdoc:
                continue
            s3_key = _resolve_s3_key(fdoc)
            if s3_key:
                out.append({"filename": fname, "s3_key": s3_key})
                seen.add(fname)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[VAULT_INVENTORY] resolve failed: {exc}")
    return out


def build_list_vault_files_tool_schema() -> Dict[str, Any]:
    """OpenAI tool schema for the agent's vault discovery primitive."""
    return {
        "type": "function",
        "function": {
            "name": "list_vault_files",
            "description": (
                "List the user's personal vault files so you can decide what to look at. "
                "Returns structured files (CSV/Excel/JSON — with row count + column names) "
                "and unstructured files (PDF/DOCX/TXT — with a short summary + tags). "
                "Call this FIRST when the user's question might be answered from their own "
                "documents and you don't yet know which files exist. Then: read passages from "
                "unstructured files with personal_data_tool, and compute on structured files "
                "with execute_code(input_files=[…the exact filenames…]). Optional `query` does a "
                "literal substring narrow (not a semantic filter); omit it to see everything."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional literal substring to narrow filenames/summaries/tags.",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["structured", "unstructured"],
                        "description": "Optional — limit to one kind. Omit for both.",
                    },
                },
                "required": [],
            },
        },
    }
