"""Unit tests for the dept SOP Library authorization gate (dept_library.py).

Pins the §3.4 access model as PURE logic (no web/Mongo): the library is
dept-NATIVE — writes are manager-only (dept_admin of the dept / org_admin /
super_admin), reads are any member of the dept (public-within-dept), and
cross-org is never permitted below super_admin.

These are pure functions, so no Citra-Service stack, Mongo, or JWT is needed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dept_library import (  # noqa: E402
    build_dept_library_registration,
    can_manage_dept_library,
    can_read_dept_library,
    dept_library_collection_name,
    dept_library_source_id,
    dept_library_tool_id,
    readable_dept_ids,
    shape_document_rows,
)


def _mgr(**kw):
    base = dict(user_org_id="acme", user_dept_ids=["operations"],
                target_org="acme", target_dept="operations")
    base.update(kw)
    return can_manage_dept_library(**base)


def _rd(**kw):
    base = dict(user_org_id="acme", user_dept_ids=["operations"],
                target_org="acme", target_dept="operations")
    base.update(kw)
    return can_read_dept_library(**base)


# ── manage (write) ───────────────────────────────────────────────────────────
def test_super_admin_manages_anything_incl_cross_org():
    assert _mgr(roles=["super_admin"], user_org_id="other", target_org="acme")
    # even with no org/dept context at all
    assert can_manage_dept_library(roles=["super_admin"], user_org_id=None,
                                   user_dept_ids=[], target_org=None, target_dept=None)


def test_org_admin_manages_own_org_only():
    assert _mgr(roles=["org_admin"], user_dept_ids=[])          # any dept in own org
    assert not _mgr(roles=["org_admin"], user_org_id="acme", target_org="beta")


def test_dept_admin_manages_only_own_dept_same_org():
    assert _mgr(roles=["dept_admin"], user_dept_ids=["operations"])
    # dept_admin of a DIFFERENT dept cannot manage operations
    assert not _mgr(roles=["dept_admin"], user_dept_ids=["finance"])
    # same dept name, different org = no (cross-tenant dept-string collision)
    assert not _mgr(roles=["dept_admin"], user_org_id="acme", target_org="beta",
                    user_dept_ids=["operations"])


def test_regular_user_never_manages():
    assert not _mgr(roles=["user"])
    assert not _mgr(roles=[])


def test_manage_requires_target_org_and_dept_below_super():
    assert not can_manage_dept_library(roles=["org_admin"], user_org_id="acme",
                                       user_dept_ids=[], target_org=None,
                                       target_dept="operations")
    assert not can_manage_dept_library(roles=["dept_admin"], user_org_id="acme",
                                       user_dept_ids=["operations"],
                                       target_org="acme", target_dept=None)


# ── read ─────────────────────────────────────────────────────────────────────
def test_dept_member_reads_own_dept():
    assert _rd(roles=["user"], user_dept_ids=["operations"])


def test_non_member_regular_user_cannot_read():
    assert not _rd(roles=["user"], user_dept_ids=["finance"])
    # cross-org member string collision must not grant read
    assert not _rd(roles=["user"], user_org_id="acme", target_org="beta",
                   user_dept_ids=["operations"])


def test_managers_read_via_manage():
    assert _rd(roles=["org_admin"], user_dept_ids=[])
    assert _rd(roles=["super_admin"], user_org_id="x", target_org="acme")


# ── source_id + collection naming (the ingest↔MCP bridge) ────────────────────
def test_source_id_is_dept_unique():
    # source_id must be globally unique (MCP registry is keyed by source_id
    # alone) — a fixed "sop_library" would collide across departments.
    assert dept_library_source_id("operations") == "sop_library_operations"
    assert dept_library_source_id("operations") != dept_library_source_id("finance")


def test_dept_collection_name_is_shared_across_depts():
    # BREAKING CHANGE (shared dept-library collection): ALL dept libraries share
    # ONE Milvus collection, isolated by the scalar org_id/dept/source_id fields —
    # so the collection name is the SAME regardless of dept (not a per-dept name).
    from dept_library_store import shared_dept_collection
    assert dept_library_collection_name("operations") == shared_dept_collection()
    assert dept_library_collection_name("operations") == dept_library_collection_name("finance")
    assert dept_library_collection_name(None) == shared_dept_collection()
    assert "-" not in dept_library_collection_name("a-b-c")   # still a valid Milvus name


# ── semantic-source DISCOVERY registration payload ───────────────────────────
def test_registration_payload_has_discovery_required_fields():
    doc = build_dept_library_registration(
        org_id="acme", dept_id="operations", name="Ops SOPs", api_key="svc-key")
    # discovery routing/identity
    assert doc["source_id"] == "sop_library_operations"
    assert doc["tool_id"] == dept_library_tool_id("acme", "operations")
    assert doc["org_ids"] == ["acme"] and doc["dept_ids"] == ["operations"]
    # semantic ⇒ answered by the platform reader, so NO MCP query endpoint
    assert doc["source_type"] == "semantic" and doc["query_endpoint"] == ""
    # the SHARED dept-library collection the reader queries
    assert doc["rag_collection"] == dept_library_collection_name("operations")
    # readable by every dept role; dept-scoped (not org-public)
    assert set(doc["visibility"]["roles_allowed"]) >= {"user", "dept_admin"}
    assert doc["visibility"]["public_within_org"] is False
    # the stable secret used to later deregister
    assert doc["api_key"] == "svc-key"


# ── readable_dept_ids (list scoping) ─────────────────────────────────────────
def test_admins_list_all_org_depts_others_only_theirs():
    org_universe = ["operations", "finance", "maintenance"]
    assert readable_dept_ids(roles=["org_admin"], user_org_id="acme",
                             user_dept_ids=["operations"],
                             org_dept_ids=org_universe) == org_universe
    assert readable_dept_ids(roles=["super_admin"], user_org_id="acme",
                             user_dept_ids=[], org_dept_ids=org_universe) == org_universe
    assert readable_dept_ids(roles=["user"], user_org_id="acme",
                             user_dept_ids=["operations"],
                             org_dept_ids=org_universe) == ["operations"]


# ── document-list shaping (pure) ─────────────────────────────────────────────
def test_shape_document_rows():
    from datetime import datetime, timezone
    rows = [
        {"_id": "doc1", "filename": "Safety SOP.pdf", "chunks": 12,
         "created_at": datetime(2026, 7, 7, tzinfo=timezone.utc), "uploaded_by": "dba@x"},
        {"_id": "doc2", "filename": None, "chunks": 3, "created_at": None,
         "uploaded_by": "ops@x"},
    ]
    out = shape_document_rows(rows)
    assert out[0]["document_id"] == "doc1" and out[0]["filename"] == "Safety SOP.pdf"
    assert out[0]["chunks"] == 12 and out[0]["created_at"].startswith("2026-07-07")
    # filename falls back to the document_id when absent
    assert out[1]["filename"] == "doc2" and out[1]["created_at"] is None
