# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
rag/retrieval_guard.py
======================
Retrieval-confidence assessment + chunk formatting helpers used by every RAG
feature in Citra-Service to gate the LLM call when the vault returned nothing
useful.

Why this exists:
- Before this module, every feature called the LLM with whatever Milvus
  returned — including an empty string — which let the LLM silently fabricate
  answers from training knowledge. Now callers can `assess_context()` and
  branch (block / warn / degrade) before paying for an LLM call that's
  doomed to hallucinate.
- The `format_chunks_with_origin()` helper guarantees the LLM sees explicit
  `[VAULT CHUNK …]` / `[INTERNET CHUNK …]` / `[STRUCTURED …]` headers, which
  is the prerequisite for the `[vault:…]` / `[internet:…]` / `[general-knowledge]`
  inline citation tags (see prompts.grounding.CITATION_TAGS_RULE).
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Env-driven thresholds — safe defaults but tunable per deployment.
MIN_VAULT_TRUST = float(os.getenv("MIN_VAULT_TRUST", "0.75"))
MIN_CHUNK_SCORE = float(os.getenv("MIN_CHUNK_SCORE", "0.0"))
MIN_CONTEXT_CHARS = int(os.getenv("MIN_CONTEXT_CHARS", "200"))
LOW_SIGNAL_SCORE = float(os.getenv("LOW_SIGNAL_SCORE", "0.45"))


@dataclass
class ContextQuality:
    """Result of `assess_context()` — what we know about the retrieval."""
    has_context: bool = False
    char_count: int = 0
    chunk_count: int = 0
    max_score: float = 0.0
    avg_score: float = 0.0
    low_signal: bool = False
    sources_present: List[str] = field(default_factory=list)  # ['vault','internet','structured']

    def as_event_dict(self) -> Dict[str, Any]:
        """Shape suitable for the SSE GROUNDING event."""
        return {
            "has_context": self.has_context,
            "char_count": self.char_count,
            "chunk_count": self.chunk_count,
            "max_score": round(self.max_score, 4),
            "avg_score": round(self.avg_score, 4),
            "low_signal": self.low_signal,
            "sources_present": list(self.sources_present),
        }


def assess_context(
    chunks: Optional[Sequence[Dict[str, Any]]] = None,
    formatted_text: Optional[str] = None,
    min_chars: int = MIN_CONTEXT_CHARS,
) -> ContextQuality:
    """
    Inspect either a list of chunk dicts or a pre-formatted context string and
    decide whether the retrieval is strong enough to ground a factual answer.

    `low_signal` = we have *some* context but the top score is below
    LOW_SIGNAL_SCORE — caller should consider keeping internet_search enabled
    or running the critic.
    """
    chunks = list(chunks or [])
    text_len = len(formatted_text or "")

    if not chunks and text_len < min_chars:
        return ContextQuality(
            has_context=False,
            char_count=text_len,
            chunk_count=0,
            max_score=0.0,
            avg_score=0.0,
            low_signal=True,
            sources_present=[],
        )

    scores: List[float] = []
    sources: set[str] = set()
    total_chars = text_len
    for ch in chunks:
        try:
            scores.append(float(ch.get("score", 0.0) or 0.0))
        except (TypeError, ValueError):
            scores.append(0.0)
        origin = (
            ch.get("source_origin")
            or ch.get("source")
            or _origin_from_metadata(ch.get("metadata") or {})
            or "vault"
        )
        sources.add(str(origin))
        if not text_len:
            total_chars += len(ch.get("text") or ch.get("content") or "")

    max_score = max(scores) if scores else 0.0
    avg_score = (sum(scores) / len(scores)) if scores else 0.0
    has_context = bool(chunks) or total_chars >= min_chars

    return ContextQuality(
        has_context=has_context,
        char_count=total_chars,
        chunk_count=len(chunks),
        max_score=max_score,
        avg_score=avg_score,
        low_signal=(not has_context) or (max_score < LOW_SIGNAL_SCORE),
        sources_present=sorted(sources),
    )


def _origin_from_metadata(metadata: Dict[str, Any]) -> Optional[str]:
    """Heuristic: derive source_origin from a chunk's metadata bag."""
    if not isinstance(metadata, dict):
        return None
    src_type = (metadata.get("source_type") or "").lower()
    if "internet" in src_type or "web" in src_type:
        return "internet"
    if "structured" in src_type or "saas" in src_type or "sql" in src_type:
        return "structured"
    if "enterprise" in src_type:
        return "enterprise"
    if src_type:
        return src_type
    return None


