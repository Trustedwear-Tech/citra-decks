"""
Structured Data Planner
=======================

Prefetch-then-generate pipeline for presentation / printable / composer.

The slide / page / report LLM only sees a schema preview (column names + a
handful of sample values) for the user's structured files (Excel/CSV/JSON).
That is enough to *decide* what data is interesting, but NOT enough to
compute real numbers — so the LLM hallucinates.

This module fixes that at outline time:

1. :func:`plan_aggregations` — one LLM call that, given the outline + the
   schema preview, emits a small JSON list of aggregations to compute
   (kind="chart"/"stat"/"list", per page).
2. :func:`compute_aggregations` — fans out to
   :func:`services.structured_sandbox.run_structured_sandbox` (max 4 in
   parallel; identical signatures are de-duped) and returns the results.
3. :func:`format_for_page` — renders a clearly delimited
   ``=== COMPUTED DATA ===`` block scoped to one page, ready to inject
   into the per-page generator's prompt.

The per-page generator is then instructed to *cite* values from that
block instead of inventing them.

The placeholder pipeline (:mod:`services.structured_data_filler`) remains
as a fallback safety net.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional

from services.structured_sandbox import run_structured_sandbox

logger = logging.getLogger(__name__)


# ─── Tunables ───────────────────────────────────────────────────────────────

# Maximum aggregations we will ask the planner to emit per generation.
# We deliberately cap at 1 because each page-gen call covers exactly one page,
# and a single page rarely needs more than one chart/stat/list. Keeping this
# tight controls cost (1 sandbox compute per page) and forces the planner to
# pick the most important aggregation rather than padding.
MAX_AGGREGATIONS = 1

# Sandbox fan-out concurrency (Docker pressure).
MAX_CONCURRENT_COMPUTE = 4

# Planner LLM tier — dashboard-building benefits from the large model's
# stronger JSON adherence and reasoning over multi-file structured overviews.
PLANNER_TIER = "large"

VALID_KINDS = {"chart", "stat", "list"}
VALID_CHART_TYPES = {"bar", "line", "pie", "doughnut", "radar", "polarArea", "scatter", "bubble"}


# ─── Public surface ─────────────────────────────────────────────────────────


async def plan_and_compute(
    *,
    user_id: str,
    folder_ids: Optional[List[str]],
    user_query: str,
    outline: Any,
    schema_preview: str,
    log_prefix: str = "DATA_PLAN",
) -> Dict[str, Any]:
    """
    Convenience wrapper: plan → compute. Returns a single dict::

        {
            "plan":     [Aggregation, ...],
            "results":  { agg_id: ResultDict, ... },
            "warnings": [ str, ... ],
        }

    Both ``plan`` and ``results`` are empty if no structured files are in
    scope (the caller should still be able to render the page).
    """
    if not schema_preview or not schema_preview.strip():
        return {"plan": [], "results": {}, "warnings": []}

    plan = await plan_aggregations(
        user_id=user_id,
        user_query=user_query,
        outline=outline,
        schema_preview=schema_preview,
        log_prefix=log_prefix,
    )
    if not plan:
        return {"plan": [], "results": {}, "warnings": []}

    results, warnings = await compute_aggregations(
        plan=plan,
        user_id=user_id,
        folder_ids=folder_ids,
        log_prefix=log_prefix,
    )
    return {"plan": plan, "results": results, "warnings": warnings}


async def plan_aggregations(
    *,
    user_id: str,
    user_query: str,
    outline: Any,
    schema_preview: str,
    log_prefix: str = "DATA_PLAN",
) -> List[Dict[str, Any]]:
    """
    Ask the planner LLM to enumerate aggregations grounded in the schema.

    Returns a list of dicts shaped like::

        {
            "id":            "agg_1",
            "page_index":    0,
            "kind":          "chart" | "stat" | "list",
            "description":   "Trade volume by symbol top 10",
            "metric":        "sum(quantity)",
            "dimension":     "symbol",
            "filter":        None | "year=2024",
            "top_n":         10,
            "preferred_chart_type": "bar" | None,
            "source_file_hint":     "tradebook.csv" | None,
        }

    Returns ``[]`` on any failure — the per-page generator will then
    operate without computed data (qualitative prose only).
    """
    outline_text = _outline_to_text(outline)
    if not outline_text.strip():
        return []

    system_prompt = _PLANNER_SYSTEM
    user_prompt = (
        f"=== USER REQUEST ===\n{user_query.strip()}\n\n"
        f"=== OUTLINE ===\n{outline_text}\n\n"
        f"=== AVAILABLE STRUCTURED FILES ===\n{schema_preview.strip()}\n\n"
        "Emit the JSON plan now."
    )

    try:
        from llm_oss import llm_call
        raw = await asyncio.to_thread(
            llm_call,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=None,
            user_id=user_id,
            temperature=0.1,
            top_p=0.9,
            tier=PLANNER_TIER,
            json_mode=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"📊 [{log_prefix}] planner LLM raised: {exc}")
        return []

    plan = _parse_plan(raw)
    if not plan:
        logger.info(f"📊 [{log_prefix}] planner returned 0 aggregations")
        return []

    plan = plan[:MAX_AGGREGATIONS]
    logger.info(
        f"📊 [{log_prefix}] planner produced {len(plan)} aggregations: "
        + ", ".join(f"{a['kind']}:{a['id']}@p{a.get('page_index', '?')}" for a in plan)
    )
    return plan


async def compute_aggregations(
    *,
    plan: List[Dict[str, Any]],
    user_id: str,
    folder_ids: Optional[List[str]],
    log_prefix: str = "DATA_PLAN",
) -> tuple[Dict[str, Dict[str, Any]], List[str]]:
    """
    Run every aggregation in ``plan`` through the sandbox.

    Returns ``(results_by_id, warnings)``.

    Result shape::

        {
            "ok":              bool,
            "kind":            "chart" | "stat" | "list",
            "value":           Any,    # chart_config | scalar | items
            "source_document": Optional[str],
            "error":           Optional[str],
        }

    Identical signatures (same kind/metric/dimension/filter/top_n/source_hint)
    are computed once and shared across pages.
    """
    if not plan:
        return {}, []

    # De-dupe: build (signature → list[agg]) so we run sandbox once per signature.
    sig_to_aggs: Dict[str, List[Dict[str, Any]]] = {}
    for agg in plan:
        sig = _signature(agg)
        sig_to_aggs.setdefault(sig, []).append(agg)

    sem = asyncio.Semaphore(MAX_CONCURRENT_COMPUTE)
    warnings: List[str] = []
    results: Dict[str, Dict[str, Any]] = {}

    async def _run_one(sig: str, aggs: List[Dict[str, Any]]):
        rep = aggs[0]
        instruction = _build_instruction(rep)
        async with sem:
            try:
                sandbox = await run_structured_sandbox(
                    user_id=user_id,
                    folder_ids=folder_ids,
                    instruction_prompt=instruction,
                    log_prefix=f"{log_prefix}-{rep['id']}",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"📊 [{log_prefix}] sandbox raised for {rep['id']}: {exc}")
                for a in aggs:
                    results[a["id"]] = {
                        "ok": False, "kind": a["kind"],
                        "value": None, "source_document": None,
                        "error": "sandbox_exception",
                    }
                warnings.append(f"{rep['id']}: sandbox_exception")
                return

        if not sandbox.get("success"):
            err = sandbox.get("error") or "exec_failed"
            for a in aggs:
                results[a["id"]] = {
                    "ok": False, "kind": a["kind"],
                    "value": None, "source_document": None,
                    "error": err,
                }
            warnings.append(f"{rep['id']}: {err}")
            return

        stdout = (sandbox.get("stdout") or "").strip()
        parsed = _safe_parse_json(stdout)
        entries = sandbox.get("entries") or []
        source_doc = entries[0].filename if entries else None

        if parsed is None:
            for a in aggs:
                results[a["id"]] = {
                    "ok": False, "kind": a["kind"],
                    "value": None, "source_document": source_doc,
                    "error": "invalid_stdout",
                }
            warnings.append(f"{rep['id']}: invalid_stdout")
            return

        # Normalise per-kind.
        value, err = _normalise(rep["kind"], parsed, rep)
        if err:
            for a in aggs:
                results[a["id"]] = {
                    "ok": False, "kind": a["kind"],
                    "value": None, "source_document": source_doc, "error": err,
                }
            warnings.append(f"{rep['id']}: {err}")
            return

        for a in aggs:
            results[a["id"]] = {
                "ok": True, "kind": a["kind"],
                "value": value, "source_document": source_doc, "error": None,
            }

    await asyncio.gather(*(_run_one(sig, aggs) for sig, aggs in sig_to_aggs.items()))

    ok_count = sum(1 for r in results.values() if r["ok"])
    logger.info(
        f"📊 [{log_prefix}] compute complete: {ok_count}/{len(results)} ok, "
        f"{len(sig_to_aggs)} unique signatures"
    )
    return results, warnings


def format_for_page(
    *,
    plan: List[Dict[str, Any]],
    results: Dict[str, Dict[str, Any]],
    page_index: int,
) -> str:
    """
    Render the slice of computed data relevant to one page as a delimited
    block ready to drop into a per-page generator's prompt.

    Returns ``""`` if no aggregations target this page.
    """
    relevant = [a for a in plan if int(a.get("page_index", -1)) == page_index]
    if not relevant:
        return ""

    lines: List[str] = []
    lines.append("=== COMPUTED DATA (USE THESE EXACT NUMBERS — DO NOT INVENT) ===")
    for agg in relevant:
        res = results.get(agg["id"])
        if not res or not res.get("ok"):
            err = (res or {}).get("error") or "missing"
            lines.append(f"\n[{agg['id']}] kind={agg['kind']} description={agg['description']!r}")
            lines.append(f"  status: FAILED ({err}) — write qualitative prose, NEVER invent numbers.")
            continue

        src = res.get("source_document") or "?"
        lines.append(f"\n[{agg['id']}] kind={agg['kind']} description={agg['description']!r}")
        lines.append(f"  source: {src}")
        # Emit value as compact JSON so the LLM can copy it.
        try:
            value_str = json.dumps(res["value"], ensure_ascii=False)
        except Exception:  # noqa: BLE001
            value_str = str(res["value"])
        if len(value_str) > 4000:
            value_str = value_str[:4000] + "...<truncated>"
        lines.append(f"  value: {value_str}")

    lines.append("\n=== END COMPUTED DATA ===")
    lines.append(
        "Rules: For chart elements on this page, copy `chartConfig` directly "
        "from the matching `value`. For any number / percentage / count cited "
        "in body text, take it from a `value` above. If no relevant entry "
        "exists, write descriptive qualitative prose — NEVER invent numbers."
    )
    return "\n".join(lines)


# ─── Internals ──────────────────────────────────────────────────────────────


_PLANNER_SYSTEM = (
    "You plan data aggregations for a multi-page artifact (presentation / "
    "printable / report). The user will provide an outline of pages and a "
    "schema preview of structured files (Excel/CSV/JSON) available. Your job "
    "is to decide which concrete aggregations should be computed against "
    "those files so the per-page generator can cite real numbers instead of "
    "inventing them.\n\n"
    "Return STRICT JSON with this exact shape:\n"
    '{"aggregations": [\n'
    '  {\n'
    '    "id": "agg_1",\n'
    '    "page_index": 0,\n'
    '    "kind": "chart" | "stat" | "list",\n'
    '    "description": "short human description",\n'
    '    "metric": "count | sum(col) | avg(col) | min(col) | max(col) | top_n",\n'
    '    "dimension": "column to group/break by, or null",\n'
    '    "filter": "natural-language filter, or null",\n'
    '    "top_n": 10,\n'
    '    "preferred_chart_type": "bar | line | pie | doughnut | scatter | null",\n'
    '    "source_file_hint": "filename if obvious from schema, else null"\n'
    '  }\n'
    "]}\n\n"
    "Hard rules:\n"
    "1. Emit AT MOST 1 aggregation. Pick the SINGLE most important chart/stat/list "
    "the page needs. If the page is text-only or doesn't need file-backed data, "
    "return `{\"aggregations\": []}`.\n"
    "2. Every `dimension` and column referenced inside `metric` MUST exist in "
    "the schema preview. Do NOT invent column names.\n"
    "3. `kind=chart` for visualisations; `kind=stat` for a single scalar; "
    "`kind=list` for a short ranked list.\n"
    "4. If NO useful aggregation is possible (schema doesn't support the "
    "outline's questions), return `{\"aggregations\": []}`. Never make up data.\n"
    "5. Output ONLY the JSON object. No prose, no markdown fences."
)


def _outline_to_text(outline: Any) -> str:
    """Best-effort flatten of an outline to a numbered list of page titles + descriptions."""
    if outline is None:
        return ""
    if isinstance(outline, str):
        return outline.strip()

    # Common shapes: list[dict] with title/description, or dict with "pages"/"slides".
    pages = None
    if isinstance(outline, list):
        pages = outline
    elif isinstance(outline, dict):
        for key in ("pages", "slides", "outline", "items"):
            if isinstance(outline.get(key), list):
                pages = outline[key]
                break

    if not pages:
        # Fallback: dump as JSON.
        try:
            return json.dumps(outline, ensure_ascii=False)[:4000]
        except Exception:  # noqa: BLE001
            return str(outline)[:4000]

    lines: List[str] = []
    for i, p in enumerate(pages):
        if isinstance(p, str):
            lines.append(f"{i}. {p}")
            continue
        if not isinstance(p, dict):
            continue
        title = p.get("title") or p.get("page_title") or p.get("slide_title") or ""
        desc = (
            p.get("description")
            or p.get("summary")
            or p.get("page_description")
            or p.get("body")
            or ""
        )
        line = f"{i}. {title}".rstrip()
        if desc:
            line += f"\n   {desc}"
        lines.append(line)
    return "\n".join(lines)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_plan(raw: str) -> List[Dict[str, Any]]:
    if not raw:
        return []
    try:
        obj = json.loads(raw)
    except Exception:  # noqa: BLE001
        # Try to extract the first {...} block.
        m = _JSON_RE.search(raw)
        if not m:
            return []
        try:
            obj = json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            return []

    if not isinstance(obj, dict):
        return []
    aggs = obj.get("aggregations")
    if not isinstance(aggs, list):
        return []

    out: List[Dict[str, Any]] = []
    seen_ids: set = set()
    for i, a in enumerate(aggs):
        if not isinstance(a, dict):
            continue
        kind = a.get("kind")
        desc = a.get("description")
        if kind not in VALID_KINDS or not isinstance(desc, str) or not desc.strip():
            continue
        agg_id = str(a.get("id") or f"agg_{i + 1}")
        if agg_id in seen_ids:
            agg_id = f"{agg_id}_{i}"
        seen_ids.add(agg_id)
        try:
            page_index = int(a.get("page_index", 0))
        except Exception:  # noqa: BLE001
            page_index = 0
        top_n = a.get("top_n")
        try:
            top_n = int(top_n) if top_n is not None else None
        except Exception:  # noqa: BLE001
            top_n = None
        chart_type = a.get("preferred_chart_type")
        if chart_type and chart_type not in VALID_CHART_TYPES:
            chart_type = None

        out.append({
            "id": agg_id,
            "page_index": page_index,
            "kind": kind,
            "description": desc.strip(),
            "metric": (a.get("metric") or "").strip() or None,
            "dimension": (a.get("dimension") or None) or None,
            "filter": (a.get("filter") or None) or None,
            "top_n": top_n,
            "preferred_chart_type": chart_type,
            "source_file_hint": (a.get("source_file_hint") or None) or None,
        })
    return out


def _signature(agg: Dict[str, Any]) -> str:
    """Stable signature for de-duping identical aggregations across pages."""
    payload = {
        "kind": agg["kind"],
        "metric": (agg.get("metric") or "").lower(),
        "dimension": (agg.get("dimension") or "").lower(),
        "filter": (agg.get("filter") or "").lower(),
        "top_n": agg.get("top_n"),
        "preferred_chart_type": agg.get("preferred_chart_type"),
        "source_file_hint": (agg.get("source_file_hint") or "").lower(),
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _build_instruction(agg: Dict[str, Any]) -> str:
    kind = agg["kind"]
    parts: List[str] = [f"User request: {agg['description']}"]
    if agg.get("source_file_hint"):
        parts.append(f"Likely source file: {agg['source_file_hint']}")
    if agg.get("metric"):
        parts.append(f"Metric: {agg['metric']}")
    if agg.get("dimension"):
        parts.append(f"Group / break by: {agg['dimension']}")
    if agg.get("filter"):
        parts.append(f"Filter: {agg['filter']}")
    if agg.get("top_n"):
        parts.append(f"Top N: {agg['top_n']}")
    ctx = "\n".join(parts)
    datetime_hint = (
        "Datetime handling requirements:\n"
        "- If columns like 'Date', 'Start Time', 'End Time' exist, parse them robustly with errors='coerce'.\n"
        "- Combine date+time when needed: to_datetime(Date.astype(str) + ' ' + Start Time.astype(str)).\n"
        "- If End Time < Start Time, treat as overnight by adding one day to End Time before subtraction.\n"
        "- Derive duration_minutes as (end_dt - start_dt).dt.total_seconds() / 60 and drop invalid rows only, not entire dataset."
    )

    if kind == "chart":
        chart_type = agg.get("preferred_chart_type") or "bar"
        return (
            f"{ctx}\n\n"
            f"{datetime_hint}\n\n"
            f"Preferred chart type: {chart_type} "
            f"(allowed: {', '.join(sorted(VALID_CHART_TYPES))}).\n\n"
            "Write a Python script that:\n"
            "1. Loads the relevant file(s) from /workspace/input/ (pandas for csv/xlsx, json module for json).\n"
            "2. Computes the labels and dataset values.\n"
            "3. Builds a Chart.js config dict with EXACTLY this shape:\n"
            '   {"type": "<chart_type>", "data": {"labels": [...], "datasets": '
            '[{"label": "...", "data": [...], "backgroundColor": [...]}]}}\n'
            "4. Prints the config as JSON to stdout via `print(json.dumps(config))`. Print NOTHING ELSE.\n"
            "Use up to 12 labels max — aggregate / take top-N as appropriate. "
            "Use realistic backgroundColor hex values."
        )
    if kind == "stat":
        return (
            f"{ctx}\n\n"
            f"{datetime_hint}\n\n"
            "Write a Python script that:\n"
            "1. Loads the relevant file(s) from /workspace/input/.\n"
            "2. Computes ONE scalar value answering the request.\n"
            "3. Prints exactly ONE JSON object to stdout via "
            "`print(json.dumps({'value': <number_or_string>, 'unit': <optional_unit>}))`.\n"
            "Print NOTHING ELSE. If the value is large (>=10000) prefer compact "
            "form (e.g. '1.2M', '3.4K') as a string."
        )
    # list
    return (
        f"{ctx}\n\n"
        f"{datetime_hint}\n\n"
        "Write a Python script that:\n"
        "1. Loads the relevant file(s) from /workspace/input/.\n"
        "2. Computes a short ordered list answering the request (max 12 items).\n"
        "3. Prints exactly ONE JSON object to stdout via `print(json.dumps({'items': [...]}))`.\n"
        "Each item is either a string or a small object with up to 3 keys. Print NOTHING ELSE."
    )


def _safe_parse_json(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        m = _JSON_RE.search(text)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            return None


def _normalise(kind: str, parsed: Any, agg: Dict[str, Any]) -> tuple[Any, Optional[str]]:
    """Return (value, error)."""
    if kind == "chart":
        if not isinstance(parsed, dict):
            return None, "invalid_chart_config"
        # Some scripts emit {labels, datasets} flat — wrap it.
        if "data" not in parsed and ("labels" in parsed or "datasets" in parsed):
            parsed = {
                "type": parsed.get("type", agg.get("preferred_chart_type") or "bar"),
                "data": {
                    "labels": parsed.get("labels", []),
                    "datasets": parsed.get("datasets", []),
                },
            }
        ctype = parsed.get("type")
        if ctype not in VALID_CHART_TYPES:
            preferred = agg.get("preferred_chart_type")
            parsed["type"] = preferred if preferred in VALID_CHART_TYPES else "bar"
        data = parsed.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("datasets"), list):
            return None, "invalid_chart_config"
        return parsed, None

    if kind == "stat":
        if not isinstance(parsed, dict):
            return None, "invalid_stat"
        if "value" not in parsed:
            return None, "invalid_stat"
        return parsed, None

    if kind == "list":
        if isinstance(parsed, list):
            return {"items": parsed[:12]}, None
        if isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
            parsed["items"] = parsed["items"][:12]
            return parsed, None
        return None, "invalid_list"

    return None, "unknown_kind"
