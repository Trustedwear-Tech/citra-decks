# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
File Relevance Scorer
=====================

Chat-time helper that takes a user's query and a list of candidate vault
files (with their upload-time enriched metadata), and asks the **large**
LLM tier which files are actually relevant.

This is what stops context-bloat: instead of mounting every file the user
owns, we mount only the ones the model says match the query. Token-overlap
heuristics are insufficient for enterprise queries — e.g. ``"the audit
doc"`` must match ``compliance_review.pdf`` even though no token overlaps.

Inputs
------
- ``query`` — the current user message
- ``candidates`` — pre-filtered list of ``CandidateFile`` (already scoped
  by the caller to ``user_id`` + ``folder_ids`` + ``use_personal_data``
  gate, and prefiltered by recency to a manageable count, e.g. ≤ 50)

Outputs
-------
- list of ``ScoredFile`` with ``score`` ∈ [0, 1] and ``reason``, only
  including entries the LLM kept.

Caching
-------
A 5-minute Redis TTL cache keyed on
``(user_id, sorted_folder_ids, sha256(query) , sorted document_ids)`` to
amortise the large-tier cost across multi-turn flows. Cache miss falls
back to a single live LLM call.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ScorerUnavailable(Exception):
    """Raised when the scorer LLM is unreachable (timeout / transport).

    Distinct from "LLM said no files match". Callers should fall back to a
    safe default (e.g. recency-based selection) rather than dropping every
    candidate file.
    """


# ── Tunables ─────────────────────────────────────────────────────────────
MAX_CANDIDATES = int(os.getenv("FILE_SCORER_MAX_CANDIDATES", "50"))
RELEVANCE_THRESHOLD = float(os.getenv("FILE_SCORER_THRESHOLD", "0.5"))
CACHE_TTL_SECONDS = int(os.getenv("FILE_SCORER_CACHE_TTL", "300"))
LLM_TIMEOUT_SECONDS = float(os.getenv("FILE_SCORER_TIMEOUT", "35"))


# ── Data shapes ──────────────────────────────────────────────────────────
@dataclass
class CandidateFile:
    document_id: str
    filename: str
    file_type: str = ""
    summary: str = ""
    doc_type: str = ""
    semantic_tags: List[str] = field(default_factory=list)
    key_entities: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoredFile:
    document_id: str
    filename: str
    score: float
    reason: str
    extra: Dict[str, Any] = field(default_factory=dict)


SYSTEM_PROMPT = (
    "You are a precise file-relevance ranker. Given a user's chat message "
    "and a list of files (each with filename, doc_type, summary, tags and "
    "entities), score each file's relevance to the message on a [0,1] "
    "scale and justify it in one short sentence.\n\n"
    "Scoring guide:\n"
    "  0.9–1.0 — file is clearly the subject (filename or summary directly "
    "matches what the user is asking about).\n"
    "  0.6–0.8 — file is a strong topical / entity match.\n"
    "  0.3–0.5 — possibly related; same broad domain.\n"
    "  0.0–0.2 — unrelated.\n\n"
    "Rules:\n"
    "- If the user message references 'this/the/uploaded' file without a "
    "specific name, prefer the most recently uploaded matching file.\n"
    "- Be strict — false positives are worse than false negatives because "
    "each match consumes context window.\n"
    "- Return ONLY a JSON object of this exact shape:\n"
    "  {\"scores\": [{\"document_id\": \"<id>\", \"score\": 0.0, "
    "\"reason\": \"<one short sentence>\"}, ...]}\n"
    "- Include EVERY input document_id exactly once."
)


def _candidate_block(c: CandidateFile, idx: int) -> str:
    parts = [
        f"[{idx}] document_id={c.document_id}",
        f"    filename: {c.filename}",
    ]
    if c.doc_type:
        parts.append(f"    doc_type: {c.doc_type}")
    if c.summary:
        parts.append(f"    summary: {c.summary[:300]}")
    if c.semantic_tags:
        parts.append(f"    tags: {', '.join(c.semantic_tags[:10])}")
    if c.key_entities:
        parts.append(f"    entities: {', '.join(c.key_entities[:10])}")
    return "\n".join(parts)


def _build_prompt(query: str, candidates: List[CandidateFile]) -> str:
    blocks = [_candidate_block(c, i) for i, c in enumerate(candidates)]
    return (
        f"User message:\n{query.strip()}\n\n"
        f"Candidate files ({len(candidates)}):\n"
        + "\n\n".join(blocks)
    )


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_response(raw: str, candidates: List[CandidateFile]) -> List[ScoredFile]:
    if not raw:
        return []
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_OBJECT_RE.search(text)
        if not m:
            logger.warning("file_relevance_scorer: response is not JSON")
            return []
        try:
            parsed = json.loads(m.group(0))
        except Exception:
            return []

    scores = parsed.get("scores") if isinstance(parsed, dict) else None
    if not isinstance(scores, list):
        return []

    by_id = {c.document_id: c for c in candidates}
    out: List[ScoredFile] = []
    for entry in scores:
        if not isinstance(entry, dict):
            continue
        doc_id = entry.get("document_id")
        if not isinstance(doc_id, str) or doc_id not in by_id:
            continue
        try:
            score = float(entry.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(1.0, score))
        reason = entry.get("reason") or ""
        if not isinstance(reason, str):
            reason = ""
        c = by_id[doc_id]
        out.append(ScoredFile(
            document_id=doc_id,
            filename=c.filename,
            score=score,
            reason=reason[:240],
            extra=c.extra,
        ))
    return out


