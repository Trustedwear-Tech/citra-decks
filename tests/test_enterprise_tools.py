# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""Tests for ``services.enterprise_tools``.

These tests mock the underlying discovery + MCP-call helpers so we exercise
schema-building and dispatch without any real network calls.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.enterprise_tools import (
    MAX_RESULTS_PER_CALL,
    MAX_TOOLS,
    build_enterprise_tool_schemas,
    dispatch_enterprise_tool,
)


def _make_tool_def(idx: int = 0, source_id: str | None = None, **overrides):
    base = {
        "name": f"tool-{idx}",
        "description": f"Description for tool {idx}",
        "query_endpoint": f"http://dept-mcp-{idx}.local/query",
        "source_id": source_id if source_id is not None else f"src-{idx}",
        "tool_id": f"tid-{idx}",
        "data_types": ["table", "metric"],
        "tags": ["finance"],
    }
    base.update(overrides)
    return base


# ─── build_enterprise_tool_schemas ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_schemas_returns_one_per_def():
    defs = [_make_tool_def(i) for i in range(3)]
    with patch("services.enterprise_mcp_client.discover_tools", new=AsyncMock(return_value=defs)):
        schemas, name_map = await build_enterprise_tool_schemas(
            org_id="org1", dept_ids=["d1"], roles=["user"], jwt_token="jwt"
        )
    assert len(schemas) == 3
    assert len(name_map) == 3
    for s in schemas:
        assert s["type"] == "function"
        fn = s["function"]
        assert fn["name"].startswith("dept_")
        assert "query" in fn["parameters"]["required"]
        props = fn["parameters"]["properties"]
        assert "query" in props and props["query"]["type"] == "string"
        assert "max_results" in props and props["max_results"]["maximum"] == MAX_RESULTS_PER_CALL


@pytest.mark.asyncio
async def test_build_schemas_caps_at_max_tools():
    defs = [_make_tool_def(i) for i in range(MAX_TOOLS + 10)]
    with patch("services.enterprise_mcp_client.discover_tools", new=AsyncMock(return_value=defs)):
        schemas, name_map = await build_enterprise_tool_schemas(
            org_id="org1", roles=["user"]
        )
    assert len(schemas) == MAX_TOOLS
    assert len(name_map) == MAX_TOOLS


@pytest.mark.asyncio
async def test_build_schemas_skips_defs_without_endpoint():
    defs = [
        _make_tool_def(0),
        _make_tool_def(1, query_endpoint=""),
        _make_tool_def(2),
    ]
    with patch("services.enterprise_mcp_client.discover_tools", new=AsyncMock(return_value=defs)):
        schemas, name_map = await build_enterprise_tool_schemas(org_id="o", roles=["user"])
    assert len(schemas) == 2
    assert all(name in name_map for name in [s["function"]["name"] for s in schemas])


@pytest.mark.asyncio
async def test_build_schemas_disambiguates_duplicate_source_ids():
    defs = [_make_tool_def(0, source_id="same"), _make_tool_def(1, source_id="same")]
    with patch("services.enterprise_mcp_client.discover_tools", new=AsyncMock(return_value=defs)):
        schemas, name_map = await build_enterprise_tool_schemas(org_id="o", roles=["user"])
    names = {s["function"]["name"] for s in schemas}
    assert len(names) == 2  # disambiguated


@pytest.mark.asyncio
async def test_build_schemas_sanitises_source_id_chars():
    defs = [_make_tool_def(0, source_id="weird name!@#$%")]
    with patch("services.enterprise_mcp_client.discover_tools", new=AsyncMock(return_value=defs)):
        schemas, _ = await build_enterprise_tool_schemas(org_id="o", roles=["user"])
    name = schemas[0]["function"]["name"]
    assert name.startswith("dept_")
    # OpenAI function-name regex
    import re
    assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name)


@pytest.mark.asyncio
async def test_build_schemas_returns_empty_when_no_defs():
    with patch("services.enterprise_mcp_client.discover_tools", new=AsyncMock(return_value=[])):
        schemas, name_map = await build_enterprise_tool_schemas(org_id="o", roles=["user"])
    assert schemas == []
    assert name_map == {}


