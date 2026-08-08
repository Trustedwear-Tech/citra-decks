"""Tests for ``services.structured_data_planner``.

These tests stub ``llm_call`` and ``run_structured_sandbox`` so the planner /
compute / format pipeline is exercised without spawning Docker or hitting an
LLM.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.structured_data_planner import (
    _build_instruction,
    _normalise,
    _outline_to_text,
    _parse_plan,
    _signature,
    compute_aggregations,
    format_for_page,
    plan_aggregations,
    plan_and_compute,
)


# ─── _outline_to_text ───────────────────────────────────────────────────────


def test_outline_to_text_handles_string():
    assert _outline_to_text("hello") == "hello"


def test_outline_to_text_handles_list_of_dicts():
    outline = [
        {"title": "P1", "description": "d1"},
        {"title": "P2"},
    ]
    text = _outline_to_text(outline)
    assert "0. P1" in text
    assert "d1" in text
    assert "1. P2" in text


def test_outline_to_text_handles_pages_wrapper():
    outline = {"pages": [{"title": "A"}, {"title": "B"}]}
    text = _outline_to_text(outline)
    assert "0. A" in text
    assert "1. B" in text


def test_outline_to_text_none():
    assert _outline_to_text(None) == ""


# ─── _parse_plan ────────────────────────────────────────────────────────────


def test_parse_plan_valid():
    raw = """{"aggregations": [
        {"id":"a1","page_index":0,"kind":"chart","description":"x","metric":"sum(q)","dimension":"sym","top_n":10,"preferred_chart_type":"bar"},
        {"id":"a2","page_index":1,"kind":"stat","description":"total"}
    ]}"""
    plan = _parse_plan(raw)
    assert len(plan) == 2
    assert plan[0]["id"] == "a1"
    assert plan[0]["preferred_chart_type"] == "bar"
    assert plan[0]["top_n"] == 10
    assert plan[1]["kind"] == "stat"


def test_parse_plan_empty_aggregations():
    assert _parse_plan('{"aggregations": []}') == []


def test_parse_plan_drops_invalid():
    raw = """{"aggregations":[
        {"id":"a1","kind":"bogus","description":"x"},
        {"kind":"chart"},
        {"kind":"chart","description":"good"}
    ]}"""
    plan = _parse_plan(raw)
    assert len(plan) == 1
    assert plan[0]["description"] == "good"


def test_parse_plan_strips_invalid_chart_type():
    raw = '{"aggregations":[{"kind":"chart","description":"x","preferred_chart_type":"sankey"}]}'
    plan = _parse_plan(raw)
    assert plan[0]["preferred_chart_type"] is None


def test_parse_plan_extracts_from_prose():
    raw = "sure! here you go:\n{\"aggregations\":[{\"kind\":\"stat\",\"description\":\"x\"}]}"
    plan = _parse_plan(raw)
    assert len(plan) == 1


def test_parse_plan_garbage():
    assert _parse_plan("nope") == []
    assert _parse_plan("") == []


# ─── _signature ─────────────────────────────────────────────────────────────


def test_signature_dedupes_same_request():
    a = {"kind": "chart", "description": "X", "metric": "sum(q)", "dimension": "s",
         "filter": None, "top_n": 10, "preferred_chart_type": "bar", "source_file_hint": "f.csv"}
    b = dict(a)
    assert _signature(a) == _signature(b)


def test_signature_distinguishes_metric():
    a = {"kind": "chart", "description": "X", "metric": "sum(q)", "dimension": "s",
         "filter": None, "top_n": 10, "preferred_chart_type": "bar", "source_file_hint": "f.csv"}
    b = dict(a, metric="avg(q)")
    assert _signature(a) != _signature(b)


# ─── _normalise ─────────────────────────────────────────────────────────────


def test_normalise_chart_wraps_flat():
    val, err = _normalise("chart", {"labels": ["a"], "datasets": [{"data": [1]}]},
                          {"preferred_chart_type": "line"})
    assert err is None
    assert val["type"] == "line"
    assert val["data"]["labels"] == ["a"]


def test_normalise_chart_invalid_returns_error():
    val, err = _normalise("chart", {"foo": "bar"}, {})
    assert err == "invalid_chart_config"
    assert val is None


def test_normalise_chart_falls_back_chart_type():
    val, err = _normalise("chart",
                           {"type": "bogus", "data": {"labels": [], "datasets": []}},
                           {"preferred_chart_type": "pie"})
    assert err is None
    assert val["type"] == "pie"


def test_normalise_stat_passthrough():
    val, err = _normalise("stat", {"value": 42, "unit": "USD"}, {})
    assert err is None
    assert val["value"] == 42


def test_normalise_stat_missing_value():
    val, err = _normalise("stat", {"unit": "x"}, {})
    assert err == "invalid_stat"


def test_normalise_list_from_array():
    val, err = _normalise("list", ["a", "b", "c"], {})
    assert err is None
    assert val == {"items": ["a", "b", "c"]}


def test_normalise_list_from_object_truncates():
    val, err = _normalise("list", {"items": list(range(20))}, {})
    assert err is None
    assert len(val["items"]) == 12


# ─── _build_instruction ─────────────────────────────────────────────────────


def test_build_instruction_chart_includes_hints():
    agg = {"id": "a1", "kind": "chart", "description": "Top 5 by qty",
           "metric": "sum(q)", "dimension": "sym", "filter": "year=2024",
           "top_n": 5, "preferred_chart_type": "bar", "source_file_hint": "x.csv"}
    text = _build_instruction(agg)
    assert "Top 5 by qty" in text
    assert "x.csv" in text
    assert "Group / break by: sym" in text
    assert "Top N: 5" in text
    assert "Filter: year=2024" in text
    assert "bar" in text
    assert "json.dumps(config)" in text


def test_build_instruction_stat():
    text = _build_instruction({"id": "a1", "kind": "stat", "description": "Total"})
    assert "ONE scalar" in text
    assert "value" in text


def test_build_instruction_list():
    text = _build_instruction({"id": "a1", "kind": "list", "description": "Top items"})
    assert "ordered list" in text
    assert "items" in text


# ─── plan_aggregations ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_aggregations_returns_empty_on_blank_outline():
    plan = await plan_aggregations(
        user_id="u", user_query="q", outline=None, schema_preview="schema",
    )
    assert plan == []


@pytest.mark.asyncio
async def test_plan_aggregations_calls_llm_and_parses():
    raw = '{"aggregations":[{"id":"a1","page_index":0,"kind":"chart","description":"X"}]}'
    with patch("services.structured_data_planner.asyncio.to_thread",
               new=AsyncMock(return_value=raw)):
        plan = await plan_aggregations(
            user_id="u", user_query="q", outline=[{"title": "P1"}],
            schema_preview="cols",
        )
    assert len(plan) == 1
    assert plan[0]["id"] == "a1"


@pytest.mark.asyncio
async def test_plan_aggregations_handles_llm_exception():
    with patch("services.structured_data_planner.asyncio.to_thread",
               new=AsyncMock(side_effect=RuntimeError("boom"))):
        plan = await plan_aggregations(
            user_id="u", user_query="q", outline=[{"title": "P1"}],
            schema_preview="cols",
        )
    assert plan == []


@pytest.mark.asyncio
async def test_plan_aggregations_caps_at_max():
    aggs = [{"id": f"a{i}", "kind": "stat", "description": f"d{i}", "page_index": 0}
            for i in range(20)]
    import json as _json
    raw = _json.dumps({"aggregations": aggs})
    with patch("services.structured_data_planner.asyncio.to_thread",
               new=AsyncMock(return_value=raw)):
        plan = await plan_aggregations(
            user_id="u", user_query="q", outline=[{"title": "P1"}],
            schema_preview="cols",
        )
    assert len(plan) == 1  # MAX_AGGREGATIONS


# ─── compute_aggregations ───────────────────────────────────────────────────


def _mk_sandbox_ok(stdout, filename="src.csv"):
    return {
        "success": True,
        "stdout": stdout,
        "stderr": "",
        "entries": [SimpleNamespace(filename=filename)],
        "error": None,
    }


@pytest.mark.asyncio
async def test_compute_empty_plan_noop():
    results, warnings = await compute_aggregations(
        plan=[], user_id="u", folder_ids=None,
    )
    assert results == {}
    assert warnings == []


@pytest.mark.asyncio
async def test_compute_runs_each_agg_once_and_dedupes():
    plan = [
        {"id": "a1", "page_index": 0, "kind": "chart", "description": "X",
         "metric": "sum(q)", "dimension": "s", "filter": None, "top_n": 10,
         "preferred_chart_type": "bar", "source_file_hint": "f.csv"},
        {"id": "a2", "page_index": 1, "kind": "chart", "description": "X",
         "metric": "sum(q)", "dimension": "s", "filter": None, "top_n": 10,
         "preferred_chart_type": "bar", "source_file_hint": "f.csv"},
    ]
    sandbox_stdout = '{"type":"bar","data":{"labels":["A"],"datasets":[{"data":[1]}]}}'
    sandbox_mock = AsyncMock(return_value=_mk_sandbox_ok(sandbox_stdout))
    with patch("services.structured_data_planner.run_structured_sandbox", sandbox_mock):
        results, warnings = await compute_aggregations(
            plan=plan, user_id="u", folder_ids=None,
        )
    # De-dup: sandbox called once
    assert sandbox_mock.await_count == 1
    # Both ids share the result
    assert results["a1"]["ok"] is True
    assert results["a2"]["ok"] is True
    assert results["a1"]["value"] == results["a2"]["value"]
    assert warnings == []


@pytest.mark.asyncio
async def test_compute_marks_failure():
    plan = [{"id": "a1", "page_index": 0, "kind": "stat", "description": "Total"}]
    sandbox_mock = AsyncMock(return_value={
        "success": False, "stdout": "", "stderr": "", "entries": [], "error": "exec_failed"})
    with patch("services.structured_data_planner.run_structured_sandbox", sandbox_mock):
        results, warnings = await compute_aggregations(
            plan=plan, user_id="u", folder_ids=None,
        )
    assert results["a1"]["ok"] is False
    assert results["a1"]["error"] == "exec_failed"
    assert any("a1" in w for w in warnings)


@pytest.mark.asyncio
async def test_compute_handles_sandbox_exception():
    plan = [{"id": "a1", "page_index": 0, "kind": "stat", "description": "Total"}]
    sandbox_mock = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("services.structured_data_planner.run_structured_sandbox", sandbox_mock):
        results, warnings = await compute_aggregations(
            plan=plan, user_id="u", folder_ids=None,
        )
    assert results["a1"]["ok"] is False
    assert results["a1"]["error"] == "sandbox_exception"


@pytest.mark.asyncio
async def test_compute_invalid_stdout():
    plan = [{"id": "a1", "page_index": 0, "kind": "stat", "description": "Total"}]
    sandbox_mock = AsyncMock(return_value=_mk_sandbox_ok("not json"))
    with patch("services.structured_data_planner.run_structured_sandbox", sandbox_mock):
        results, warnings = await compute_aggregations(
            plan=plan, user_id="u", folder_ids=None,
        )
    assert results["a1"]["ok"] is False
    assert results["a1"]["error"] == "invalid_stdout"


# ─── format_for_page ────────────────────────────────────────────────────────


def test_format_for_page_empty_when_no_relevant():
    plan = [{"id": "a1", "page_index": 1, "kind": "stat", "description": "X"}]
    assert format_for_page(plan=plan, results={}, page_index=0) == ""


def test_format_for_page_renders_ok_result():
    plan = [{"id": "a1", "page_index": 0, "kind": "stat", "description": "Total trades"}]
    results = {"a1": {"ok": True, "kind": "stat",
                      "value": {"value": 1522, "unit": "trades"},
                      "source_document": "tradebook.csv", "error": None}}
    text = format_for_page(plan=plan, results=results, page_index=0)
    assert "COMPUTED DATA" in text
    assert "tradebook.csv" in text
    assert "1522" in text
    assert "Total trades" in text


def test_format_for_page_marks_failed_aggs():
    plan = [{"id": "a1", "page_index": 0, "kind": "stat", "description": "X"}]
    results = {"a1": {"ok": False, "kind": "stat", "value": None,
                      "source_document": None, "error": "exec_failed"}}
    text = format_for_page(plan=plan, results=results, page_index=0)
    assert "FAILED" in text
    assert "exec_failed" in text


def test_format_for_page_truncates_huge_value():
    plan = [{"id": "a1", "page_index": 0, "kind": "list", "description": "X"}]
    results = {"a1": {"ok": True, "kind": "list",
                      "value": {"items": ["x" * 6000]},
                      "source_document": "f.csv", "error": None}}
    text = format_for_page(plan=plan, results=results, page_index=0)
    assert "<truncated>" in text


# ─── plan_and_compute ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_and_compute_skips_when_no_schema():
    out = await plan_and_compute(
        user_id="u", folder_ids=None, user_query="q",
        outline=[{"title": "P"}], schema_preview="",
    )
    assert out == {"plan": [], "results": {}, "warnings": []}


@pytest.mark.asyncio
async def test_plan_and_compute_end_to_end():
    raw = '{"aggregations":[{"id":"a1","page_index":0,"kind":"stat","description":"Total"}]}'
    sandbox_ok = _mk_sandbox_ok('{"value": 42}')
    with patch("services.structured_data_planner.asyncio.to_thread",
               new=AsyncMock(return_value=raw)), \
         patch("services.structured_data_planner.run_structured_sandbox",
               new=AsyncMock(return_value=sandbox_ok)):
        out = await plan_and_compute(
            user_id="u", folder_ids=None, user_query="q",
            outline=[{"title": "P"}], schema_preview="cols",
        )
    assert len(out["plan"]) == 1
    assert out["results"]["a1"]["ok"] is True
    assert out["results"]["a1"]["value"]["value"] == 42
