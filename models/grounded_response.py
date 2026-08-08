"""
models/grounded_response.py
===========================
Additive response envelope used by features that want to expose grounding
metadata to the UI. Existing endpoints continue to return their current shapes;
this struct is opt-in via `EXPOSE_CITATIONS=true` env or per-request flag.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CitationEntry(BaseModel):
    """One citation with explicit source-origin so the UI can render distinctly."""
    source_origin: str = Field(
        ...,
        description="One of: vault | internet | structured | enterprise | general-knowledge",
    )
    text: Optional[str] = None
    url: Optional[str] = None
    doc_id: Optional[str] = None
    chunk_id: Optional[str] = None
    table: Optional[str] = None
    score: Optional[float] = None
    display_name: Optional[str] = None
    description: Optional[str] = None


class GroundingStats(BaseModel):
    """Per-response grounding telemetry."""
    has_context: bool = False
    chunk_count: int = 0
    max_score: float = 0.0
    avg_score: float = 0.0
    low_signal: bool = False
    sources_present: List[str] = Field(default_factory=list)
    internet_used: bool = False
    internet_decision_reason: Optional[str] = None
    unsupported_claims_count: int = 0
    critic_ran: bool = False


class GroundedResponse(BaseModel):
    """Envelope for any feature that wants to advertise grounding."""
    content: str
    citations: List[CitationEntry] = Field(default_factory=list)
    grounded: bool = True
    confidence: float = 0.0
    grounding: GroundingStats = Field(default_factory=GroundingStats)
    extra: Dict[str, Any] = Field(default_factory=dict)
