# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""Pure cores of the platform semantic reader (RAG short-circuit #6).

Pins:
  * resolve_semantic_collection derives <prefix>_<dept>_<source> IDENTICALLY to
    the MCP / VectorSink / SOP-Library ingestion (so the reader queries where
    the content was written — the acme-power hyphen gotcha);
  * build_filter_expr composes a SAFE Milvus boolean expr — only allowlisted
    fields, values quoted/escaped so a filter value can't inject expression
    syntax.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from semantic_reader import (  # noqa: E402
    _collection_cache,
    _default_prefix,
    _doc_order_key,
    _resolve_live_collection,
    build_filter_expr,
    can_query_semantic,
    resolve_semantic_collection,
    scope_expr,
    shape_chunk,
)


class _FakeMilvus:
    def __init__(self, collections):
        self._cols = list(collections)

    def has_collection(self, name):
        return name in self._cols

    def list_collections(self):
        return list(self._cols)


# ── collection naming (the ingest↔read contract) ────────────────────────────
def test_collection_name_matches_mcp_convention():
    assert resolve_semantic_collection("operations", "sop_library_operations") == \
        "mcp_operations_sop_library_operations"


def test_collection_name_sanitizes_hyphens_and_case():
    # hyphens/uppercase → underscores/lowercase — valid Milvus name AND identical
    # on the ingest and read sides.
    assert resolve_semantic_collection("Field-Ops", "policy-lib") == \
        "mcp_field_ops_policy_lib"
    assert "-" not in resolve_semantic_collection("a-b", "c-d")


def test_collection_name_defaults_dept_and_requires_source():
    assert resolve_semantic_collection(None, "src").startswith("mcp_default_")
    import pytest
    with pytest.raises(ValueError):
        resolve_semantic_collection("ops", "")


# test_dept_libraries_share_one_collection removed — tested dept_library.py,
# deleted in this pass as unrelated to the presentation/printable/report
# composers. Nothing else in this file depends on it (semantic_reader.py, the
# module this file actually tests, is unaffected and stays).


# ── filter expression (safe) ─────────────────────────────────────────────────
def test_scope_expr_bounds_read_to_source_dept_org():
    # Data-layer isolation: every clause present, injection-safe, dept via OR so
    # one expr fits both the VectorSink (`dept`) and SOP-Library (`department`) schema.
    e = scope_expr(source_id="policy_lib", dept_id="central_pmu", org_id="acme-power")
    assert 'source_id == "policy_lib"' in e
    assert 'dept == "central_pmu"' in e
    assert 'department' not in e   # strict (non-dynamic) collections reject unknown fields
    assert 'org_id == "acme-power"' in e
    assert e.count(" and ") == 2


def test_scope_expr_emits_only_provided_clauses_and_escapes():
    # A caller that can't supply dept/org still gets source_id isolation.
    assert scope_expr(source_id="s") == 'source_id == "s"'
    # quote-escaping (injection-safe): an embedded quote can't break out.
    assert '\\"' in scope_expr(source_id='a" or org_id == "b')


def test_doc_order_key_sorts_sections_numerically():
    # VectorSink ids are document-ordered (<slug>_p<page>_c<idx>); _c10 must sort
    # AFTER _c2, and pages before chunks — a plain string sort would break this.
    def chunk(cid):
        return {"metadata": {"chunk_id": cid}}
    ids = ["d_p1_c2", "d_p1_c10", "d_p1_c0", "d_p2_c0", "d_p1_c1"]
    ordered = sorted((chunk(i) for i in ids), key=_doc_order_key)
    assert [c["metadata"]["chunk_id"] for c in ordered] == \
        ["d_p1_c0", "d_p1_c1", "d_p1_c2", "d_p1_c10", "d_p2_c0"]
    # non-matching ids fall back to (page, id) without raising
    assert _doc_order_key({"metadata": {"chunk_id": "misc", "page": 3}}) == (3, "misc")


def test_doc_order_key_mixed_ids_do_not_raise():
    # A batch mixing conforming ids (int idx) and non-conforming ids on the SAME
    # page must not compare int-vs-str on the tiebreaker → no TypeError at sort
    # (which runs outside the reader's try/except and would 500 the endpoint).
    chunks = [
        {"metadata": {"chunk_id": "d_p3_c1", "page": 3}},   # matches → (3, "000000001")
        {"metadata": {"chunk_id": "loose",   "page": 3}},   # no match → (3, "loose")
        {"metadata": {"page": 3}},                          # no id    → (3, "")
    ]
    ordered = sorted(chunks, key=_doc_order_key)             # must not raise
    assert len(ordered) == 3


def test_filter_scalar_and_list():
    assert build_filter_expr({"folder_id": "f1"}) == 'folder_id == "f1"'
    assert build_filter_expr({"department": "ops", "folder_id": "f1"}) == \
        'department == "ops" and folder_id == "f1"'
    assert build_filter_expr({"doc_type": ["policy", "sop"]}) == \
        'doc_type in ["policy", "sop"]'
    # VectorSink dept-collection metadata (verified live) is allowlisted
    assert build_filter_expr({"dept": "central_pmu"}) == 'dept == "central_pmu"'