@pytest.mark.asyncio
async def test_build_schemas_fails_loud_on_discovery_error():
    """A discovery OUTAGE must NOT silently degrade to zero enterprise tools —
    build raises DiscoveryUnavailableError so the caller can surface it (RULE #1).
    Contrast with test_build_schemas_returns_empty_when_no_defs: a SUCCESSFUL
    discovery returning [] (genuine no-sources) still returns ([], {})."""
    from services.enterprise_mcp_client import DiscoveryUnavailableError
    with patch(
        "services.enterprise_mcp_client.discover_tools",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(DiscoveryUnavailableError):
            await build_enterprise_tool_schemas(org_id="o", roles=["user"])


# ─── dispatch_enterprise_tool ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_returns_error():
    out = await dispatch_enterprise_tool(
        name="dept_unknown", args={"query": "x"}, name_map={}, jwt_token=None
    )
    assert out["success"] is False
    assert "Unknown" in out["error"]


@pytest.mark.asyncio
async def test_dispatch_missing_query_returns_error():
    name_map = {"dept_x": _make_tool_def(0, source_id="x")}
    out = await dispatch_enterprise_tool(
        name="dept_x", args={}, name_map=name_map, jwt_token=None
    )
    assert out["success"] is False
    assert "query" in out["error"].lower()


@pytest.mark.asyncio
async def test_dispatch_calls_mcp_and_shapes_results():
    name_map = {"dept_x": _make_tool_def(0, source_id="src1")}
    raw_results = [
        {"text": "row 1", "score": 0.9, "source": "s", "metadata": {"k": "v"}},
        {"text": "row 2", "score": 0.8, "source": "s", "metadata": {"k": "v2"}},
    ]
    with patch(
        "services.enterprise_mcp_client.call_tool",
        new=AsyncMock(return_value=raw_results),
    ), patch(
        "services.enterprise_mcp_client.service_api_key",
        return_value="apikey",
    ):
        out = await dispatch_enterprise_tool(
            name="dept_x",
            args={"query": "what is x", "max_results": 50},  # exceeds cap
            name_map=name_map,
            jwt_token=None,
            user_id="u1",
        )
    assert out["success"] is True
    assert out["source_id"] == "src1"
    assert out["total"] == 2
    assert out["returned"] == 2
    assert len(out["results"]) == 2
    assert out["results"][0]["text"] == "row 1"


@pytest.mark.asyncio
async def test_dispatch_truncates_long_text():
    long_text = "x" * 5000
    name_map = {"dept_x": _make_tool_def(0, source_id="src1")}
    raw_results = [{"text": long_text, "score": 0.5, "source": "s"}]
    with patch(
        "services.enterprise_mcp_client.call_tool",
        new=AsyncMock(return_value=raw_results),
    ), patch(
        "services.enterprise_mcp_client.service_api_key",
        return_value="apikey",
    ):
        out = await dispatch_enterprise_tool(
            name="dept_x", args={"query": "q"}, name_map=name_map
        )
    assert out["success"] is True
    assert len(out["results"][0]["text"]) < len(long_text)


@pytest.mark.asyncio
async def test_dispatch_caps_results_at_max_per_call():
    name_map = {"dept_x": _make_tool_def(0, source_id="src1")}
    raw_results = [{"text": f"r{i}", "score": 0.1} for i in range(MAX_RESULTS_PER_CALL + 5)]
    with patch(
        "services.enterprise_mcp_client.call_tool",
        new=AsyncMock(return_value=raw_results),
    ), patch(
        "services.enterprise_mcp_client.service_api_key",
        return_value="apikey",
    ):
        # Default max_results when not provided
        out = await dispatch_enterprise_tool(
            name="dept_x", args={"query": "q"}, name_map=name_map
        )
    assert out["truncated"] is True
    assert out["total"] == MAX_RESULTS_PER_CALL + 5
    assert len(out["results"]) <= MAX_RESULTS_PER_CALL


@pytest.mark.asyncio
async def test_dispatch_returns_error_on_mcp_exception():
    name_map = {"dept_x": _make_tool_def(0, source_id="src1")}
    with patch(
        "services.enterprise_mcp_client.call_tool",
        new=AsyncMock(side_effect=RuntimeError("network down")),
    ), patch(
        "services.enterprise_mcp_client.service_api_key",
        return_value="apikey",
    ):
        out = await dispatch_enterprise_tool(
            name="dept_x", args={"query": "q"}, name_map=name_map
        )
    assert out["success"] is False
    assert "network down" in out["error"]
    assert out["source_id"] == "src1"


@pytest.mark.asyncio
async def test_dispatch_forwards_raw_user_jwt():
    """The caller's HS256 session token is forwarded verbatim as X-User-JWT."""
    name_map = {"dept_x": _make_tool_def(0, source_id="src1")}
    captured = {}

    async def fake_call_mcp(**kwargs):
        captured.update(kwargs)
        return []

    with patch("services.enterprise_mcp_client.call_tool", new=fake_call_mcp), patch(
        "services.enterprise_mcp_client.service_api_key", return_value="apikey"
    ):
        out = await dispatch_enterprise_tool(
            name="dept_x",
            args={"query": "q"},
            name_map=name_map,
            jwt_token="user-jwt",
        )
    assert out["success"] is True
    assert captured["user_jwt"] == "user-jwt"
    assert captured["api_key"] == "apikey"
    assert captured["source_id"] == "src1"


@pytest.mark.asyncio
async def test_dispatch_plumbs_max_results_to_mcp_call():
    name_map = {"dept_x": _make_tool_def(0, source_id="src1")}
    captured = {}

    async def fake_call_mcp(**kwargs):
        captured.update(kwargs)
        return []

    with patch("services.enterprise_mcp_client.call_tool", new=fake_call_mcp), patch(
        "services.enterprise_mcp_client.service_api_key", return_value="apikey"
    ):
        await dispatch_enterprise_tool(
            name="dept_x",
            args={"query": "q", "max_results": 17},
            name_map=name_map,
        )
    assert captured["max_results"] == 17


@pytest.mark.asyncio
async def test_dispatch_clamps_max_results_above_limit():
    name_map = {"dept_x": _make_tool_def(0, source_id="src1")}
    captured = {}

    async def fake_call_mcp(**kwargs):
        captured.update(kwargs)
        return []

    with patch("services.enterprise_mcp_client.call_tool", new=fake_call_mcp), patch(
        "services.enterprise_mcp_client.service_api_key", return_value="apikey"
    ):
        await dispatch_enterprise_tool(
            name="dept_x",
            args={"query": "q", "max_results": 9999},
            name_map=name_map,
        )
    assert captured["max_results"] == MAX_RESULTS_PER_CALL


# ─── call_tool fail-loud contract (regression: failure must NOT look empty) ──
#
# Root cause of the ACME-POWER "weather=5" hallucination: call_tool swallowed a 30s
# MCP timeout into `return []`, so dispatch reported success=True/total=0 and the
# LLM treated "the source didn't answer" as "the source has no such data" and
# fabricated the missing buckets. These guard the fixed behaviour: a FAILED call
# raises MCPCallError (→ dispatch success=False); a genuine empty 200 stays [].


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = "" if status < 400 else "boom"

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("err", request=None, response=self)

    def json(self):
        return self._payload


def _fake_async_client(post_impl):
    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return await post_impl(*a, **k)

    return _C


@pytest.mark.asyncio
async def test_call_tool_raises_on_timeout_not_empty(monkeypatch):
    import httpx
    from services.enterprise_mcp_client import call_tool, MCPCallError

    async def _timeout_post(*a, **k):
        raise httpx.ReadTimeout("")  # str(ReadTimeout) is empty — the bug's tell

    monkeypatch.setattr(
        "services.enterprise_mcp_client.httpx.AsyncClient",
        _fake_async_client(_timeout_post),
    )
    with pytest.raises(MCPCallError) as ei:
        await call_tool(
            query_endpoint="http://unique-timeout-endpoint.local/query",
            query="summary of transformer outage",
            source_id="outage_management",
            api_key="k",
            tool_def={"source_type": "structured"},
        )
    msg = str(ei.value).lower()
    assert "timed out" in msg and "outage_management" in msg


@pytest.mark.asyncio
async def test_call_tool_raises_on_http_error_not_empty(monkeypatch):
    from services.enterprise_mcp_client import call_tool, MCPCallError

    async def _500_post(*a, **k):
        return _FakeResp({"detail": "planner crashed"}, status=500)

    monkeypatch.setattr(
        "services.enterprise_mcp_client.httpx.AsyncClient",
        _fake_async_client(_500_post),
    )
    with pytest.raises(MCPCallError):
        await call_tool(
            query_endpoint="http://unique-500-endpoint.local/query",
            query="q",
            source_id="src1",
            api_key="k",
        )


@pytest.mark.asyncio
async def test_call_tool_empty_200_still_returns_empty_list(monkeypatch):
    """A genuine HTTP 200 with zero rows is NOT a failure — must stay []."""
    from services.enterprise_mcp_client import call_tool

    async def _empty_post(*a, **k):
        return _FakeResp({"results": []})

    monkeypatch.setattr(
        "services.enterprise_mcp_client.httpx.AsyncClient",
        _fake_async_client(_empty_post),
    )
    out = await call_tool(
        query_endpoint="http://unique-empty-endpoint.local/query",
        query="q",
        source_id="src1",
        api_key="k",
    )
    assert out == []


@pytest.mark.asyncio
async def test_dispatch_surfaces_timeout_as_success_false(monkeypatch):
    """End-to-end: a timed-out MCP call reaches the LLM as success=False with a
    real error message — never as success=True/total=0 (which it would fabricate
    around)."""
    import httpx
    from services.enterprise_mcp_client import MCPCallError

    name_map = {"dept_x": _make_tool_def(0, source_id="outage_management")}

    async def _raise_timeout(**kwargs):
        raise MCPCallError("query to 'outage_management' timed out after 30s")

    with patch("services.enterprise_mcp_client.call_tool", new=_raise_timeout), patch(
        "services.enterprise_mcp_client.service_api_key", return_value="apikey"
    ):
        out = await dispatch_enterprise_tool(
            name="dept_x", args={"query": "q"}, name_map=name_map
        )
    assert out["success"] is False
    assert "timed out" in out["error"]
    assert out.get("total", 0) == 0


# ─── OpenAI schema validation ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schema_shape_matches_openai_function_calling():
    defs = [_make_tool_def(0)]
    with patch("services.enterprise_mcp_client.discover_tools", new=AsyncMock(return_value=defs)):
        schemas, _ = await build_enterprise_tool_schemas(org_id="o", roles=["user"])
    s = schemas[0]
    assert set(s.keys()) == {"type", "function"}
    fn = s["function"]
    assert set(fn.keys()) >= {"name", "description", "parameters"}
    params = fn["parameters"]
    assert params["type"] == "object"
    assert "properties" in params and "required" in params


# ─── max_results_cap on schemas ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schema_default_max_when_no_cap():
    defs = [_make_tool_def(0)]
    with patch("services.enterprise_mcp_client.discover_tools", new=AsyncMock(return_value=defs)):
        schemas, _ = await build_enterprise_tool_schemas(org_id="o", roles=["user"])
    maxv = schemas[0]["function"]["parameters"]["properties"]["max_results"]["maximum"]
    assert maxv == MAX_RESULTS_PER_CALL


@pytest.mark.asyncio
async def test_schema_honours_explicit_cap():
    """Per-feature cap should override the global default in the OpenAI schema."""
    defs = [_make_tool_def(0)]
    with patch("services.enterprise_mcp_client.discover_tools", new=AsyncMock(return_value=defs)):
        schemas, _ = await build_enterprise_tool_schemas(
            org_id="o", roles=["user"], max_results_cap=3
        )
    props = schemas[0]["function"]["parameters"]["properties"]
    assert props["max_results"]["maximum"] == 3
    assert "max 3" in props["max_results"]["description"]


@pytest.mark.asyncio
async def test_schema_cap_clamped_to_global_max():
    defs = [_make_tool_def(0)]
    with patch("services.enterprise_mcp_client.discover_tools", new=AsyncMock(return_value=defs)):
        schemas, _ = await build_enterprise_tool_schemas(
            org_id="o", roles=["user"], max_results_cap=MAX_RESULTS_PER_CALL + 100
        )
    maxv = schemas[0]["function"]["parameters"]["properties"]["max_results"]["maximum"]
    assert maxv == MAX_RESULTS_PER_CALL


# ─── max_results_cap on dispatcher ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_enforces_max_results_cap():
    """Even if the LLM passes max_results=99, the dispatcher cap clamps it."""
    name_map = {"dept_x": _make_tool_def(0, source_id="src1")}
    captured = {}

    async def fake_call_mcp(**kwargs):
        captured["max_results"] = kwargs.get("max_results")
        return [{"text": f"r{i}", "score": 0.5} for i in range(20)]

    with patch("services.enterprise_mcp_client.call_tool", new=fake_call_mcp), patch(
        "services.enterprise_mcp_client.service_api_key", return_value="k"
    ):
        out = await dispatch_enterprise_tool(
            name="dept_x",
            args={"query": "q", "max_results": 99},
            name_map=name_map,
            max_results_cap=3,
        )
    # Cap=3 must override the LLM's 99 at the dispatcher layer
    assert captured["max_results"] == 3
    assert out["success"] is True
    assert out["returned"] == 3


@pytest.mark.asyncio
async def test_dispatch_default_when_no_cap_passed():
    """Without an explicit cap, the global default is used."""
    from services.enterprise_tools import DEFAULT_RESULTS_PER_CALL
    name_map = {"dept_x": _make_tool_def(0, source_id="src1")}
    captured = {}

    async def fake_call_mcp(**kwargs):
        captured["max_results"] = kwargs.get("max_results")
        return []

    with patch("services.enterprise_mcp_client.call_tool", new=fake_call_mcp), patch(
        "services.enterprise_mcp_client.service_api_key", return_value="k"
    ):
        await dispatch_enterprise_tool(
            name="dept_x",
            args={"query": "q"},
            name_map=name_map,
        )
    assert captured["max_results"] == DEFAULT_RESULTS_PER_CALL


# ─── run_Enterprise_or_Personal_tool — agentic helper ────────────────────────────


def _stub_llm_completion(*, content=None, tool_calls=None, usage_in=10, usage_out=5):
    """Build a minimal openai-style chat completion response."""
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=msg, finish_reason="stop")
    usage = SimpleNamespace(prompt_tokens=usage_in, completion_tokens=usage_out)
    return SimpleNamespace(choices=[choice], usage=usage)


