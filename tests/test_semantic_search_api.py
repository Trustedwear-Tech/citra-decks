"""resolve_source_scoping — the endpoint's AUTHORITATIVE dept/visibility read
from the DISCOVERY registry (the MCP publishes every source at boot; dept SOP
libraries register there directly). The retired central ``dept_sources``
collection is no longer consulted. A consumer must not widen its own access by
supplying a dept_id — the server resolves scope itself."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _patch_scope(monkeypatch, scope):
    """Patch the discovery lookup (``get_source_scope``) to return ``scope``."""
    import services.enterprise_mcp_client as emc

    async def _fake(source_id, jwt_token=None):
        return scope if (scope and source_id == scope.get("source_id")) else None

    monkeypatch.setattr(emc, "get_source_scope", _fake)


def test_resolve_scoping_returns_registry_truth(monkeypatch):
    from semantic_search_api import resolve_source_scoping
    _patch_scope(monkeypatch, {
        "source_id": "acme_power_policy_library", "source_type": "semantic",
        "dept_id": "central_pmu", "org_id": "acme-power",
        "public_within_org": True, "rag_collection": "mcp_dept_libraries"})
    out = asyncio.run(resolve_source_scoping("acme_power_policy_library"))
    assert out == {"dept_id": "central_pmu", "org_id": "acme-power",
                   "rag_collection": "mcp_dept_libraries", "public_within_org": True,
                   # Server truth like the rest: the source's declared read
                   # allow-list. Absent from the scope payload ⇒ [] ⇒ no role
                   # restriction. Without this the dept gate was the only check,
                   # so any dept member could read an admin-restricted corpus.
                   "roles_allowed": []}


def test_resolve_scoping_carries_roles_allowed(monkeypatch):
    from semantic_search_api import resolve_source_scoping
    _patch_scope(monkeypatch, {
        "source_id": "s", "source_type": "semantic",
        "dept_id": "d", "org_id": "o", "public_within_org": False,
        "rag_collection": "c", "roles_allowed": ["dept_admin", "org_admin"]})
    out = asyncio.run(resolve_source_scoping("s"))
    assert out["roles_allowed"] == ["dept_admin", "org_admin"]


def test_resolve_scoping_none_when_unregistered(monkeypatch):
    from semantic_search_api import resolve_source_scoping
    _patch_scope(monkeypatch, None)
    assert asyncio.run(resolve_source_scoping("nope")) is None


def test_resolve_scoping_none_on_discovery_error(monkeypatch):
    # A discovery outage makes get_source_scope return None (fail-CLOSED — it must
    # NOT raise, which would 500 the read, and must NOT grant): the endpoint then
    # 403s rather than serving an unscoped read.
    from semantic_search_api import resolve_source_scoping
    import services.enterprise_mcp_client as emc

    async def _down(source_id, jwt_token=None):
        return None

    monkeypatch.setattr(emc, "get_source_scope", _down)
    assert asyncio.run(resolve_source_scoping("acme_power_policy_library")) is None