def test_default_prefix_from_env(monkeypatch):
    monkeypatch.delenv("SEMANTIC_COLLECTION_PREFIX", raising=False)
    assert _default_prefix() == "mcp"                         # enterprise default
    monkeypatch.setenv("SEMANTIC_COLLECTION_PREFIX", "demo_acme_power")
    assert _default_prefix() == "demo_acme_power"             # demo deployment (verified live)


def test_resolve_live_collection_exact_then_suffix():
    _collection_cache.clear()
    # exact prefix hit
    c = _FakeMilvus(["demo_acme_power_central_pmu_acme_power_policy_library"])
    assert _resolve_live_collection(c, "central_pmu", "acme_power_policy_library",
                                    prefix="demo_acme_power") == \
        "demo_acme_power_central_pmu_acme_power_policy_library"


def test_resolve_live_collection_suffix_fallback_on_wrong_prefix():
    _collection_cache.clear()
    # prefix is WRONG (mcp) but the real collection is found by its dept_source suffix
    c = _FakeMilvus(["demo_acme_power_central_pmu_acme_power_policy_library", "citra"])
    assert _resolve_live_collection(c, "central_pmu", "acme_power_policy_library",
                                    prefix="mcp") == \
        "demo_acme_power_central_pmu_acme_power_policy_library"


def test_resolve_live_collection_none_when_absent():
    _collection_cache.clear()
    c = _FakeMilvus(["citra", "something_else"])
    assert _resolve_live_collection(c, "central_pmu", "acme_power_policy_library",
                                    prefix="mcp") is None


def test_semantic_search_embed_failure_returns_empty(monkeypatch):
    # regression: the embed-failure handler must not reference an unbound
    # `collection` (resolved later) — an embed error degrades to no context,
    # it must NEVER raise (which would 500 the consumer).
    import asyncio
    import semantic_reader as sr

    async def _boom(*a, **k):
        raise RuntimeError("embedding provider down")

    monkeypatch.setattr("utils.embed_text", _boom, raising=False)
    out = asyncio.run(sr.semantic_search(
        source_id="acme_power_policy_library", dept_id="central_pmu",
        query="anything", top_k=3))
    assert out == []


def test_semantic_search_honors_explicit_collection(monkeypatch):
    # regression: semantic_search MUST search the caller's explicit rag_collection
    # (e.g. the shared `mcp_dept_libraries`) — a stray `collection = None` before the
    # try clobbered the param, forcing a per-dept derivation that doesn't exist and
    # returning zero hits ("no collection for source=...") while doc-fetch worked.
    import asyncio
    import semantic_reader as sr

    searched = {}

    class _Client:
        def has_collection(self, name):        # the explicit name exists → used as-is
            return name == "mcp_dept_libraries"

        def search(self, *, collection_name, **kw):
            searched["collection"] = collection_name
            return [[]]                        # no hits is fine; we assert the target

    async def _vec(*a, **k):
        return [0.0] * 8

    monkeypatch.setattr("utils.embed_text", _vec, raising=False)
    monkeypatch.setattr("config.milvus_config.get_milvus_client",
                        lambda: _Client(), raising=False)
    monkeypatch.setattr(sr, "_resolve_vector_field", lambda c, n: "dense_vector", raising=False)
    monkeypatch.setattr("reranker.is_reranker_enabled", lambda: False, raising=False)

    asyncio.run(sr.semantic_search(
        source_id="sop_library_central_pmu", dept_id="central_pmu",
        org_id="acme-power", query="crew dispatch", top_k=3,
        collection="mcp_dept_libraries"))
    assert searched.get("collection") == "mcp_dept_libraries"


def test_shape_chunk_drops_raw_vector():
    # output_fields=["*"] returns the 768-float vector — it must never ship
    out = shape_chunk({"id": "c1", "distance": 0.5,
                       "entity": {"text": "t", "vector": [0.1] * 768, "dept": "ops"}})
    assert out["text"] == "t" and "vector" not in out["metadata"]
    assert out["metadata"]["dept"] == "ops"


def test_filter_drops_unknown_fields():
    # an attacker-supplied key is not allowlisted → never enters the expression
    assert build_filter_expr({"user_id": "x", "folder_id": "f1"}) == 'folder_id == "f1"'
    assert build_filter_expr({"'; drop": "x"}) == ""


def test_filter_escapes_injection_in_values():
    # a value that tries to break out of the quoted literal is escaped
    expr = build_filter_expr({"folder_id": 'f" or department == "ops'})
    # the two inner quotes are backslash-escaped, so they can't close the literal
    assert expr == 'folder_id == "f\\" or department == \\"ops"'


def test_filter_empty_and_none():
    assert build_filter_expr(None) == ""
    assert build_filter_expr({}) == ""
    assert build_filter_expr({"folder_id": None}) == ""
    assert build_filter_expr({"doc_type": []}) == ""


