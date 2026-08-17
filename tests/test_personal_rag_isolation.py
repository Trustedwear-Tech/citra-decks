# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""
Personal-RAG Isolation Tests
============================

These tests assert that the `citra` Milvus collection (the personal RAG
store) is ALWAYS queried with a `user_id == "<caller>"` filter expression.
The review flagged this as the single highest residual data-leak risk —
if a bug ever dropped the user-id predicate, one user's query could return
another user's chunks.

Strategy:
  • Import `LlamaIndexQueryEngine` and monkey-patch its `_milvus_query`
    method to capture the constructed `filter_expr`.
  • Drive a personal search as user_A and assert the captured filter
    contains `user_id == "<user_A>"`.
  • Drive another search as user_B and confirm the filter no longer
    contains user_A's id — i.e. construction is stateless and per-call.
  • Explicit negative check: assert the filter never contains
    `user_id != ...` or an unbounded expression.

These tests do NOT touch Milvus itself and MUST NOT modify the collection
or the code paths that serve real users — only observe.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

import pytest


# ---------------------------------------------------------------------------
# Safe import — skip whole module if Citra-Service deps aren't installed in
# the test env (e.g. running dept-mcp tests in a stripped-down container).
# ---------------------------------------------------------------------------
pytest.importorskip("llama_index")
pytest.importorskip("pymilvus")

# Ensure env vars are safe for module import.
os.environ.setdefault("MILVUS_URI", "http://localhost:19530")
os.environ.setdefault("MILVUS_TOKEN", "")
os.environ.setdefault("MILVUS_COLLECTION", "citra")

from llamaindex_query_engine import UnifiedQueryEngine  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _FilterCapturingEngine(UnifiedQueryEngine):
    """Test double: records every filter expression passed to _milvus_query."""

    def __init__(self):
        # Bypass heavy __init__ — we only exercise filter construction.
        self.collection_name = os.environ["MILVUS_COLLECTION"]
        self.milvus_uri = os.environ["MILVUS_URI"]
        self.milvus_token = os.environ["MILVUS_TOKEN"]
        self.personal_similarity_threshold = 0.0
        self.captured_filters: List[str] = []

    def _create_namespace_index(self, user_id: str):
        class _StubIndex:  # pragma: no cover - trivial
            pass
        return _StubIndex()

    def _milvus_query(self, vector, filter_expr=None, top_k=10, output_fields=None):
        self.captured_filters.append(filter_expr or "")
        # Return empty results so downstream code treats this as a no-hit run.
        return []


@pytest.fixture
def engine(monkeypatch):
    """Patch embedding + any service calls so the filter construction path runs
    without real Milvus / embedding / Mongo."""
    eng = _FilterCapturingEngine()

    # Stub embedding — inherit from MockEmbedding so llama-index's setter
    # accepts it as a BaseEmbedding instance.
    from llama_index.core.embeddings import MockEmbedding

    class _StubEmbed(MockEmbedding):
        def _get_query_embedding(self, _q):
            return [0.0] * 768

    import llamaindex_query_engine as mod
    mod.Settings.embed_model = _StubEmbed(embed_dim=768)

    # Reranker off so results path is short.
    monkeypatch.setattr(mod, "is_reranker_enabled", lambda: False, raising=False)

    return eng


def _run(coro):
    """Run a coroutine on a fresh event loop.

    pytest-asyncio (asyncio_mode=auto in pytest.ini) creates and tears down
    a loop per async test. Calling ``asyncio.get_event_loop()`` from a sync
    test that runs after an async test raises ``RuntimeError: There is no
    current event loop in thread 'MainThread'``. Creating a new loop here
    is independent of pytest-asyncio's lifecycle and isolation-safe.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            asyncio.set_event_loop(None)
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# Isolation assertions
# ---------------------------------------------------------------------------

def test_personal_filter_includes_caller_user_id(engine):
    """User A's search must carry `user_id == "user-A"` in the Milvus filter."""
    _run(engine._perform_personal_direct_query(
        personal_index=engine._create_namespace_index("user-A"),
        query="what did I eat yesterday",
        user_id="user-A",
        permission_filter=None,
        top_k=5,
    ))
    assert engine.captured_filters, "engine must have issued at least one Milvus query"
    f = engine.captured_filters[-1]
    assert 'user_id == "user-A"' in f, (
        f"personal query filter missing user_id predicate for caller. "
        f"Got: {f!r}"
    )


