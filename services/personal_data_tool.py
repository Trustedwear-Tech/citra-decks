# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""
personal_data_tool.py
=====================
Personal-vault retrieval as an LLM-callable tool — symmetric with the
`dept_*` enterprise MCP tools.

Why this exists
---------------
Main chat used to PRE-FETCH Milvus chunks for every turn (orchestrator
ran simplified_planner → source_provider → context_merger before the LLM
saw the question). That stuffed irrelevant chunks into many turns and
added latency to non-RAG turns ("hi", code questions, etc.).

After this refactor, personal vault retrieval is a TOOL the chat LLM
calls only when it needs vault context. The orchestrator now pre-fetches
only the file-listing metadata (small, ~500 tokens) so the LLM knows
what files are available; it then calls `personal_data_tool` to actually
fetch chunks.

Public API
----------
- ``build_personal_data_tool_schema(folder_ids, has_file_metadata)`` →
  the OpenAI tool schema. Folder scope is bound at registration time;
  the LLM doesn't pass ``folder_ids`` itself.

- ``dispatch_personal_data_tool(args, *, user_id, user_email, folder_ids)`` →
  executes the underlying Milvus retrieval (with optional sub-query
  expansion via the simplified planner), returns a compact dict the LLM
  can read inside its tool-call loop.

Folder scoping rules (per the user's spec)
------------------------------------------
- Tool is registered ONLY when ``use_personal_data`` is True.
- ``folder_ids`` from the UI is bound at registration time and ALWAYS
  forwarded to the dispatcher; the LLM cannot widen the scope.
- ``folder_search_enabled`` is implicitly True whenever folder_ids is
  non-empty (matches the orchestrator's old behaviour).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Limits ─────────────────────────────────────────────────────────────────
MAX_RESULTS_PER_CALL = int(os.getenv("PERSONAL_TOOL_MAX_RESULTS_PER_CALL", "30"))
DEFAULT_RESULTS_PER_CALL = int(os.getenv("PERSONAL_TOOL_DEFAULT_RESULTS_PER_CALL", "15"))
MAX_TEXT_CHARS = int(os.getenv("PERSONAL_TOOL_MAX_TEXT_CHARS", "1200"))

# When True, expand the LLM's single query into 2-5 sub-queries via the
# simplified planner, fan out to Milvus per sub-query, then dedupe + cap.
# DEFAULT OFF in the agentic system: the chat LLM already crafts the query when
# it calls this tool (and can call it again with a sharper query), so a planner
# LLM round-trip per vault call just adds latency. Set the env to "true" to
# re-enable multi-query recall expansion if needed.
USE_SUBQUERY_EXPANSION = os.getenv("PERSONAL_TOOL_SUBQUERY_EXPANSION", "false").lower() == "true"


TOOL_NAME = "personal_data_tool"


# ───────────────────────────────────────────────────────────────────────────
# Schema builder
# ───────────────────────────────────────────────────────────────────────────

def build_personal_data_tool_schema(
    *,
    folder_ids: Optional[List[str]] = None,
    has_file_metadata: bool = False,
    max_results_cap: Optional[int] = None,
) -> Dict[str, Any]:
    """Return one OpenAI function-calling schema for the personal-vault tool.

    The LLM sees a single tool that fetches relevant chunks from the user's
    selected vault folders. It can NOT pick a different folder scope —
    the dispatcher binds ``folder_ids`` from the request scope.

    Parameters
    ----------
    folder_ids : list[str]
        UI-selected folder IDs that scope this conversation. Surfaced in
        the tool description so the LLM knows the search is scoped.
    has_file_metadata : bool
        When True, the system prompt has already told the LLM about the
        files in scope (filenames, summaries). The tool description nudges
        the LLM to first try answering from that listing before retrieving.
    max_results_cap : int, optional
        Per-feature override of the global ``MAX_RESULTS_PER_CALL``. Used by
        composer/presentation/printable to tighten the budget (e.g. 5 for
        outlines/sections, 3 for per-slide/per-page). Falls back to the
        global cap when None.
    """
    effective_cap = max(1, min(int(max_results_cap or MAX_RESULTS_PER_CALL), MAX_RESULTS_PER_CALL))
    effective_default = min(DEFAULT_RESULTS_PER_CALL, effective_cap)

    folder_scope_text = (
        f"scoped to {len(folder_ids)} selected folder(s)"
        if folder_ids
        else "across the user's full vault"
    )
    metadata_note = (
        " The system prompt already lists the available files (filenames, "
        "summaries, schemas). Use this tool when you need the actual passages, "
        "rows, or facts from those files — not when the listing alone answers "
        "the user."
        if has_file_metadata
        else ""
    )
    description = (
        f"Search the user's personal vault (uploaded documents, notes, "
        f"private files) for chunks relevant to a query. Retrieval is "
        f"semantic (embedding cosine), {folder_scope_text}.{metadata_note} "
        f"Returns up to {effective_cap} reranked chunks with text + "
        f"document_id + score. For STRUCTURED files (CSV/Excel/JSON) "
        f"prefer `execute_code` instead — this tool returns only sample "
        f"rows for those."
    )

    return {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Natural-language search query for the vault. Pass "
                            "the user's question (or a focused sub-question) "
                            "verbatim; the retriever will rank semantically. "
                            "For broad multi-topic questions, call this tool "
                            "multiple times with focused sub-queries instead "
                            "of one fuzzy query."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": (
                            f"Number of chunks to return (default "
                            f"{effective_default}, max {effective_cap})."
                        ),
                        "minimum": 1,
                        "maximum": effective_cap,
                    },
                    "document_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional: restrict search to specific document "
                            "IDs from the file listing in the system prompt. "
                            "Use this when the user references a specific "
                            "file."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    }


