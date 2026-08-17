# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""Main-chat semantic migration (RAG short-circuit).

Chat's ONLY source of truth is the discovery registry, which the MCP publishes at
boot. A source flagged ``source_type == "semantic"`` there is a RAG corpus: chat
surfaces it as a ``dept_*`` tool and dispatches it IN-PROCESS to the platform
reader (fetching the published ``rag_collection`` from Milvus directly), NEVER the
MCP ``/query`` — even though the registration still carries a ``query_endpoint``.
"""
from unittest.mock import AsyncMock, patch

import pytest

from services.enterprise_tools import (
    build_enterprise_tool_schemas,
    dispatch_enterprise_tool,
)


# ── build: a discovery source_type=semantic becomes an in-process RAG tool ───
@pytest.mark.asyncio
async def test_build_surfaces_semantic_tool_from_discovery():
    # A semantic source carries a query_endpoint in discovery (required field) —
    # chat MUST branch on source_type, not on the endpoint's presence, or it would
    # dispatch RAG to the MCP /query and 404 (the exact bug this fixes).
    tools = [{
        "source_id": "policy_lib", "name": "Policy Library", "description": "SOPs",
        "source_type": "semantic", "dept_ids": ["ops"],
        "rag_collection": "demo_ops_policy_lib",
        "query_endpoint": "http://mcp:8090/query",   # present but MUST be ignored
    }]
    with patch("services.enterprise_mcp_client.discover_tools",
               new=AsyncMock(return_value=tools)):
        schemas, name_map = await build_enterprise_tool_schemas(
            org_id="o", dept_ids=["ops"], roles=["user"])
    assert len(name_map) == 1
    tool_name, tool_def = next(iter(name_map.items()))
    assert tool_name.startswith("dept_")
    assert tool_def["kind"] == "semantic" and tool_def["source_id"] == "policy_lib"
    assert tool_def["dept_id"] == "ops"
    assert tool_def["rag_collection"] == "demo_ops_policy_lib"
    props = schemas[0]["function"]["parameters"]["properties"]
    assert "query" in props and "max_results" in props
    # semantic tools expose NO dataset_ids param (that's a structured-planner hint)
    assert "dataset_ids" not in props


@pytest.mark.asyncio
async def test_build_structured_tool_stays_structured():
    tools = [{
        "source_id": "billing", "name": "Billing", "description": "bills",
        "source_type": "structured", "dept_ids": ["fin"],
        "query_endpoint": "http://mcp:8090/query",
    }]
    with patch("services.enterprise_mcp_client.discover_tools",
               new=AsyncMock(return_value=tools)):
        schemas, name_map = await build_enterprise_tool_schemas(
            org_id="o", dept_ids=["fin"], roles=["user"])
    _, tool_def = next(iter(name_map.items()))
    assert tool_def.get("kind") != "semantic"
    assert tool_def["query_endpoint"].endswith("/query")
    # structured tools keep the dataset_ids planner hint
    assert "dataset_ids" in schemas[0]["function"]["parameters"]["properties"]


# ── dispatch: semantic routes in-process, NEVER the MCP ─────────────────────
@pytest.mark.asyncio
async def test_dispatch_semantic_routes_in_process_not_mcp():
    name_map = {"dept_policy": {"source_id": "policy_lib", "kind": "semantic",
                                "dept_id": "ops", "name": "Policy",
                                "rag_collection": "demo_ops_policy_lib"}}
    reader = AsyncMock(return_value=[
        {"text": "penalty clause", "score": 0.9, "metadata": {"doc_type": "policy"}},
        {"text": "seal broken", "score": 0.8, "metadata": {}},
    ])
    mcp = AsyncMock(return_value=[])
    with patch("semantic_reader.semantic_search", new=reader), \
         patch("services.enterprise_mcp_client.call_tool", new=mcp):
        res = await dispatch_enterprise_tool(
            name="dept_policy", args={"query": "meter tampering", "max_results": 3},
            name_map=name_map, jwt_token=None, user_id="u")
    assert res["success"] is True
    assert res["source_id"] == "policy_lib" and res["returned"] == 2
    assert res["results"][0]["text"] == "penalty clause"
    reader.assert_awaited_once()
    mcp.assert_not_awaited()                       # the MCP is NEVER hit for semantic
    kw = reader.await_args.kwargs
    assert kw["source_id"] == "policy_lib" and kw["dept_id"] == "ops"
    # the published collection is threaded to the reader for a direct Milvus fetch
    assert kw["collection"] == "demo_ops_policy_lib"


# ── build: the semantic tool exposes doc_path (whole-document read) ─────────
@pytest.mark.asyncio
async def test_build_semantic_tool_exposes_doc_path_param():
    tools = [{"source_id": "policy_lib", "name": "Policy", "description": "SOPs",
              "source_type": "semantic", "dept_ids": ["ops"],
              "rag_collection": "c", "query_endpoint": "http://mcp:8090/query"}]
    with patch("services.enterprise_mcp_client.discover_tools",
               new=AsyncMock(return_value=tools)):
        schemas, _ = await build_enterprise_tool_schemas(
            org_id="o", dept_ids=["ops"], roles=["user"])
    props = schemas[0]["function"]["parameters"]["properties"]
    assert "doc_path" in props        # lets the LLM read a whole document by path


# ── dispatch: doc_path routes to the whole-document fetch, NOT vector search ─
@pytest.mark.asyncio
async def test_dispatch_semantic_doc_path_fetches_whole_document():
    name_map = {"dept_policy": {"source_id": "policy_lib", "kind": "semantic",
                                "dept_id": "ops", "rag_collection": "demo_ops_policy_lib"}}
    fetch = AsyncMock(return_value=[{"text": "sec 1", "score": None, "metadata": {}},
                                    {"text": "sec 2", "score": None, "metadata": {}}])
    search = AsyncMock(return_value=[])
    with patch("semantic_reader.fetch_document", new=fetch), \
         patch("semantic_reader.semantic_search", new=search):
        res = await dispatch_enterprise_tool(
            name="dept_policy",
            args={"query": "read the whole SOP", "doc_path": "policy/dt_failure_response_sop.md"},
            name_map=name_map, user_id="u")
    assert res["success"] is True and res["returned"] == 2
    fetch.assert_awaited_once()
    search.assert_not_awaited()                    # whole-doc fetch, not top-k search
    kw = fetch.await_args.kwargs
    assert kw["doc_path"] == "policy/dt_failure_response_sop.md"
    assert kw["collection"] == "demo_ops_policy_lib"


@pytest.mark.asyncio
async def test_dispatch_semantic_doc_path_only_no_query_is_allowed():
    """A doc_path-only call (no query) must NOT be rejected — the tool tells the
    LLM to pass doc_path INSTEAD of a query for a whole-document read."""
    name_map = {"dept_policy": {"source_id": "policy_lib", "kind": "semantic",
                                "dept_id": "ops", "rag_collection": "c"}}
    fetch = AsyncMock(return_value=[{"text": "sec 1", "score": None, "metadata": {}}])
    with patch("semantic_reader.fetch_document", new=fetch), \
         patch("semantic_reader.semantic_search", new=AsyncMock(return_value=[])):
        res = await dispatch_enterprise_tool(
            name="dept_policy", args={"doc_path": "policy/x.md"},   # NO query
            name_map=name_map, user_id="u")
    assert res["success"] is True and res["returned"] == 1
    fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_semantic_no_query_no_doc_path_is_error():
    name_map = {"dept_policy": {"source_id": "policy_lib", "kind": "semantic",
                                "dept_id": "ops"}}
    res = await dispatch_enterprise_tool(
        name="dept_policy", args={}, name_map=name_map, user_id="u")
    assert res["success"] is False and "query" in res["error"].lower()


@pytest.mark.asyncio
async def test_dispatch_semantic_search_failure_is_tool_error():
    name_map = {"dept_policy": {"source_id": "policy_lib", "kind": "semantic",
                                "dept_id": "ops"}}
    with patch("semantic_reader.semantic_search",
               new=AsyncMock(side_effect=RuntimeError("milvus down"))):
        res = await dispatch_enterprise_tool(
            name="dept_policy", args={"query": "q"}, name_map=name_map, user_id="u")
    assert res["success"] is False and "milvus down" in res["error"]
