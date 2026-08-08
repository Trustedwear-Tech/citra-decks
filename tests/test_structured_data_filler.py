"""Tests for ``services.structured_data_filler``.

These tests mock ``run_structured_sandbox`` so we exercise the extract /
resolve / apply path without spawning Docker.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.structured_data_filler import (
    extract_data_requests,
    fill_data_requests,
    _normalise_chart_config,
    _normalise_request,
)


# ---------------------------------------------------------------------------
# extract_data_requests
# ---------------------------------------------------------------------------


def test_extract_returns_empty_when_no_requests():
    slide = {"elements": [{"id": "t1", "type": "text", "text": "hello"}]}
    assert extract_data_requests(slide) == []


def test_extract_finds_chart_request():
    slide = {
        "elements": [
            {
                "id": "c1",
                "type": "chart",
                "chartConfig": {},
                "_data_request": {
                    "kind": "chart",
                    "description": "Top 5 colleges by enrollment",
                    "metric": "top_n",
                    "dimension": "college",
                    "preferred_chart_type": "bar",
                    "top_n": 5,
                },
            }
        ]
    }
    descriptors = extract_data_requests(slide)
    assert len(descriptors) == 1
    d = descriptors[0]
    assert d["element_id"] == "c1"
    assert d["request"]["kind"] == "chart"
    assert d["request"]["preferred_chart_type"] == "bar"
    assert d["request"]["top_n"] == 5


def test_extract_drops_invalid_kind():
    slide = {
        "elements": [
            {
                "id": "x1",
                "type": "text",
                "_data_request": {"kind": "weird", "description": "anything"},
            }
        ]
    }
    assert extract_data_requests(slide) == []


def test_extract_drops_missing_description():
    slide = {
        "elements": [
            {
                "id": "x1",
                "type": "chart",
                "_data_request": {"kind": "chart"},
            }
        ]
    }
    assert extract_data_requests(slide) == []


# ---------------------------------------------------------------------------
# _normalise_request
# ---------------------------------------------------------------------------


def test_normalise_request_clamps_invalid_chart_type():
    out = _normalise_request(
        {"kind": "chart", "description": "x", "preferred_chart_type": "bogus"}
    )
    assert out is not None
    assert out["preferred_chart_type"] is None


def test_normalise_request_drops_out_of_range_top_n():
    out = _normalise_request(
        {"kind": "list", "description": "x", "top_n": 999}
    )
    assert out is not None
    assert out["top_n"] is None


# ---------------------------------------------------------------------------
# _normalise_chart_config
# ---------------------------------------------------------------------------


def test_normalise_chart_config_accepts_valid():
    cfg = {
        "type": "bar",
        "data": {"labels": ["A"], "datasets": [{"label": "x", "data": [1]}]},
    }
    assert _normalise_chart_config(cfg) is not None


def test_normalise_chart_config_falls_back_to_bar():
    cfg = {
        "type": "weird",
        "data": {"labels": ["A"], "datasets": [{"label": "x", "data": [1]}]},
    }
    out = _normalise_chart_config(cfg)
    assert out is not None
    assert out["type"] == "bar"


def test_normalise_chart_config_rejects_missing_data():
    assert _normalise_chart_config({"type": "bar"}) is None
    assert _normalise_chart_config("not a dict") is None


# ---------------------------------------------------------------------------
# fill_data_requests — end-to-end with mocked sandbox
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fill_no_requests_is_noop():
    slide = {"elements": [{"id": "t", "type": "text", "text": "hi"}]}
    with patch(
        "services.structured_data_filler.run_structured_sandbox",
        new=AsyncMock(),
    ) as mock_sandbox:
        report = await fill_data_requests(
            slide, user_id="u1", folder_ids=None,
        )
    assert report == {
        "resolved": 0, "failed": 0, "data_warnings": [], "source_documents": [],
    }
    mock_sandbox.assert_not_called()


@pytest.mark.asyncio
async def test_fill_chart_request_replaces_config():
    slide = {
        "elements": [
            {
                "id": "c1",
                "type": "chart",
                "chartConfig": {},
                "_data_request": {
                    "kind": "chart",
                    "description": "Top 3 cities by sales",
                    "preferred_chart_type": "bar",
                },
            }
        ]
    }
    sandbox_payload = {
        "type": "bar",
        "data": {
            "labels": ["A", "B", "C"],
            "datasets": [
                {"label": "Sales", "data": [10, 20, 30],
                 "backgroundColor": ["#111", "#222", "#333"]}
            ],
        },
    }
    sandbox_result = {
        "success": True,
        "stdout": __import__("json").dumps(sandbox_payload),
        "stderr": "",
        "entries": [SimpleNamespace(filename="sales.csv")],
        "error": None,
        "raw_response": None,
    }
    with patch(
        "services.structured_data_filler.run_structured_sandbox",
        new=AsyncMock(return_value=sandbox_result),
    ):
        report = await fill_data_requests(
            slide, user_id="u1", folder_ids=["f1"],
        )

    assert report["resolved"] == 1
    assert report["failed"] == 0
    el = slide["elements"][0]
    assert "_data_request" not in el
    assert el["chartConfig"]["type"] == "bar"
    assert el["chartConfig"]["data"]["labels"] == ["A", "B", "C"]
    assert el["dataSource"] == "sales.csv"
    assert report["source_documents"] == ["sales.csv"]


@pytest.mark.asyncio
async def test_fill_stat_request_replaces_text():
    slide = {
        "elements": [
            {
                "id": "s1",
                "type": "text",
                "text": "{{value}}",
                "_data_request": {
                    "kind": "stat",
                    "description": "Total colleges",
                    "metric": "count",
                },
            }
        ]
    }
    sandbox_result = {
        "success": True,
        "stdout": '{"value": 1043, "unit": null}',
        "stderr": "",
        "entries": [],
        "error": None,
    }
    with patch(
        "services.structured_data_filler.run_structured_sandbox",
        new=AsyncMock(return_value=sandbox_result),
    ):
        report = await fill_data_requests(
            slide, user_id="u1", folder_ids=None,
        )
    assert report["resolved"] == 1
    el = slide["elements"][0]
    assert "_data_request" not in el
    assert el["text"] == "1043"


@pytest.mark.asyncio
async def test_fill_list_request_replaces_items():
    slide = {
        "elements": [
            {
                "id": "l1",
                "type": "card",
                "items": [],
                "_data_request": {
                    "kind": "list",
                    "description": "Top 5 customers",
                    "top_n": 5,
                },
            }
        ]
    }
    sandbox_result = {
        "success": True,
        "stdout": '{"items": ["Acme", "Globex", "Initech"]}',
        "stderr": "",
        "entries": [],
        "error": None,
    }
    with patch(
        "services.structured_data_filler.run_structured_sandbox",
        new=AsyncMock(return_value=sandbox_result),
    ):
        report = await fill_data_requests(
            slide, user_id="u1", folder_ids=None,
        )
    assert report["resolved"] == 1
    el = slide["elements"][0]
    assert "_data_request" not in el
    assert el["items"] == ["Acme", "Globex", "Initech"]


@pytest.mark.asyncio
async def test_fill_failure_marks_chart_for_ai_fix():
    slide = {
        "elements": [
            {
                "id": "c2",
                "type": "chart",
                "chartConfig": {},
                "_data_request": {
                    "kind": "chart",
                    "description": "Revenue by quarter",
                },
            }
        ]
    }
    sandbox_result = {
        "success": False,
        "stdout": "",
        "stderr": "boom",
        "entries": [],
        "error": "exec_failed",
    }
    with patch(
        "services.structured_data_filler.run_structured_sandbox",
        new=AsyncMock(return_value=sandbox_result),
    ):
        report = await fill_data_requests(
            slide, user_id="u1", folder_ids=None,
        )
    assert report["resolved"] == 0
    assert report["failed"] == 1
    assert report["data_warnings"][0]["element_id"] == "c2"
    el = slide["elements"][0]
    # placeholder stripped, chart marked for AI-fix pass
    assert "_data_request" not in el
    assert el["chartConfig"]["_ai_fix_needed"] is True


@pytest.mark.asyncio
async def test_fill_invalid_stdout_is_failure():
    slide = {
        "elements": [
            {
                "id": "s2",
                "type": "text",
                "text": "{{value}}",
                "_data_request": {
                    "kind": "stat",
                    "description": "Avg score",
                },
            }
        ]
    }
    sandbox_result = {
        "success": True,
        "stdout": "not json at all",
        "stderr": "",
        "entries": [],
        "error": None,
    }
    with patch(
        "services.structured_data_filler.run_structured_sandbox",
        new=AsyncMock(return_value=sandbox_result),
    ):
        report = await fill_data_requests(
            slide, user_id="u1", folder_ids=None,
        )
    assert report["failed"] == 1
    assert report["data_warnings"][0]["reason"] == "invalid_stdout"


@pytest.mark.asyncio
async def test_fill_handles_sandbox_exception():
    slide = {
        "elements": [
            {
                "id": "c3",
                "type": "chart",
                "chartConfig": {},
                "_data_request": {
                    "kind": "chart",
                    "description": "Anything",
                },
            }
        ]
    }
    with patch(
        "services.structured_data_filler.run_structured_sandbox",
        new=AsyncMock(side_effect=RuntimeError("docker offline")),
    ):
        report = await fill_data_requests(
            slide, user_id="u1", folder_ids=None,
        )
    assert report["failed"] == 1
    assert report["data_warnings"][0]["reason"] == "sandbox_exception"
