# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""Tests for ``services.personal_data_tool``.

Personal-vault retrieval as an LLM-callable tool (symmetric with `dept_*`
enterprise MCP tools). These tests mock the underlying Milvus retriever
(`RETRIEVAL_TOOLS["personal"]`) and the simplified planner so we exercise
the schema builder + dispatcher without any real Milvus / LLM calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

import pytest

from services.personal_data_tool import (
    DEFAULT_RESULTS_PER_CALL,
    MAX_RESULTS_PER_CALL,
    TOOL_NAME,
    build_personal_data_tool_schema,
    dispatch_personal_data_tool,
)


# ─── Schema builder ────────────────────────────────────────────────────────


def test_schema_basic_shape():
    schema = build_personal_data_tool_schema(folder_ids=["f1", "f2"])
    assert schema["type"] == "function"
    fn = schema["function"]
    assert fn["name"] == TOOL_NAME
    params = fn["parameters"]
    assert params["type"] == "object"
    assert "query" in params["required"]
    props = params["properties"]
    assert set(props.keys()) >= {"query", "max_results", "document_ids"}
    assert props["query"]["type"] == "string"
    assert props["max_results"]["type"] == "integer"
    assert props["max_results"]["minimum"] == 1


def test_schema_default_max_when_no_cap():
    schema = build_personal_data_tool_schema(folder_ids=["f1"])
    maxv = schema["function"]["parameters"]["properties"]["max_results"]["maximum"]
    assert maxv == MAX_RESULTS_PER_CALL


def test_schema_honours_explicit_cap():
    schema = build_personal_data_tool_schema(folder_ids=["f1"], max_results_cap=3)
    maxv = schema["function"]["parameters"]["properties"]["max_results"]["maximum"]
    assert maxv == 3
    # Description must reflect the lower cap so the LLM sees the right ceiling
    desc = schema["function"]["description"]
    assert "up to 3 reranked chunks" in desc


def test_schema_cap_clamped_to_global_max():
    # cap > global ceiling should be clamped down to MAX_RESULTS_PER_CALL
    schema = build_personal_data_tool_schema(
        folder_ids=["f1"], max_results_cap=MAX_RESULTS_PER_CALL + 100
    )
    maxv = schema["function"]["parameters"]["properties"]["max_results"]["maximum"]
    assert maxv == MAX_RESULTS_PER_CALL


def test_schema_cap_minimum_one():
    # cap=0 or negative is coerced up to at least 1
    schema = build_personal_data_tool_schema(folder_ids=["f1"], max_results_cap=0)
    maxv = schema["function"]["parameters"]["properties"]["max_results"]["maximum"]
    assert maxv >= 1


def test_schema_describes_folder_scope():
    schema = build_personal_data_tool_schema(folder_ids=["fa", "fb", "fc"])
    desc = schema["function"]["description"]
    assert "scoped to 3 selected folder(s)" in desc


def test_schema_describes_full_vault_when_no_folders():
    schema = build_personal_data_tool_schema(folder_ids=None)
    desc = schema["function"]["description"]
    assert "across the user's full vault" in desc


def test_schema_with_file_metadata_nudge():
    schema_with = build_personal_data_tool_schema(folder_ids=["f1"], has_file_metadata=True)
    schema_without = build_personal_data_tool_schema(folder_ids=["f1"], has_file_metadata=False)
    assert "system prompt already lists" in schema_with["function"]["description"]
    assert "system prompt already lists" not in schema_without["function"]["description"]


# ─── Dispatcher ────────────────────────────────────────────────────────────


def _stub_personal_tool(returns):
    """Build a stub PersonalDataTool with .retrieve returning ``returns``."""
    stub = MagicMock()
    stub.retrieve = AsyncMock(return_value=returns)
    return stub


@pytest.mark.asyncio
async def test_dispatch_rejects_missing_user_id():
    out = await dispatch_personal_data_tool(args={"query": "q"}, user_id="")
    assert out["success"] is False
    assert "user_id" in out["error"].lower()


@pytest.mark.asyncio
async def test_dispatch_rejects_empty_query():
    out = await dispatch_personal_data_tool(args={"query": "   "}, user_id="u1")
    assert out["success"] is False
    assert "query" in out["error"].lower()


