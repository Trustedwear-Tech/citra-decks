"""
rag/retrieval_profiles.py
=========================
Per-feature top_k / rerank-to constants. Single place to tune retrieval breadth
without hunting through 9 feature files.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class RetrievalProfile:
    name: str
    top_k_initial: int   # how many chunks Milvus returns
    top_k_final: int     # how many survive the reranker
    min_score: float     # cosine threshold below which chunks are dropped


PROFILES: Dict[str, RetrievalProfile] = {
    # Factual / conversational chat — small but high-precision context window.
    "factual": RetrievalProfile("factual", top_k_initial=8, top_k_final=4, min_score=0.55),
    # Structured outputs (diagrams, mindmaps, JSON) — moderate breadth.
    "structured": RetrievalProfile("structured", top_k_initial=12, top_k_final=6, min_score=0.50),
    # Long-form generation (composer, presentation, printable) — wide net.
    "creative": RetrievalProfile("creative", top_k_initial=20, top_k_final=8, min_score=0.45),
    # Tool-using agent flows.
    "agent": RetrievalProfile("agent", top_k_initial=10, top_k_final=5, min_score=0.50),
}


def get_profile(name: str) -> RetrievalProfile:
    """Return a known profile or fall back to `factual`."""
    return PROFILES.get(name, PROFILES["factual"])