# ── result shaping ───────────────────────────────────────────────────────────
def test_shape_chunk_nested_entity():
    hit = {"id": "c1", "distance": 0.42,
           "entity": {"text": "SOP body", "document_id": "d1", "folder_id": "f1"}}
    out = shape_chunk(hit)
    assert out["text"] == "SOP body" and out["score"] == 0.42
    assert out["metadata"]["document_id"] == "d1" and out["metadata"]["folder_id"] == "f1"
    assert "text" not in out["metadata"]          # text lifted out of metadata


def test_shape_chunk_flat_and_id_fallback():
    out = shape_chunk({"primary_key": "pk9", "score": 0.3, "text": "t", "doc_type": "policy"})
    assert out["text"] == "t" and out["score"] == 0.3
    assert out["metadata"]["chunk_id"] == "pk9" and out["metadata"]["doc_type"] == "policy"


def test_shape_chunk_missing_text_and_score():
    out = shape_chunk({"entity": {"document_id": "d1"}})
    assert out["text"] == "" and out["score"] is None


# ── query authorization ──────────────────────────────────────────────────────
def test_dept_member_can_query_own_dept():
    assert can_query_semantic(roles=["user"], user_dept_ids=["operations"], dept_id="operations")


def test_non_member_blocked():
    assert not can_query_semantic(roles=["user"], user_dept_ids=["finance"], dept_id="operations")


def test_admins_query_any_dept():
    assert can_query_semantic(roles=["org_admin"], user_dept_ids=[], dept_id="operations")
    assert can_query_semantic(roles=["super_admin"], user_dept_ids=[], dept_id="anything")


def test_org_wide_source_readable_by_any_authenticated():
    # no dept_id = org-wide corpus → any authenticated caller (already org-scoped)
    assert can_query_semantic(roles=["user"], user_dept_ids=[], dept_id=None)


def test_public_within_org_source_readable_across_depts():
    # a dept-owned but public_within_org corpus (e.g. the acme policy library) is
    # readable by ANY org member, even one not in the owning dept.
    assert can_query_semantic(roles=["user"], user_dept_ids=["finance"],
                              dept_id="central_pmu", public_within_org=True)
    # ...but a NON-public dept source stays dept-gated for a non-member.
    assert not can_query_semantic(roles=["user"], user_dept_ids=["finance"],
                                  dept_id="central_pmu", public_within_org=False)


# ── roles_allowed — the source's declared read allow-list ────────────────────
# sources.json documents roles_allowed as "roles that can query/read this source
# (checked against the caller's JWT)", and the dept-MCP hard-gates on it for
# STRUCTURED reads (auth.py:155). The semantic path ignored it entirely: a plain
# `user` in the owning dept could POST /semantic/search with any source_id and
# read a corpus authored roles_allowed: ["dept_admin","org_admin"].
# /tools/available hid it from their ROUTING, but the endpoint takes source_id
# straight from the request body.

def test_roles_allowed_blocks_a_dept_member_without_the_role():
    assert not can_query_semantic(
        roles=["user"], user_dept_ids=["central_pmu"], dept_id="central_pmu",
        roles_allowed=["dept_admin", "org_admin"],
    )


def test_roles_allowed_admits_a_dept_member_with_the_role():
    assert can_query_semantic(
        roles=["dept_admin"], user_dept_ids=["central_pmu"], dept_id="central_pmu",
        roles_allowed=["dept_admin", "org_admin"],
    )


def test_roles_allowed_is_case_insensitive():
    assert can_query_semantic(
        roles=["Dept_Admin"], user_dept_ids=["d"], dept_id="d",
        roles_allowed=["DEPT_ADMIN"],
    )


def test_empty_roles_allowed_means_no_role_restriction():
    """The sources.json default is ["user"], and a source that declares nothing
    must keep behaving exactly as before — this gate is additive."""
    assert can_query_semantic(roles=["user"], user_dept_ids=["d"], dept_id="d",
                              roles_allowed=[])
    assert can_query_semantic(roles=["user"], user_dept_ids=["d"], dept_id="d",
                              roles_allowed=None)


def test_roles_allowed_does_not_widen_the_dept_gate():
    """Having the role is necessary, not sufficient: a non-member is still out."""
    assert not can_query_semantic(
        roles=["dept_admin"], user_dept_ids=["finance"], dept_id="central_pmu",
        roles_allowed=["dept_admin"],
    )


def test_roles_allowed_does_not_block_org_admin_or_super_admin():
    """Platform admins keep their override — the same posture as the structured
    path, where auth.py grants org_admin above the role gate."""
    assert can_query_semantic(roles=["org_admin"], user_dept_ids=[], dept_id="d",
                              roles_allowed=["dept_admin"])
    assert can_query_semantic(roles=["super_admin"], user_dept_ids=[], dept_id="d",
                              roles_allowed=["nobody"])


def test_roles_allowed_still_applies_to_a_public_within_org_corpus():
    """public_within_org widens the DEPT gate, not the ROLE gate — otherwise
    marking a restricted corpus org-public would silently drop its allow-list."""
    assert not can_query_semantic(
        roles=["user"], user_dept_ids=["finance"], dept_id="central_pmu",
        public_within_org=True, roles_allowed=["dept_admin"],
    )