def _make_tool_call(*, call_id, name, arguments):
    fn = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(id=call_id, function=fn, type="function")


@pytest.mark.asyncio
async def test_run_Enterprise_or_Personal_tool_no_tool_calls_returns_text():
    """Plain answer (no tool calls) is returned verbatim."""
    from services.enterprise_tools import run_Enterprise_or_Personal_tool

    fake_resp = _stub_llm_completion(content="Direct answer.")
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    with patch("services.enterprise_mcp_client.discover_tools", new=AsyncMock(return_value=[])), \
         patch("citra_llm.get_llm_client", return_value=fake_client), \
         patch("citra_llm.get_llm_model", return_value="test-model"), \
         patch("citra_llm.get_llm_extra_body", return_value={}):
        out = await run_Enterprise_or_Personal_tool(prompt="hi", system="sys")
    assert out == "Direct answer."


@pytest.mark.asyncio
async def test_run_Enterprise_or_Personal_tool_registers_personal_when_enabled():
    """When use_personal_data=True and user_id is set, personal_data_tool is in the tool palette."""
    from services.enterprise_tools import run_Enterprise_or_Personal_tool
    from types import SimpleNamespace as SN
    captured_tools = {}

    async def fake_create(**kwargs):
        captured_tools["tools"] = kwargs.get("tools")
        return _stub_llm_completion(content="done")

    fake_client = SN(chat=SN(completions=SN(create=fake_create)))

    with patch("services.enterprise_mcp_client.discover_tools", new=AsyncMock(return_value=[])), \
         patch("citra_llm.get_llm_client", return_value=fake_client), \
         patch("citra_llm.get_llm_model", return_value="test-model"), \
         patch("citra_llm.get_llm_extra_body", return_value={}):
        await run_Enterprise_or_Personal_tool(
            prompt="hi",
            user_id="u1",
            use_personal_data=True,
            selected_folder_ids=["f1"],
        )
    tools = captured_tools["tools"] or []
    names = [t["function"]["name"] for t in tools]
    assert "personal_data_tool" in names


