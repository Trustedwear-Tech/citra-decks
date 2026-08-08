"""
Agent samples — historical decision corpus per Smart App agent.

A Smart App's "Refresh from History" workflow pulls historical records from a
dept-MCP source (SAP claims, CRM tickets, KYC submissions, etc.), packages them
into ``{input, output, reasoning, source_id}`` shape, and writes one document
per workflow run here. Each document holds the full sample batch plus stats so
re-curation never has to re-pull from the source.

Twin storage: the same workflow run also writes embedded copies to a per-agent
Milvus collection (``samples_<agent_id>``) where ``is_canonical=True`` marks
the curated few-shot subset and the rest is searched by vector similarity at
runtime via ``NeighborSamplesTool``.

Composite primary key: ``(tenant_id, agent_id, version)``. Latest version wins
for runtime reads; older versions kept for audit + rollback.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SampleRecord(BaseModel):
    """One historical decision packaged for few-shot use."""

    source_id: str = Field(..., description="Stable id from the source system, e.g. 'SAP:CLAIM:000123'")
    input: Dict[str, Any] = Field(..., description="Input fields the decision was made from")
    output: Dict[str, Any] = Field(..., description="Decision + supporting fields (reason_code, cited_policy, amount, …)")
    reasoning_trace: Optional[str] = Field(None, description="Human-written reasoning if present in source")
    decision: Optional[str] = Field(None, description="Decision class extracted from output (approve/reject/escalate/…). Indexed.")
    severity: Optional[str] = Field(None, description="Optional severity tag (high/medium/low). Indexed for filtering.")
    is_canonical: bool = Field(False, description="Set by FewShotSelector. Canonical examples are always-loaded.")
    captured_at: Optional[datetime] = None


class SampleStats(BaseModel):
    """Distributions surfaced in the Smart App > Workflows view."""

    total: int = 0
    decision_dist: Dict[str, float] = Field(default_factory=dict)
    canonical_count: int = 0
    pii_scrubbed_count: int = 0
    deduped_count: int = 0


class AgentSamplesDocument(BaseModel):
    """One workflow run's worth of samples for a Smart App agent."""

    # Composite identity
    tenant_id: str
    agent_id: str
    version: int = Field(1, ge=1, description="Monotonic per (tenant_id, agent_id). Latest wins at runtime.")

    # Provenance
    app_slug: Optional[str] = None
    source_workflow_run_id: Optional[str] = None
    source_mcp: Dict[str, Any] = Field(
        default_factory=dict,
        description="{ dept_id, source_id, tool_name } — for re-pull and audit",
    )
    filters_used: Dict[str, Any] = Field(
        default_factory=dict,
        description="The filter set passed to the dept-MCP for this pull.",
    )

    # The samples themselves
    samples: List[SampleRecord] = Field(default_factory=list)
    stats: SampleStats = Field(default_factory=SampleStats)

    # Status
    status: str = Field("published", description="pending | published | superseded")

    # Audit
    produced_at: Optional[datetime] = None
    created_by: Optional[str] = None


class CreateAgentSamplesRequest(BaseModel):
    tenant_id: str
    agent_id: str
    app_slug: Optional[str] = None
    source_workflow_run_id: Optional[str] = None
    source_mcp: Dict[str, Any] = Field(default_factory=dict)
    filters_used: Dict[str, Any] = Field(default_factory=dict)
    samples: List[SampleRecord] = Field(default_factory=list)
    stats: SampleStats = Field(default_factory=SampleStats)