@pytest.mark.asyncio
async def test_dispatch_returns_results():
    chunks = [
        {"text": "alpha", "score": 0.9, "metadata": {"document_id": "d1", "filename": "a.pdf"}},
        {"text": "beta", "score": 0.8, "metadata": {"document_id": "d2"}},
    ]
    stub = _stub_personal_tool(chunks)
    with patch.dict(
        "agentic_rag.tools.RETRIEVAL_TOOLS", {"personal": stub}
    ), patch(
        "services.personal_data_tool._expand_subqueries",
        new=AsyncMock(return_value=["q"]),
    ):
        out = await dispatch_personal_data_tool(
            args={"query": "q", "max_results": 5},
            user_id="u1",
            folder_ids=["f1"],
        )
    assert out["success"] is True
    assert out["returned"] == 2
    assert out["folder_scope"] == ["f1"]
    # Top-level hoisted fields
    assert out["results"][0]["document_id"] == "d1"
    assert out["results"][0]["filename"] == "a.pdf"
    # Underlying retriever got the right scope
    stub.retrieve.assert_awaited()


@pytest.mark.asyncio
async def test_dispatch_enforces_max_results_cap():
    """Even if LLM passes max_results=99, the cap clamps it."""
    chunks = [
        {"text": f"chunk-{i}", "score": 1.0 - i * 0.01, "metadata": {"document_id": f"d{i}"}}
        for i in range(20)
    ]
    stub = _stub_personal_tool(chunks)
    with patch.dict(
        "agentic_rag.tools.RETRIEVAL_TOOLS", {"personal": stub}
    ), patch(
        "services.personal_data_tool._expand_subqueries",
        new=AsyncMock(return_value=["q"]),
    ):
        out = await dispatch_personal_data_tool(
            args={"query": "q", "max_results": 99},
            user_id="u1",
            folder_ids=["f1"],
            max_results_cap=3,
        )
    assert out["success"] is True
    # Cap=3 must be enforced regardless of LLM's request
    assert out["returned"] == 3
    assert len(out["results"]) == 3
    assert out["truncated"] is True


@pytest.mark.asyncio
async def test_dispatch_uses_default_when_no_max_results():
    chunks = [
        {"text": f"c{i}", "score": 1.0, "metadata": {"document_id": f"d{i}"}}
        for i in range(50)
    ]
    stub = _stub_personal_tool(chunks)
    with patch.dict(
        "agentic_rag.tools.RETRIEVAL_TOOLS", {"personal": stub}
    ), patch(
        "services.personal_data_tool._expand_subqueries",
        new=AsyncMock(return_value=["q"]),
    ):
        out = await dispatch_personal_data_tool(
            args={"query": "q"},
            user_id="u1",
            folder_ids=["f1"],
        )
    assert out["returned"] == DEFAULT_RESULTS_PER_CALL


@pytest.mark.asyncio
async def test_dispatch_filters_by_document_ids():
    chunks = [
        {"text": "a", "score": 0.9, "metadata": {"document_id": "doc-keep"}},
        {"text": "b", "score": 0.8, "metadata": {"document_id": "doc-skip"}},
        {"text": "c", "score": 0.7, "metadata": {"document_id": "doc-keep"}},
    ]
    stub = _stub_personal_tool(chunks)
    with patch.dict(
        "agentic_rag.tools.RETRIEVAL_TOOLS", {"personal": stub}
    ), patch(
        "services.personal_data_tool._expand_subqueries",
        new=AsyncMock(return_value=["q"]),
    ):
        out = await dispatch_personal_data_tool(
            args={"query": "q", "document_ids": ["doc-keep"]},
            user_id="u1",
            folder_ids=["f1"],
        )
    assert out["success"] is True
    assert out["returned"] == 2
    assert all(r["document_id"] == "doc-keep" for r in out["results"])


@pytest.mark.asyncio
async def test_dispatch_dedupes_by_chunk_id():
    duplicate_chunk = {
        "text": "dup",
        "score": 0.9,
        "metadata": {"chunk_id": "chunk-x", "document_id": "d1"},
    }
    chunks = [duplicate_chunk, duplicate_chunk, duplicate_chunk]
    stub = _stub_personal_tool(chunks)
    with patch.dict(
        "agentic_rag.tools.RETRIEVAL_TOOLS", {"personal": stub}
    ), patch(
        "services.personal_data_tool._expand_subqueries",
        new=AsyncMock(return_value=["q"]),
    ):
        out = await dispatch_personal_data_tool(
            args={"query": "q"}, user_id="u1", folder_ids=["f1"]
        )
    assert out["returned"] == 1