def tag_chunks_with_origin(
    chunks: Sequence[Dict[str, Any]],
    default_origin: str = "vault",
) -> List[Dict[str, Any]]:
    """
    Return a new list with `source_origin` set on each chunk dict (in-place
    mutation avoided so caller-supplied lists aren't aliased).
    """
    tagged: List[Dict[str, Any]] = []
    for ch in chunks:
        if not isinstance(ch, dict):
            continue
        copy = dict(ch)
        if "source_origin" not in copy:
            origin = (
                copy.get("source")
                or _origin_from_metadata(copy.get("metadata") or {})
                or default_origin
            )
            copy["source_origin"] = origin
        tagged.append(copy)
    return tagged


def format_chunks_with_origin(
    chunks: Sequence[Dict[str, Any]],
    max_chars: Optional[int] = None,
) -> str:
    """
    Render chunks for the LLM with explicit `[VAULT CHUNK doc=… score=…]` /
    `[INTERNET CHUNK url=…]` / `[STRUCTURED CHUNK table=…]` headers so the
    LLM can produce typed inline citations.
    """
    if not chunks:
        return ""

    parts: List[str] = []
    used_chars = 0
    for idx, ch in enumerate(chunks, 1):
        if not isinstance(ch, dict):
            continue
        origin = (
            ch.get("source_origin")
            or ch.get("source")
            or _origin_from_metadata(ch.get("metadata") or {})
            or "vault"
        )
        text = ch.get("text") or ch.get("content") or ""
        if not text.strip():
            continue
        score = ch.get("score", 0.0)
        try:
            score_str = f"{float(score):.2f}"
        except (TypeError, ValueError):
            score_str = "0.00"

        if origin == "internet":
            url = ch.get("url") or (ch.get("metadata") or {}).get("url") or ""
            host = urlparse(url).netloc if url else "unknown"
            header = f"[INTERNET CHUNK {idx} host={host} score={score_str}]"
        elif origin in ("structured", "saas"):
            table = ch.get("table") or (ch.get("metadata") or {}).get("table") or "structured"
            header = f"[STRUCTURED CHUNK {idx} table={table} score={score_str}]"
        elif origin == "enterprise":
            doc_id = ch.get("document_id") or (ch.get("metadata") or {}).get("document_id") or ""
            header = f"[ENTERPRISE CHUNK {idx} doc={doc_id} score={score_str}]"
        else:
            doc_id = ch.get("document_id") or (ch.get("metadata") or {}).get("document_id") or ""
            topic = ch.get("topic") or ""
            extra = f" topic={topic!r}" if topic else ""
            header = f"[VAULT CHUNK {idx} doc={doc_id} score={score_str}{extra}]"

        block = f"{header}\n{text.strip()}"
        if max_chars is not None and used_chars + len(block) > max_chars:
            parts.append("[…context truncated for length…]")
            break
        parts.append(block)
        used_chars += len(block)

    return "\n\n".join(parts)


def decide_internet_search(
    quality: ContextQuality,
    user_enabled: bool,
    force_internet: bool = False,
    min_vault_trust: float = MIN_VAULT_TRUST,
) -> Dict[str, Any]:
    """
    Internet search gate.

    The previous behaviour suppressed ``internet_search`` whenever the vault
    looked "authoritative" (top score >= ``MIN_VAULT_TRUST``). That broke
    queries like *"latest news today"* because tools that return synthetic
    score=1.0 (e.g. ``SaaSDataTool`` schema previews) would always trip the
    gate and starve the LLM of fresh web data.

    The LLM already knows when to call ``internet_search`` — there's no need
    for a server-side heuristic to second-guess it. We now pass through the
    user toggle (with ``force_internet`` as the only override) and let the
    LLM decide whether to invoke the tool.
    """
    if force_internet:
        return {"enabled": True, "reason": "force_internet"}
    if not user_enabled:
        return {"enabled": False, "reason": "user_toggle_off"}
    return {"enabled": True, "reason": "user_toggle_on"}


def grounding_log_event(
    feature: str,
    quality: ContextQuality,
    decision: Dict[str, Any],
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a structured log payload — emit via logger.info with extra=this dict."""
    payload = {
        "event": "grounding_decision",
        "feature": feature,
        "request_id": request_id,
        "internet_enabled": decision.get("enabled"),
        "internet_decision_reason": decision.get("reason"),
        **quality.as_event_dict(),
    }
    logger.info(
        f"🛡️  [GROUNDING] feature={feature} ctx={quality.chunk_count} "
        f"max={quality.max_score:.2f} internet={decision.get('enabled')} "
        f"reason={decision.get('reason')}"
    )
    return payload