# ───────────────────────────────────────────────────────────────────────────
# Dispatcher
# ───────────────────────────────────────────────────────────────────────────

def _truncate_text(text: Any, limit: int = MAX_TEXT_CHARS) -> str:
    if text is None:
        return ""
    s = str(text)
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _shape_chunk(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Compress a Milvus chunk dict into something LLM-friendly."""
    out: Dict[str, Any] = {
        "text": _truncate_text(raw.get("text", "")),
        "score": raw.get("score"),
    }
    md = raw.get("metadata") or {}
    if isinstance(md, dict) and md:
        compact_md: Dict[str, Any] = {}
        for k, v in md.items():
            if k in ("dense_vector", "sparse_vector", "embedding"):
                continue
            if isinstance(v, (str, int, float, bool)) or v is None:
                if isinstance(v, str) and len(v) > 200:
                    compact_md[k] = v[:199] + "…"
                else:
                    compact_md[k] = v
            elif isinstance(v, (list, tuple)) and len(v) <= 10:
                compact_md[k] = list(v)[:10]
        if compact_md:
            out["metadata"] = compact_md
    # Lift document_id to top level for easy LLM citation
    if md.get("document_id"):
        out["document_id"] = md["document_id"]
    if md.get("filename") or md.get("display_name"):
        out["filename"] = md.get("filename") or md.get("display_name")
    return out


async def _expand_subqueries(
    query: str,
    user_persona: Optional[Dict[str, Any]] = None,
    *,
    enabled: Optional[bool] = None,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
) -> List[str]:
    """Use the simplified planner to expand one query into focused sub-queries.

    Returns at least [query]. Failures fall back to [query]. ``enabled``
    overrides ``USE_SUBQUERY_EXPANSION`` per call (used by lite-mode callers
    like per-slide / per-page generation that want plain Milvus top-k).
    """
    if enabled is False or (enabled is None and not USE_SUBQUERY_EXPANSION):
        return [query]
    try:
        from agentic_rag.simplified_planner import SimplifiedStrategyPlanner
        planner = SimplifiedStrategyPlanner()
        intent = await planner.analyze_and_generate_subqueries(
            query=query,
            user_persona=user_persona or {},
            user_id=user_id,
            user_email=user_email,
        )
        sub_qs = [sq.query_text for sq in (intent.sub_queries or []) if getattr(sq, "query_text", "").strip()]
        if not sub_qs:
            return [query]
        # Always include the original query as a safety net at the front
        if query not in sub_qs:
            sub_qs.insert(0, query)
        return sub_qs[:5]  # cap to avoid runaway fan-out
    except Exception as exc:
        logger.debug(f"[PERSONAL_TOOL] sub-query expansion failed ({exc}); using original query")
        return [query]


async def dispatch_personal_data_tool(
    *,
    args: Dict[str, Any],
    user_id: str,
    user_email: Optional[str] = None,
    folder_ids: Optional[List[str]] = None,
    persona_data: Optional[Dict[str, Any]] = None,
    max_results_cap: Optional[int] = None,
    lite: bool = False,
    expand_subqueries: bool = True,
    precomputed_embedding: Optional[List[float]] = None,
    adaptive_threshold: bool = False,
    adaptive_floor: int = 5,
) -> Dict[str, Any]:
    """Execute one ``personal_data_tool`` call.

    Always returns a dict; never raises. Errors come back as
    ``{"success": False, "error": "..."}`` so the LLM can recover.

    Folder scope is taken from the ``folder_ids`` keyword arg (bound by the
    caller from the request scope) — NOT from ``args`` — so the LLM can't
    widen the scope.

    ``max_results_cap`` lets the caller (composer/presentation/printable)
    enforce a tighter per-call budget than the global default. The LLM
    cannot exceed this cap even if it passes a higher ``max_results``.

    ``lite`` skips sub-query expansion (saves an LLM call) and the
    cross-encoder reranker (saves the reranker HTTP round-trip). Used by
    per-slide / per-page / per-section flows where the query is already
    focused and the agentic tool-loop would otherwise add 15–35 s of
    avoidable latency. Outline / chat paths leave ``lite=False`` so they
    keep planner + reranker quality.

    ``expand_subqueries`` is a finer-grained knob: setting it to False
    disables ONLY the planner sub-query expansion (one fewer LLM call and
    fewer embedding fan-out calls) while preserving the cross-encoder
    reranker. Used by presentation / printable / report-composer paths
    where the LLM-driven query is already specific and fan-out just
    multiplies embedding/Milvus/rerank round-trips against the same doc.
    """
    if not user_id:
        return {"success": False, "error": "Missing user_id."}

    query = (args or {}).get("query", "")
    if not isinstance(query, str) or not query.strip():
        return {"success": False, "error": "Missing or empty 'query' argument."}
    query = query.strip()

    effective_cap = max(1, min(int(max_results_cap or MAX_RESULTS_PER_CALL), MAX_RESULTS_PER_CALL))
    effective_default = min(DEFAULT_RESULTS_PER_CALL, effective_cap)
    try:
        max_results = int((args or {}).get("max_results") or effective_default)
    except (TypeError, ValueError):
        max_results = effective_default
    max_results = max(1, min(max_results, effective_cap))

    document_ids = (args or {}).get("document_ids") or []
    if not isinstance(document_ids, list):
        document_ids = []

    folder_search_enabled = bool(folder_ids)

    # 1. Sub-query expansion (optional, internal). Falls back to [query].
    #    Disabled when lite=True (per-slide/page/section flows) OR when the
    #    caller explicitly sets expand_subqueries=False (presentation /
    #    printable / report-composer agentic loops — the LLM-driven query
    #    is already focused and fan-out just multiplies embedding/Milvus
    #    /rerank round-trips against the same doc).
    sq_enabled: Optional[bool] = None
    if lite or not expand_subqueries:
        sq_enabled = False
    sub_queries = await _expand_subqueries(
        query,
        user_persona=persona_data,
        enabled=sq_enabled,
        user_id=user_id,
        user_email=user_email,
    )
    logger.info(
        f"🔍 [PERSONAL_TOOL] user={user_id} folders={folder_ids} "
        f"max={max_results} subqueries={len(sub_queries)} doc_ids={len(document_ids)} "
        f"lite={lite} expand_subqueries={expand_subqueries}"
    )

    # 2. Fan out to Milvus per sub-query, gather, dedupe, cap.
    try:
        from agentic_rag.tools import RETRIEVAL_TOOLS
        personal_tool = RETRIEVAL_TOOLS.get("personal")
        if personal_tool is None:
            return {"success": False, "error": "Personal retrieval tool unavailable."}
    except Exception as exc:
        logger.error(f"❌ [PERSONAL_TOOL] Could not load PersonalDataTool: {exc}")
        return {"success": False, "error": "Personal retrieval unavailable."}

    # Heuristic: per-subquery cap so total chunks stays under ~max_results × 1.5
    # (we then dedupe and trim to max_results below).
    per_sq_cap = max(5, (max_results * 2) // max(1, len(sub_queries)))

    all_chunks: List[Dict[str, Any]] = []
    seen_ids: set = set()
    # Precomputed embedding only applies when sub-query expansion is disabled
    # (single sub_query == original query). Multi-subquery fan-out re-embeds
    # each expanded variant via the usual path.
    _sq_precomputed_embedding = precomputed_embedding if len(sub_queries) == 1 else None
    try:
        for sq in sub_queries:
            sq_chunks = await personal_tool.retrieve(
                query=sq,
                user_id=user_id,
                max_results=per_sq_cap,
                selected_folder_ids=folder_ids or [],
                folder_search_enabled=folder_search_enabled,
                user_email=user_email,
                skip_rerank=lite,
                precomputed_embedding=_sq_precomputed_embedding,
                adaptive_threshold=adaptive_threshold,
                adaptive_floor=adaptive_floor,
            )
            for c in (sq_chunks or []):
                if not isinstance(c, dict):
                    continue
                # Dedupe by chunk id when present, else by (document_id, text-hash)
                md = c.get("metadata") or {}
                chunk_id = md.get("chunk_id") or md.get("vector_id") or md.get("id")
                if not chunk_id:
                    chunk_id = (md.get("document_id"), hash((c.get("text") or "")[:200]))
                if chunk_id in seen_ids:
                    continue
                seen_ids.add(chunk_id)
                # If document_ids filter requested, drop non-matching chunks
                if document_ids and md.get("document_id") not in document_ids:
                    continue
                all_chunks.append(c)
    except Exception as exc:
        logger.error(f"❌ [PERSONAL_TOOL] Milvus fan-out failed: {exc}")
        return {"success": False, "error": f"Retrieval failed: {exc}"}

    # 3. Sort by score desc, cap at max_results, shape for LLM
    try:
        all_chunks.sort(key=lambda c: float(c.get("score") or 0.0), reverse=True)
    except Exception:
        pass
    sliced = all_chunks[:max_results]
    shaped = [_shape_chunk(c) for c in sliced]
    total = len(all_chunks)
    truncated = total > max_results

    logger.info(
        f"✅ [PERSONAL_TOOL] returned {len(shaped)}/{total} chunks "
        f"(query='{query[:80]}', folders={folder_ids})"
    )

    return {
        "success": True,
        "query": query,
        "sub_queries_used": sub_queries if len(sub_queries) > 1 else None,
        "folder_scope": folder_ids or [],
        "results": shaped,
        "total": total,
        "returned": len(shaped),
        "truncated": truncated,
    }


async def retrieve_vault_context_for_prompt(
    *,
    query: str,
    user_id: str,
    user_email: Optional[str] = None,
    folder_ids: Optional[List[str]] = None,
    document_ids: Optional[List[str]] = None,
    max_results: int = 3,
    log_prefix: str = "VAULT_LITE",
    precomputed_embedding: Optional[List[float]] = None,
    adaptive_threshold: bool = False,
    adaptive_floor: int = 5,
) -> str:
    """Lite vault retrieval used by per-slide / per-page / per-section flows.

    Bypasses the agentic tool-loop entirely: a single Milvus top-k query
    (no sub-query expansion, no reranker) → formatted prompt block. Caller
    pastes the returned string into the user prompt and calls the LLM once
    for content synthesis. This recovers the pre-refactor 1-RTT latency
    shape while keeping the rest of the system on the agentic-tool design
    where it matters (outline planning, chat).

    Returns ``""`` (empty string) when ``folder_ids`` is empty, the user
    has no matching chunks, or retrieval fails. Callers concatenate the
    return value into the prompt unconditionally — an empty string is a
    no-op, so no caller-side branching is required.
    """
    if not user_id or not folder_ids or not query or not query.strip():
        return ""

    args: Dict[str, Any] = {"query": query.strip(), "max_results": max_results}
    if document_ids:
        args["document_ids"] = list(document_ids)

    try:
        result = await dispatch_personal_data_tool(
            args=args,
            user_id=user_id,
            user_email=user_email,
            folder_ids=folder_ids,
            max_results_cap=max_results,
            lite=True,
            precomputed_embedding=precomputed_embedding,
            adaptive_threshold=adaptive_threshold,
            adaptive_floor=adaptive_floor,
        )
    except Exception as exc:
        logger.warning(f"❌ [{log_prefix}] retrieve_vault_context_for_prompt failed: {exc}")
        return ""

    if not result.get("success"):
        return ""
    chunks = result.get("results") or []
    if not chunks:
        return ""

    lines: List[str] = []
    lines.append(
        f"=== VAULT PASSAGES (top {len(chunks)} from your selected folder(s), "
        f"retrieved for: \"{query.strip()[:120]}\") ==="
    )
    for i, c in enumerate(chunks, start=1):
        filename = c.get("filename") or ""
        text = (c.get("text") or "").strip()
        header_bits: List[str] = [f"[{i}]"]
        if filename:
            header_bits.append(filename)
        lines.append("")
        lines.append(" ".join(header_bits))
        if text:
            lines.append(text)
    lines.append("")
    lines.append("=== END VAULT PASSAGES ===")
    lines.append(
        "GROUNDING: Use these passages as the source of truth for facts, "
        "names, figures, and quotes. If a needed fact is not in these passages, "
        "do not invent — describe qualitatively or omit. "
        "DO NOT include any citation markers, doc IDs, or bracketed references "
        "(e.g. [vault:...], [doc:...], [source:...]) in the rendered output — "
        "these passages are for grounding only, not for display."
    )
    logger.info(
        f"📥 [{log_prefix}] injected {len(chunks)} vault chunks "
        f"({sum(len(c.get('text') or '') for c in chunks)} chars) "
        f"for query='{query.strip()[:80]}'"
    )
    return "\n".join(lines)


async def retrieve_vault_contexts_batch(
    *,
    queries: List[str],
    user_id: str,
    user_email: Optional[str] = None,
    folder_ids: Optional[List[str]] = None,
    document_ids: Optional[List[str]] = None,
    max_results: int = 3,
    log_prefix: str = "VAULT_BATCH",
) -> List[str]:
    """Batch variant of ``retrieve_vault_context_for_prompt``.

    Embeds every query in a SINGLE OpenAI ``/embeddings`` call (eliminating
    the N concurrent calls + rate-limit retries we'd otherwise pay during
    deck/document generation), then runs the per-query Milvus + Mongo
    retrieval in parallel. Returns one formatted vault block per input
    query, in the same order. Empty queries / missing folders / fetch
    failures return ``""`` for that slot so callers can index by position.

    Per-slide/per-page generation endpoints accept the returned block via
    a ``prefetched_vault_block`` field on their request body and skip
    their own vault lookup when it is supplied.
    """
    if not user_id or not folder_ids or not queries:
        return ["" for _ in queries]

    cleaned: List[str] = [(q or "").strip() for q in queries]
    nonempty_idx = [i for i, q in enumerate(cleaned) if q]
    if not nonempty_idx:
        return ["" for _ in queries]

    # 1. ONE embed call for all non-empty queries.
    try:
        from utils import embed_texts_batch
        nonempty_queries = [cleaned[i] for i in nonempty_idx]
        embeddings = await embed_texts_batch(nonempty_queries)
    except Exception as exc:
        logger.warning(
            f"⚠️ [{log_prefix}] batch embed failed ({exc}); falling back to per-query path"
        )
        embeddings = [None] * len(nonempty_idx)  # type: ignore[list-item]

    if len(embeddings) != len(nonempty_idx):
        logger.warning(
            f"⚠️ [{log_prefix}] batch embed returned {len(embeddings)} vectors "
            f"for {len(nonempty_idx)} queries — falling back to per-query path"
        )
        embeddings = [None] * len(nonempty_idx)  # type: ignore[list-item]

    # 2. Track aggregate embedding usage once for the whole batch (the
    #    per-query path's tracker is now skipped because we pass
    #    precomputed embeddings downstream).
    if user_email:
        try:
            from middleware.credit_check_middleware import get_usage_service
            usage_service = get_usage_service()
            total_chars = sum(len(q) for q in nonempty_queries)
            usage_service.track_embedding_usage(
                user_id=user_id,
                email=user_email,
                total_characters=total_chars,
            )
        except Exception as track_exc:  # noqa: BLE001 — never block retrieval on tracking
            logger.warning(f"⚠️ [{log_prefix}] usage tracking failed: {track_exc}")

    # 3. Parallel per-query retrieval (Milvus + Mongo), each using its
    #    precomputed vector so no further /embeddings RTT happens.
    async def _one(idx_in_nonempty: int, original_idx: int) -> str:
        try:
            return await retrieve_vault_context_for_prompt(
                query=cleaned[original_idx],
                user_id=user_id,
                user_email=None,  # tracking already handled above
                folder_ids=folder_ids,
                document_ids=document_ids,
                max_results=max_results,
                log_prefix=log_prefix,
                precomputed_embedding=embeddings[idx_in_nonempty],
            )
        except Exception as exc:  # noqa: BLE001 — partial failure shouldn't poison the whole batch
            logger.warning(
                f"⚠️ [{log_prefix}] per-query retrieval failed (idx={original_idx}): {exc}"
            )
            return ""

    tasks = [_one(i, orig) for i, orig in enumerate(nonempty_idx)]
    fetched: List[str] = await asyncio.gather(*tasks)

    # 4. Reassemble into the original positions (empty queries → "").
    result: List[str] = ["" for _ in queries]
    for slot, value in zip(nonempty_idx, fetched):
        result[slot] = value
    logger.info(
        f"📦 [{log_prefix}] prefetched {sum(1 for v in result if v)}/{len(queries)} "
        f"vault blocks in 1 embed call + {len(nonempty_idx)} parallel Milvus/Mongo fetches"
    )
    return result


# Belt-and-braces scrubber: strip inline citation markers (`[vault:...]`,
# `[doc:...]`, `[source:...]`, etc.) that occasionally leak through into
# rendered presentation / printable / report output despite the prompt
# instruction. Vault passages are injected for grounding only — these
# bracketed IDs look like garbage when they show up in slide bullets or
# page bodies.
#
# Pattern matches the tag itself (no surrounding whitespace) so the
# substitution can insert a single space — that way `decline[vault:x]is`
# becomes `decline is` rather than `declineis`. Trailing cleanup collapses
# the resulting double-spaces and removes spaces before punctuation.
_CITATION_TAG_PATTERN = re.compile(
    r'\[\s*(?:vault|doc|document|source|internet|structured|chunk)\s*:\s*[^\]]*\]',
    re.IGNORECASE,
)
_SPACE_BEFORE_PUNCT = re.compile(r'[ \t]+([.,;:!?\)\]])')
_MULTI_SPACE = re.compile(r'[ \t]{2,}')
_SPACE_AT_LINE_START = re.compile(r'(^|\n)[ \t]+', re.MULTILINE)
_SPACE_AT_LINE_END = re.compile(r'[ \t]+(\n|$)')


def strip_citation_tags(value: Any) -> Any:
    """Recursively strip `[vault:...]` / `[doc:...]` / `[source:...]` /
    `[internet:...]` / `[structured:...]` / `[chunk:...]` tags from any
    string fields in ``value``. Walks dicts and lists so callers can pass a
    parsed slot tree (presentation / printable) or an HTML string (report
    composer) and get clean output back. Non-string scalars pass through
    unchanged.

    Replaces each tag with a single space (then collapses) so adjacent
    word characters don't get merged when the model emitted the tag with
    no surrounding whitespace.
    """
    if isinstance(value, str):
        if '[' not in value:
            # Fast path — most strings have no tags. Skip regex work.
            return value
        # Replace each tag with a single space.
        cleaned = _CITATION_TAG_PATTERN.sub(' ', value)
        # Tighten up: drop spaces before punctuation, collapse multi-spaces,
        # and trim leading whitespace on each line (paragraph boundaries
        # left intact).
        cleaned = _SPACE_BEFORE_PUNCT.sub(r'\1', cleaned)
        cleaned = _MULTI_SPACE.sub(' ', cleaned)
        cleaned = _SPACE_AT_LINE_START.sub(r'\1', cleaned)
        cleaned = _SPACE_AT_LINE_END.sub(r'\1', cleaned)
        return cleaned
    if isinstance(value, list):
        return [strip_citation_tags(v) for v in value]
    if isinstance(value, dict):
        return {k: strip_citation_tags(v) for k, v in value.items()}
    return value


__all__ = [
    "TOOL_NAME",
    "MAX_RESULTS_PER_CALL",
    "DEFAULT_RESULTS_PER_CALL",
    "build_personal_data_tool_schema",
    "dispatch_personal_data_tool",
    "retrieve_vault_context_for_prompt",
    "retrieve_vault_contexts_batch",
    "strip_citation_tags",
]