@pytest.mark.asyncio
async def test_dispatch_sorts_by_score_desc():
    chunks = [
        {"text": "low", "score": 0.1, "metadata": {"document_id": "d1"}},
        {"text": "high", "score": 0.9, "metadata": {"document_id": "d2"}},
        {"text": "mid", "score": 0.5, "metadata": {"document_id": "d3"}},
    ]
    stub = _stub_personal_tool(chunks)
    with patch.dict(
        "agentic_rag.tools.RETRIEVAL_TOOLS", {"personal": stub}
    ), patch(
        "services.personal_data_tool._expand_subqueries",
        new=AsyncMock(return_value=["q"]),
    ):
        out = await dispatch_personal_data_tool(
            args={"query": "q"}, user_id="u1", folder_ids=["f1"]
        )
    scores = [r["score"] for r in out["results"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_dispatch_returns_error_dict_when_retriever_raises():
    stub = MagicMock()
    stub.retrieve = AsyncMock(side_effect=RuntimeError("milvus down"))
    with patch.dict(
        "agentic_rag.tools.RETRIEVAL_TOOLS", {"personal": stub}
    ), patch(
        "services.personal_data_tool._expand_subqueries",
        new=AsyncMock(return_value=["q"]),
    ):
        out = await dispatch_personal_data_tool(
            args={"query": "q"}, user_id="u1", folder_ids=["f1"]
        )
    assert out["success"] is False
    assert "milvus down" in out["error"]


@pytest.mark.asyncio
async def test_dispatch_passes_folder_scope_to_retriever():
    """Folder scope from the caller MUST flow into the retriever — the LLM
    can't widen it because the schema doesn't expose folder_ids as an arg."""
    stub = _stub_personal_tool([])
    with patch.dict(
        "agentic_rag.tools.RETRIEVAL_TOOLS", {"personal": stub}
    ), patch(
        "services.personal_data_tool._expand_subqueries",
        new=AsyncMock(return_value=["q"]),
    ):
        await dispatch_personal_data_tool(
            args={"query": "q"},
            user_id="u1",
            folder_ids=["folder-a", "folder-b"],
        )
    call_kwargs = stub.retrieve.await_args.kwargs
    assert call_kwargs["selected_folder_ids"] == ["folder-a", "folder-b"]
    assert call_kwargs["folder_search_enabled"] is True


@pytest.mark.asyncio
async def test_dispatch_no_folder_scope_disables_folder_search():
    stub = _stub_personal_tool([])
    with patch.dict(
        "agentic_rag.tools.RETRIEVAL_TOOLS", {"personal": stub}
    ), patch(
        "services.personal_data_tool._expand_subqueries",
        new=AsyncMock(return_value=["q"]),
    ):
        await dispatch_personal_data_tool(args={"query": "q"}, user_id="u1")
    call_kwargs = stub.retrieve.await_args.kwargs
    assert call_kwargs["folder_search_enabled"] is False


@pytest.mark.asyncio
async def test_dispatch_subquery_expansion_fans_out():
    """When subquery expansion produces multiple queries, the retriever
    is called once per sub-query; results are then merged + dedup'd."""
    sub_queries = ["q1", "q2", "q3"]

    # Each sub-query returns one unique chunk
    call_log = []

    async def fake_retrieve(*args, **kwargs):
        q = kwargs.get("query")
        call_log.append(q)
        return [{"text": q, "score": 0.5, "metadata": {"document_id": f"doc-{q}"}}]

    stub = MagicMock()
    stub.retrieve = AsyncMock(side_effect=fake_retrieve)

    with patch.dict(
        "agentic_rag.tools.RETRIEVAL_TOOLS", {"personal": stub}
    ), patch(
        "services.personal_data_tool._expand_subqueries",
        new=AsyncMock(return_value=sub_queries),
    ):
        out = await dispatch_personal_data_tool(
            args={"query": "original"}, user_id="u1", folder_ids=["f1"]
        )
    assert call_log == sub_queries
    assert out["sub_queries_used"] == sub_queries
    assert out["returned"] == 3
