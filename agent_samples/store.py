"""
Async Mongo CRUD for ``agent_samples``.

Composite primary key ``(tenant_id, agent_id, version)``. Version is monotonic
per (tenant_id, agent_id) — ``insert_new_version()`` reads the current max and
writes max+1 atomically. Workflow runs only ever insert new versions; the
runtime always reads the latest published one. Older versions are kept for
audit and rollback.

Indexes (created lazily on first access):
  • uq_tenant_agent_version  — unique composite key
  • idx_tenant_agent_status  — fast "latest published" lookup
  • idx_run_id               — debug + traceability
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from citra_mongo import MONGODB_DATABASE, get_async_mongo_client

from models.agent_samples import (
    AgentSamplesDocument,
    CreateAgentSamplesRequest,
    SampleRecord,
    SampleStats,
)

logger = logging.getLogger(__name__)

COLLECTION = "agent_samples"
_indexes_ready = False


def _coll():
    return get_async_mongo_client()[MONGODB_DATABASE][COLLECTION]


async def ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    coll = _coll()
    await coll.create_index(
        [("tenant_id", 1), ("agent_id", 1), ("version", -1)],
        unique=True,
        name="uq_tenant_agent_version",
    )
    await coll.create_index(
        [("tenant_id", 1), ("agent_id", 1), ("status", 1), ("version", -1)],
        name="idx_tenant_agent_status",
    )
    await coll.create_index(
        [("source_workflow_run_id", 1)],
        name="idx_run_id",
        sparse=True,
    )
    _indexes_ready = True
    logger.info("[agent_samples] indexes ready")


def _to_model(doc: Dict[str, Any]) -> AgentSamplesDocument:
    doc = dict(doc)
    doc.pop("_id", None)
    samples_raw = doc.get("samples") or []
    doc["samples"] = [SampleRecord(**s) if isinstance(s, dict) else s for s in samples_raw]
    stats_raw = doc.get("stats") or {}
    doc["stats"] = SampleStats(**stats_raw) if isinstance(stats_raw, dict) else stats_raw
    return AgentSamplesDocument(**doc)


async def _next_version(tenant_id: str, agent_id: str) -> int:
    """Read the current max version for this agent and return max+1.

    First insertion returns version=1. Concurrent inserts will collide on the
    unique index and the second one must retry — callers should catch the
    DuplicateKey and re-call ``_next_version`` if that happens.
    """
    cur = (
        _coll()
        .find({"tenant_id": tenant_id, "agent_id": agent_id}, {"version": 1})
        .sort("version", -1)
        .limit(1)
    )
    async for doc in cur:
        return int(doc.get("version") or 0) + 1
    return 1


async def insert_new_version(
    req: CreateAgentSamplesRequest,
    *,
    created_by: Optional[str] = None,
    status: str = "published",
) -> AgentSamplesDocument:
    """Append a new versioned snapshot for (tenant_id, agent_id).

    Computes ``version = max(existing) + 1`` and writes. Workflow runs call
    this once at completion; the runtime then sees the new version on the
    next request.
    """
    await ensure_indexes()
    now = datetime.utcnow()

    # Stats can be derived if caller didn't supply them.
    stats = req.stats
    if not stats.total and req.samples:
        decision_counts: Dict[str, int] = {}
        canon = 0
        for s in req.samples:
            if s.decision:
                decision_counts[s.decision] = decision_counts.get(s.decision, 0) + 1
            if s.is_canonical:
                canon += 1
        total = len(req.samples)
        stats = SampleStats(
            total=total,
            decision_dist={
                k: round(v / total, 3) for k, v in decision_counts.items()
            },
            canonical_count=canon,
            pii_scrubbed_count=stats.pii_scrubbed_count,
            deduped_count=stats.deduped_count,
        )

    # Retry once on version collision (rare; only happens on truly concurrent runs).
    for attempt in range(2):
        version = await _next_version(req.tenant_id, req.agent_id)
        payload = {
            "tenant_id": req.tenant_id,
            "agent_id": req.agent_id,
            "version": version,
            "app_slug": req.app_slug,
            "source_workflow_run_id": req.source_workflow_run_id,
            "source_mcp": req.source_mcp,
            "filters_used": req.filters_used,
            "samples": [s.model_dump() for s in req.samples],
            "stats": stats.model_dump(),
            "status": status,
            "produced_at": now,
            "created_by": created_by,
        }
        try:
            await _coll().insert_one(payload)
            # Mark previous version superseded (best-effort; non-blocking semantics).
            await _coll().update_many(
                {
                    "tenant_id": req.tenant_id,
                    "agent_id": req.agent_id,
                    "version": {"$lt": version},
                    "status": "published",
                },
                {"$set": {"status": "superseded"}},
            )
            return _to_model(payload)
        except Exception as exc:  # likely DuplicateKey from a concurrent run
            if attempt == 0:
                logger.warning("[agent_samples] version collision on attempt %d, retrying: %s", attempt, exc)
                continue
            raise


async def get_latest(tenant_id: str, agent_id: str, *, status: Optional[str] = "published") -> Optional[AgentSamplesDocument]:
    """Return the most-recent version for this agent. Default filters to status='published'."""
    q: Dict[str, Any] = {"tenant_id": tenant_id, "agent_id": agent_id}
    if status is not None:
        q["status"] = status
    doc = await _coll().find_one(q, sort=[("version", -1)])
    return _to_model(doc) if doc else None


async def get_version(tenant_id: str, agent_id: str, version: int) -> Optional[AgentSamplesDocument]:
    doc = await _coll().find_one(
        {"tenant_id": tenant_id, "agent_id": agent_id, "version": version}
    )
    return _to_model(doc) if doc else None


async def list_versions(
    tenant_id: str,
    agent_id: str,
    *,
    include_samples: bool = False,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Return version history (newest first) — metadata only by default to
    keep the response small for the Workflows tab."""
    projection: Optional[Dict[str, Any]] = None
    if not include_samples:
        projection = {
            "samples": 0,  # heaviest field — exclude
        }
    cur = (
        _coll()
        .find({"tenant_id": tenant_id, "agent_id": agent_id}, projection)
        .sort("version", -1)
        .limit(int(limit))
    )
    out: List[Dict[str, Any]] = []
    async for doc in cur:
        d = dict(doc)
        d.pop("_id", None)
        out.append(d)
    return out


async def find_samples(
    tenant_id: str,
    agent_id: str,
    *,
    decision: Optional[str] = None,
    is_canonical: Optional[bool] = None,
    severity: Optional[str] = None,
    limit: int = 100,
    version: Optional[int] = None,
) -> List[SampleRecord]:
    """Filter samples within the latest (or specified) version for this agent.

    Used by audit views and by the BA's "View samples" panel. Runtime
    retrieval goes through Milvus, not this function.
    """
    doc = (
        await get_version(tenant_id, agent_id, version)
        if version is not None
        else await get_latest(tenant_id, agent_id)
    )
    if not doc:
        return []
    out: List[SampleRecord] = []
    for s in doc.samples:
        if decision is not None and s.decision != decision:
            continue
        if is_canonical is not None and s.is_canonical != is_canonical:
            continue
        if severity is not None and s.severity != severity:
            continue
        out.append(s)
        if len(out) >= limit:
            break
    return out


async def delete_version(tenant_id: str, agent_id: str, version: int) -> bool:
    res = await _coll().delete_one(
        {"tenant_id": tenant_id, "agent_id": agent_id, "version": version}
    )
    return res.deleted_count > 0