# ── Optional Redis cache ─────────────────────────────────────────────────
def _cache_key(
    *, user_id: str, folder_ids: List[str], query: str, doc_ids: List[str]
) -> str:
    h = hashlib.sha256()
    h.update(user_id.encode())
    h.update(b"|")
    h.update(",".join(sorted(folder_ids)).encode())
    h.update(b"|")
    h.update(query.strip().encode())
    h.update(b"|")
    h.update(",".join(sorted(doc_ids)).encode())
    return f"file_relevance:{h.hexdigest()}"


def _get_redis():
    try:
        import redis  # type: ignore

        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        db = int(os.getenv("REDIS_DB", "0"))
        password = os.getenv("REDIS_PASSWORD") or None
        return redis.Redis(host=host, port=port, db=db, password=password,
                           decode_responses=True, socket_timeout=1)
    except Exception:
        return None


def _cache_get(key: str) -> Optional[List[Dict[str, Any]]]:
    try:
        r = _get_redis()
        if r is None:
            return None
        raw = r.get(key)
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def _cache_set(key: str, payload: List[Dict[str, Any]]) -> None:
    try:
        r = _get_redis()
        if r is None:
            return
        r.setex(key, CACHE_TTL_SECONDS, json.dumps(payload))
    except Exception:
        pass


# ── Public API ───────────────────────────────────────────────────────────
async def score_files_against_query(
    *,
    query: str,
    candidates: List[CandidateFile],
    user_id: str,
    folder_ids: Optional[List[str]] = None,
    threshold: float = RELEVANCE_THRESHOLD,
    max_candidates: int = MAX_CANDIDATES,
) -> List[ScoredFile]:
    """
    Score and filter ``candidates`` against ``query`` using the medium LLM.

    Returns only files with ``score >= threshold``, sorted high→low.
    Returns an empty list on any failure (caller falls back to filename
    heuristics or recency).
    """
    if not query or not candidates:
        return []

    folder_ids = folder_ids or []
    # Hard cap candidates so the prompt stays bounded.
    candidates = candidates[:max_candidates]
    doc_ids = [c.document_id for c in candidates]

    # Cache lookup
    key = _cache_key(user_id=user_id, folder_ids=folder_ids, query=query, doc_ids=doc_ids)
    cached = _cache_get(key)
    if cached is not None:
        logger.info("file_relevance_scorer: cache hit (%d cached scores)", len(cached))
        by_id = {c.document_id: c for c in candidates}
        out = []
        for entry in cached:
            c = by_id.get(entry.get("document_id"))
            if not c:
                continue
            score = float(entry.get("score", 0.0))
            if score < threshold:
                continue
            out.append(ScoredFile(
                document_id=c.document_id,
                filename=c.filename,
                score=score,
                reason=entry.get("reason", ""),
                extra=c.extra,
            ))
        out.sort(key=lambda s: s.score, reverse=True)
        return out

    try:
        from llm_oss import llm_call
    except Exception:
        logger.exception("file_relevance_scorer: cannot import llm_oss.llm_call")
        return []

    user_prompt = _build_prompt(query, candidates)

    def _sync_call() -> str:
        try:
            return llm_call(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                user_id=user_id,
                # Reasoning-capable models (e.g. deepseek-v4-pro) spend
                # hidden reasoning tokens against this budget. At 900 the
                # reasoning regularly consumed the entire budget, leaving
                # content_chars=0 with finish_reason=length — forcing the
                # llm_oss auto-retry to double and re-run (~11s wasted per
                # section during report builds). Setting 4000 up front gives
                # the reasoning + JSON output room on the first attempt.
                max_tokens=4000,
                temperature=0.1,
                top_p=0.9,
                json_mode=True,
                tier="large",
            )
        except Exception as e:
            logger.warning("file_relevance_scorer: llm_call failed: %s", e)
            return ""

    try:
        raw = await asyncio.wait_for(asyncio.to_thread(_sync_call),
                                     timeout=LLM_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning("file_relevance_scorer: timed out after %.1fs", LLM_TIMEOUT_SECONDS)
        raise ScorerUnavailable("scorer timed out")
    except Exception as e:
        logger.warning("file_relevance_scorer: unexpected error: %s", e)
        raise ScorerUnavailable(str(e))

    if not raw:
        # Empty raw means the inner sync llm_call raised; treat as unavailable
        # so the caller can fall back rather than silently dropping files.
        raise ScorerUnavailable("empty LLM response")

    scored = _parse_response(raw, candidates)
    if not scored:
        return []

    # Cache full set (above and below threshold) so subsequent turns reuse it.
    _cache_set(key, [
        {"document_id": s.document_id, "score": s.score, "reason": s.reason}
        for s in scored
    ])

    filtered = [s for s in scored if s.score >= threshold]
    filtered.sort(key=lambda s: s.score, reverse=True)
    logger.info(
        "file_relevance_scorer: %d/%d files passed threshold %.2f",
        len(filtered), len(scored), threshold,
    )
    return filtered
