# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
compute_fact_tool.py

LLM-callable tool that returns a single scalar / aggregate / short result
computed from one of the user's STRUCTURED vault files (.csv, .xlsx, .xls,
.json) by running Python in the action sandbox.

Used by presentation and printable generation flows to inline numerical facts
into slide / page content (e.g. "total revenue FY24"). Charts continue to
flow through the `<chart-placeholder>` + `/composer/generate-chart` path —
this tool is for SCALAR or SHORT-LIST values only.

Vault-scoped: the dispatcher only reads files from the user's vault folders
via `services.structured_sandbox.run_structured_sandbox`. Enterprise data
sources are not reachable.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from services.structured_sandbox import run_structured_sandbox

logger = logging.getLogger(__name__)


def build_compute_fact_tool_schema() -> Dict[str, Any]:
    """OpenAI function-tool schema for `compute_fact`."""
    return {
        "type": "function",
        "function": {
            "name": "compute_fact",
            "description": (
                "Compute a single scalar value or short aggregate (sum, count, mean, "
                "median, min, max, top-N, latest value, group-by-with-N-rows) from one "
                "of the user's STRUCTURED vault files (.csv, .xlsx, .xls, .json) and "
                "return the result as JSON. Use this when you need an exact numerical "
                "fact to inline into slide / printable content — e.g. 'total revenue "
                "FY24', 'top 5 customers by sales'. "
                "DO NOT use this for charts (emit a `<chart-placeholder>` element "
                "instead — the chart endpoint handles full Chart.js generation). "
                "DO NOT use this for prose / passages from PDFs / DOCX / TXT — call "
                "`personal_data_tool` for those. "
                "Internally runs Python in a sandbox against the full file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Plain-English request for the value, including the metric, "
                            "any time / filter scope, and (if known) which file. "
                            "Examples: 'sum of Revenue column in sales.xlsx for FY 2024', "
                            "'top 5 products by units sold in inventory.csv', "
                            "'count of distinct customers in transactions.csv'."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    }


_INSTRUCTION_TEMPLATE = (
    "User wants this single fact / short aggregate computed from their vault data:\n"
    "{query}\n\n"
    "Write a Python script that:\n"
    "1. Loads the relevant file(s) from /workspace/input/ (pandas for csv/xlsx, "
    "json module for json).\n"
    "2. Computes the requested value.\n"
    "3. Prints exactly ONE JSON object to stdout with this shape:\n"
    "   {{\"value\": <number|string|list>, \"unit\": <optional unit string>, "
    "\"detail\": <optional 1-line description>}}\n"
    "   For top-N or grouped results, value can be a list of "
    "{{\"label\": ..., \"value\": ...}} objects.\n"
    "Print NOTHING ELSE — no logs, no explanations, no markdown."
)


async def dispatch_compute_fact(
    args: Dict[str, Any],
    *,
    user_id: str,
    folder_ids: Optional[List[str]] = None,
    log_prefix: str = "COMPUTE_FACT",
) -> str:
    """
    Dispatch a `compute_fact` tool call.

    Returns a JSON string suitable for use as an OpenAI tool-call result:
        {"success": true, "result": {...}}                — parsed JSON value
        {"success": true, "raw_stdout": "..."}            — non-JSON stdout
        {"success": false, "error": "...", "message": ".."}
    """
    query = ((args or {}).get("query") or "").strip()
    if not query:
        return json.dumps({
            "success": False,
            "error": "missing_query",
            "message": "compute_fact requires a non-empty `query` argument.",
        })

    instruction = _INSTRUCTION_TEMPLATE.format(query=query)

    try:
        result = await run_structured_sandbox(
            user_id=user_id,
            folder_ids=folder_ids,
            instruction_prompt=instruction,
            log_prefix=log_prefix,
        )
    except Exception as exc:
        logger.exception(f"❌ [{log_prefix}] sandbox crashed for query={query!r}")
        return json.dumps({
            "success": False,
            "error": "sandbox_crashed",
            "message": str(exc)[:300],
        })

    err = result.get("error")
    if err == "no_structured_data":
        return json.dumps({
            "success": False,
            "error": "no_structured_data",
            "message": (
                "No structured (CSV/Excel/JSON) files found in the user's selected "
                "vault folders. Cannot compute. Either fall back to "
                "personal_data_tool for prose answers, or tell the user no "
                "structured data is available."
            ),
        })
    if err == "no_script":
        return json.dumps({
            "success": False,
            "error": "no_script",
            "message": (
                "Could not derive a Python computation from the request. Try "
                "rephrasing with explicit column names / filters."
            ),
        })
    if not result.get("success"):
        return json.dumps({
            "success": False,
            "error": "exec_failed",
            "stderr": (result.get("stderr") or "")[:500],
        })

    stdout = (result.get("stdout") or "").strip()
    if not stdout:
        return json.dumps({
            "success": True,
            "raw_stdout": "",
            "message": "Sandbox executed but printed nothing.",
        })

    try:
        parsed = json.loads(stdout)
        return json.dumps({"success": True, "result": parsed})
    except json.JSONDecodeError:
        return json.dumps({
            "success": True,
            "raw_stdout": stdout[:2000],
            "note": "Sandbox stdout was not valid JSON; returning raw text.",
        })


def make_compute_fact_dispatcher(
    *,
    user_id: str,
    folder_ids: Optional[List[str]] = None,
    log_prefix: str = "COMPUTE_FACT",
):
    """
    Build an `extra_tool_dispatch` callable for use with
    :func:`services.enterprise_tools.run_Enterprise_or_Personal_tool`.

    Returns ``None`` for unknown tool names so the helper can fall through to
    its default error handling.
    """

    async def _dispatch(name: str, args: Dict[str, Any]) -> Optional[str]:
        if name != "compute_fact":
            return None
        return await dispatch_compute_fact(
            args, user_id=user_id, folder_ids=folder_ids, log_prefix=log_prefix,
        )

    return _dispatch


COMPUTE_FACT_ROUTING_RULE = """
**🚦 STRUCTURED VS UNSTRUCTURED ROUTING (read before picking a tool):**
- **Inline scalar / aggregate facts from structured files (.csv, .xlsx, .xls, .json)** → call `compute_fact(query=...)`. Returns JSON like `{"value": ..., "unit": ..., "detail": ...}`. Use whenever you need an exact number for slide / section text (totals, averages, counts, top-N, latest values).
- **Charts on structured files** → emit a `<chart-placeholder data-description="..." data-metric="sum|count|avg|top_n|distribution|trend" data-dimension="<column>" data-source-hint="<filename>"/>` element. Do NOT call `compute_fact` to generate chart data — the chart endpoint handles full Chart.js generation.
- **Prose / passages / qualitative content from PDF / DOCX / TXT files** → call `personal_data_tool(query=...)`. Do NOT call `compute_fact` on unstructured files.
- **General knowledge / non-vault content** → answer from training knowledge as usual.
""".strip()