@pytest.mark.asyncio
async def test_run_Enterprise_or_Personal_tool_no_personal_when_disabled():
    """When use_personal_data=False, personal_data_tool is NOT registered."""
    from services.enterprise_tools import run_Enterprise_or_Personal_tool
    from types import SimpleNamespace as SN
    captured = {}

    async def fake_create(**kwargs):
        captured["tools"] = kwargs.get("tools") or []
        return _stub_llm_completion(content="done")

    fake_client = SN(chat=SN(completions=SN(create=fake_create)))

    with patch("services.enterprise_mcp_client.discover_tools", new=AsyncMock(return_value=[])), \
         patch("citra_llm.get_llm_client", return_value=fake_client), \
         patch("citra_llm.get_llm_model", return_value="test-model"), \
         patch("citra_llm.get_llm_extra_body", return_value={}):
        await run_Enterprise_or_Personal_tool(
            prompt="hi", user_id="u1", use_personal_data=False, selected_folder_ids=["f1"]
        )
    names = [t["function"]["name"] for t in captured["tools"]]
    assert "personal_data_tool" not in names


@pytest.mark.asyncio
async def test_run_Enterprise_or_Personal_tool_dispatches_personal_tool_call():
    """When the LLM calls personal_data_tool, the dispatcher fires with bound folder scope + cap."""
    from services.enterprise_tools import run_Enterprise_or_Personal_tool
    from types import SimpleNamespace as SN
    dispatch_calls = []

    async def fake_dispatch_personal(**kwargs):
        dispatch_calls.append(kwargs)
        return {"success": True, "results": [{"text": "x"}], "returned": 1}

    # First LLM round emits a personal_data_tool call; second round produces text.
    tool_call = _make_tool_call(call_id="tc1", name="personal_data_tool", arguments='{"query": "x"}')
    resp_with_tool = _stub_llm_completion(content=None, tool_calls=[tool_call])
    resp_final = _stub_llm_completion(content="final answer")

    create_responses = [resp_with_tool, resp_final]
    create_iter = iter(create_responses)

    async def fake_create(**_kwargs):
        return next(create_iter)

    fake_client = SN(chat=SN(completions=SN(create=fake_create)))

    with patch("services.enterprise_mcp_client.discover_tools", new=AsyncMock(return_value=[])), \
         patch("citra_llm.get_llm_client", return_value=fake_client), \
         patch("citra_llm.get_llm_model", return_value="test-model"), \
         patch("citra_llm.get_llm_extra_body", return_value={}), \
         patch("services.personal_data_tool.dispatch_personal_data_tool", new=fake_dispatch_personal):
        out = await run_Enterprise_or_Personal_tool(
            prompt="please look",
            user_id="u1",
            use_personal_data=True,
            selected_folder_ids=["folder-x"],
            max_results_cap=3,
        )
    assert "final answer" in out
    assert len(dispatch_calls) == 1
    call = dispatch_calls[0]
    assert call["folder_ids"] == ["folder-x"]  # scope bound by caller
    assert call["max_results_cap"] == 3        # cap propagated
    assert call["user_id"] == "u1"