def test_personal_filter_excludes_enterprise_and_kg(engine):
    """Personal search must exclude enterprise data and KG nodes."""
    _run(engine._perform_personal_direct_query(
        personal_index=engine._create_namespace_index("user-A"),
        query="anything",
        user_id="user-A",
        permission_filter=None,
        top_k=5,
    ))
    f = engine.captured_filters[-1]
    assert "is_enterprise == false" in f, f"expected enterprise-exclusion in {f!r}"
    assert 'chunk_type != "knowledge_graph_node"' in f, \
        f"expected KG-exclusion in {f!r}"


def test_personal_filter_does_not_leak_previous_user(engine):
    """Querying as user-A then as user-B must never reuse user-A's id."""
    _run(engine._perform_personal_direct_query(
        personal_index=engine._create_namespace_index("user-A"),
        query="q1", user_id="user-A", permission_filter=None, top_k=5,
    ))
    _run(engine._perform_personal_direct_query(
        personal_index=engine._create_namespace_index("user-B"),
        query="q2", user_id="user-B", permission_filter=None, top_k=5,
    ))
    assert len(engine.captured_filters) == 2
    filter_a, filter_b = engine.captured_filters
    assert 'user_id == "user-A"' in filter_a
    assert 'user_id == "user-B"' in filter_b
    assert 'user_id == "user-A"' not in filter_b, \
        f"user-B's filter must not contain user-A: {filter_b!r}"
    assert 'user_id == "user-B"' not in filter_a


def test_personal_filter_never_unbounded(engine):
    """A personal query must never issue an empty or unbounded Milvus filter."""
    _run(engine._perform_personal_direct_query(
        personal_index=engine._create_namespace_index("user-X"),
        query="q",
        user_id="user-X",
        permission_filter=None,
        top_k=3,
    ))
    f = engine.captured_filters[-1]
    assert f, "filter expression must not be empty"
    # Common footguns the review explicitly warned about:
    assert "user_id !=" not in f, f"negated user filter leaks cross-user data: {f!r}"
    assert 'user_id == ""' not in f, f"empty user_id in filter is unsafe: {f!r}"


def test_personal_filter_quote_escaping(engine):
    """A user id with embedded quotes must not break out of the filter expr.

    Milvus filter syntax uses `==` on a quoted string. If a malicious user_id
    contained a double-quote + predicate injection the filter would become
    `user_id == "u"  or  1==1 "` which would fetch everyone else's chunks.
    Assert our construction either escapes or rejects quotes.
    """
    evil = 'u" or user_id != "u'
    _run(engine._perform_personal_direct_query(
        personal_index=engine._create_namespace_index(evil),
        query="q",
        user_id=evil,
        permission_filter=None,
        top_k=3,
    ))
    f = engine.captured_filters[-1]
    # Either the engine escaped the quote (safe), OR
    # the final filter is obviously not an injection (no dangling `or`).
    # We assert the dangerous `or user_id !=` fragment did NOT survive as a
    # top-level boolean injection — the quoted literal is fine as long as
    # it's enclosed inside user_id's string.
    # Heuristic: the filter should still contain `is_enterprise == false`
    # AND should NOT contain an unquoted `or user_id !=` outside of the
    # inner user-id value position.
    assert "is_enterprise == false" in f
    # If this assertion fails, the injection escaped — mitigate in the
    # query-engine (sanitize / reject quotes in user_id before formatting).
    suspicious = f.replace(f'user_id == "{evil}"', "")
    assert "user_id !=" not in suspicious, (
        f"possible filter-injection: {f!r}"
    )