@pytest.mark.asyncio
async def test_run_Enterprise_or_Personal_tool_propagates_cap_to_enterprise_dispatcher():
    """When the LLM calls a dept_* tool, dispatch_enterprise_tool receives the cap."""
    from services.enterprise_tools import run_Enterprise_or_Personal_tool
    from types import SimpleNamespace as SN

    defs = [_make_tool_def(0, source_id="src1")]
    enterprise_dispatch_calls = []

    async def fake_dispatch_enterprise(**kwargs):
        enterprise_dispatch_calls.append(kwargs)
        return {"success": True, "results": [{"text": "y"}], "returned": 1}

    tool_call = _make_tool_call(call_id="tc1", name="dept_src1", arguments='{"query": "q"}')
    resp_with_tool = _stub_llm_completion(content=None, tool_calls=[tool_call])
    resp_final = _stub_llm_completion(content="merged answer")

    create_iter = iter([resp_with_tool, resp_final])

    async def fake_create(**_kwargs):
        return next(create_iter)

    fake_client = SN(chat=SN(completions=SN(create=fake_create)))

    with patch("services.enterprise_mcp_client.discover_tools", new=AsyncMock(return_value=defs)), \
         patch("citra_llm.get_llm_client", return_value=fake_client), \
         patch("citra_llm.get_llm_model", return_value="test-model"), \
         patch("citra_llm.get_llm_extra_body", return_value={}), \
         patch("services.enterprise_tools.dispatch_enterprise_tool", new=fake_dispatch_enterprise):
        out = await run_Enterprise_or_Personal_tool(
            prompt="please",
            org_id="o1",
            roles=["user"],
            max_results_cap=5,
        )
    assert "merged answer" in out
    assert len(enterprise_dispatch_calls) == 1
    assert enterprise_dispatch_calls[0]["max_results_cap"] == 5
