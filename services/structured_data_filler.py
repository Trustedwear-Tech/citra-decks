"""
Structured Data Filler
======================

Resolves ``_data_request`` placeholders embedded by the slide / page LLM
into real values computed from the user's structured vault files
(Excel/CSV/JSON) via the sandbox ``execute_code`` path.

Why this exists
---------------
After the SaaS-collection removal, the slide / page LLM only sees a schema
preview (column names + 3 sample values per column) for structured files.
That is enough to decide *what* a chart or stat should show, but NOT enough
to compute real values — so the LLM was hallucinating numbers.

The fix is a small protocol:

* The LLM emits a placeholder anywhere it needs file-backed data:

  - **Chart**:  an element of ``type == "chart"`` with a ``_data_request``
    object describing the desired aggregation. ``chartConfig`` may be
    omitted or empty.
  - **Stat / metric**:  a text element with a ``_data_request`` object and
    a placeholder value (e.g. ``"text": "{{value}}"``). The element's
    ``content`` is replaced with the resolved scalar.
  - **List**:  a text/card element with a ``_data_request`` of kind
    ``"list"``. The element gets back a short JSON array which the caller
    can render into bullets / cards.

* This module walks the slide JSON, fans out each ``_data_request`` to
  :func:`services.structured_sandbox.run_structured_sandbox`, and
  substitutes the resolved values back into the slide JSON in-place.

Concurrency cap is 4 (Docker pressure). Failures are non-fatal — the
placeholder is left intact and a ``data_warnings`` list is returned so the
caller can flag the element for the existing AI-fix pass.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from services.structured_sandbox import run_structured_sandbox

logger = logging.getLogger(__name__)

# Cap how many sandbox calls we run in parallel per slide / page. Each one
# spawns a Docker exec, so we keep this small.
MAX_CONCURRENT_RESOLUTIONS = 4

# Hard cap on the number of placeholders we will resolve in a single slide.
# Anything past this is left as a placeholder + warning.
MAX_REQUESTS_PER_SLIDE = 8

VALID_KINDS = {"chart", "stat", "list"}
VALID_CHART_TYPES = {"bar", "line", "pie", "doughnut", "radar", "polarArea", "scatter", "bubble"}


# ----------------------------------------------------------------------------
# Extraction
# ----------------------------------------------------------------------------


def _walk(node: Any, path: Tuple[Any, ...]):
    """Yield (parent_container, key_or_index, value, path) for every node."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield node, k, v, path + (k,)
            yield from _walk(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield node, i, v, path + (i,)
            yield from _walk(v, path + (i,))


def extract_data_requests(slide_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Return one descriptor per ``_data_request`` found in the slide JSON.

    Each descriptor is::

        {
            "request":   <the _data_request dict, normalised>,
            "container": <the dict that holds _data_request>,
            "element_id": <id of the nearest ancestor element with an "id">,
        }
    """
    if not isinstance(slide_json, dict):
        return []

    requests: List[Dict[str, Any]] = []
    # Track ancestor element ids so we can attribute warnings to a slide element.
    # We do a simple DFS keeping the most recent dict that has both "id" and "type".

    def _scan(node: Any, ancestor_id: Optional[str]):
        if isinstance(node, dict):
            current_id = ancestor_id
            if "id" in node and "type" in node:
                current_id = node.get("id") or current_id
            req = node.get("_data_request")
            if isinstance(req, dict):
                normalised = _normalise_request(req)
                if normalised is not None:
                    requests.append(
                        {
                            "request": normalised,
                            "container": node,
                            "element_id": current_id,
                        }
                    )
            for v in node.values():
                _scan(v, current_id)
        elif isinstance(node, list):
            for v in node:
                _scan(v, ancestor_id)

    _scan(slide_json, None)
    return requests[:MAX_REQUESTS_PER_SLIDE]


def _normalise_request(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Validate + normalise an LLM-emitted ``_data_request``. Returns None if unusable."""
    kind = (req.get("kind") or "").strip().lower()
    if kind not in VALID_KINDS:
        return None
    description = (req.get("description") or "").strip()
    if not description:
        return None

    out: Dict[str, Any] = {
        "kind": kind,
        "description": description,
        "metric": (req.get("metric") or "").strip().lower() or None,
        "dimension": (req.get("dimension") or "").strip() or None,
        "filter": (req.get("filter") or "").strip() or None,
        "top_n": req.get("top_n") if isinstance(req.get("top_n"), int) else None,
        "preferred_chart_type": (req.get("preferred_chart_type") or "").strip().lower() or None,
        "source_file_hint": (req.get("source_file_hint") or "").strip() or None,
    }
    if out["preferred_chart_type"] and out["preferred_chart_type"] not in VALID_CHART_TYPES:
        out["preferred_chart_type"] = None
    if isinstance(out["top_n"], int) and (out["top_n"] < 1 or out["top_n"] > 50):
        out["top_n"] = None
    return out


# ----------------------------------------------------------------------------
# Instruction prompts (per kind)
# ----------------------------------------------------------------------------


def _build_instruction(req: Dict[str, Any]) -> str:
    kind = req["kind"]
    parts: List[str] = [f"User request: {req['description']}"]
    if req.get("source_file_hint"):
        parts.append(f"Likely source file: {req['source_file_hint']}")
    if req.get("metric"):
        parts.append(f"Metric: {req['metric']}")
    if req.get("dimension"):
        parts.append(f"Group / break by: {req['dimension']}")
    if req.get("filter"):
        parts.append(f"Filter: {req['filter']}")
    if req.get("top_n"):
        parts.append(f"Top N: {req['top_n']}")
    ctx = "\n".join(parts)

    if kind == "chart":
        chart_type = req.get("preferred_chart_type") or "bar"
        return (
            f"{ctx}\n\n"
            f"Preferred chart type: {chart_type} "
            f"(allowed: {', '.join(sorted(VALID_CHART_TYPES))}).\n\n"
            "Write a Python script that:\n"
            "1. Loads the relevant file(s) from /workspace/input/ (pandas for csv/xlsx, json module for json).\n"
            "2. Computes the labels and dataset values.\n"
            "3. Builds a Chart.js config dict with EXACTLY this shape:\n"
            '   {"type": "<chart_type>", "data": {"labels": [...], "datasets": '
            '[{"label": "...", "data": [...], "backgroundColor": [...]}]}}\n'
            "4. Prints the config as JSON to stdout via `print(json.dumps(config))`. Print NOTHING ELSE.\n"
            "Use up to 12 labels max — aggregate / take top-N as appropriate. Use realistic backgroundColor hex values."
        )
    if kind == "stat":
        return (
            f"{ctx}\n\n"
            "Write a Python script that:\n"
            "1. Loads the relevant file(s) from /workspace/input/.\n"
            "2. Computes ONE scalar value answering the request.\n"
            "3. Prints exactly ONE JSON object to stdout via `print(json.dumps({'value': <number_or_string>, 'unit': <optional_unit>}))`.\n"
            "Print NOTHING ELSE — no logs, no explanations.\n"
            "If the value is large (>=10000) prefer compact form (e.g. '1.2M', '3.4K') as a string."
        )
    # list
    return (
        f"{ctx}\n\n"
        "Write a Python script that:\n"
        "1. Loads the relevant file(s) from /workspace/input/.\n"
        "2. Computes a short ordered list answering the request (max 12 items).\n"
        "3. Prints exactly ONE JSON object to stdout via `print(json.dumps({'items': [...]}))`.\n"
        "Each item is either a string or a small object with up to 3 keys. Print NOTHING ELSE."
    )


# ----------------------------------------------------------------------------
# Resolution
# ----------------------------------------------------------------------------


async def _resolve_one(
    user_id: str,
    folder_ids: Optional[List[str]],
    descriptor: Dict[str, Any],
    log_prefix: str,
) -> Dict[str, Any]:
    """
    Run the sandbox for a single descriptor and return::

        {
            "ok":       bool,
            "kind":     str,
            "value":    <kind-specific resolved value>,  # only on ok=True
            "source_document": Optional[str],
            "error":    Optional[str],                    # short reason on failure
            "element_id": Optional[str],
        }
    """
    req = descriptor["request"]
    kind = req["kind"]
    element_id = descriptor.get("element_id")

    try:
        result = await run_structured_sandbox(
            user_id=user_id,
            folder_ids=folder_ids,
            instruction_prompt=_build_instruction(req),
            log_prefix=log_prefix,
        )
    except Exception as exc:  # noqa: BLE001 — we never want this to bubble
        logger.warning(
            f"📊 [{log_prefix}] sandbox raised for element={element_id} kind={kind}: {exc}"
        )
        return {
            "ok": False, "kind": kind, "element_id": element_id,
            "error": "sandbox_exception", "source_document": None, "value": None,
        }

    if not result.get("success"):
        err = result.get("error") or "exec_failed"
        return {
            "ok": False, "kind": kind, "element_id": element_id,
            "error": err, "source_document": None, "value": None,
        }

    stdout = (result.get("stdout") or "").strip()
    parsed = _safe_parse_json(stdout)
    if parsed is None:
        return {
            "ok": False, "kind": kind, "element_id": element_id,
            "error": "invalid_stdout", "source_document": None, "value": None,
        }

    entries = result.get("entries") or []
    source_doc = entries[0].filename if entries else None

    if kind == "chart":
        normalised = _normalise_chart_config(parsed)
        if normalised is None:
            return {
                "ok": False, "kind": kind, "element_id": element_id,
                "error": "invalid_chart_config", "source_document": source_doc, "value": None,
            }
        # Honour preferred type if the script ignored it.
        preferred = req.get("preferred_chart_type")
        if preferred and normalised.get("type") not in VALID_CHART_TYPES:
            normalised["type"] = preferred
        return {
            "ok": True, "kind": kind, "element_id": element_id,
            "value": normalised, "source_document": source_doc, "error": None,
        }
    if kind == "stat":
        if not isinstance(parsed, dict) or "value" not in parsed:
            return {
                "ok": False, "kind": kind, "element_id": element_id,
                "error": "invalid_stat_payload", "source_document": source_doc, "value": None,
            }
        return {
            "ok": True, "kind": kind, "element_id": element_id,
            "value": {"value": parsed["value"], "unit": parsed.get("unit")},
            "source_document": source_doc, "error": None,
        }
    # list
    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return {
            "ok": False, "kind": kind, "element_id": element_id,
            "error": "invalid_list_payload", "source_document": source_doc, "value": None,
        }
    return {
        "ok": True, "kind": kind, "element_id": element_id,
        "value": {"items": items[:12]},
        "source_document": source_doc, "error": None,
    }


def _safe_parse_json(stdout: str) -> Any:
    if not stdout:
        return None
    try:
        return json.loads(stdout)
    except Exception:
        pass
    start = stdout.find("{")
    end = stdout.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(stdout[start:end + 1])
        except Exception:
            return None
    return None


def _normalise_chart_config(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    cfg = dict(raw)
    ctype = cfg.get("type", "bar")
    if ctype not in VALID_CHART_TYPES:
        stripped = str(ctype).replace("chart-", "").replace("chart_", "")
        cfg["type"] = stripped if stripped in VALID_CHART_TYPES else "bar"
    if "data" not in cfg and ("labels" in cfg or "datasets" in cfg):
        cfg["data"] = {
            "labels": cfg.pop("labels", []),
            "datasets": cfg.pop("datasets", []),
        }
    data = cfg.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("datasets"), list):
        return None
    return cfg


# ----------------------------------------------------------------------------
# Application
# ----------------------------------------------------------------------------


def _apply_one(descriptor: Dict[str, Any], resolution: Dict[str, Any]) -> None:
    container = descriptor["container"]
    if not isinstance(container, dict):
        return

    # Always strip the marker so the client never sees it.
    container.pop("_data_request", None)

    if not resolution.get("ok"):
        # Mark the element so the existing AI-fix pass can take a swing at it.
        if container.get("type") == "chart":
            existing_cfg = container.get("chartConfig")
            if not isinstance(existing_cfg, dict):
                existing_cfg = {}
            existing_cfg["_ai_fix_needed"] = True
            container["chartConfig"] = existing_cfg
        return

    kind = resolution["kind"]
    value = resolution["value"]

    if kind == "chart":
        container["chartConfig"] = value
        container.pop("_ai_fix_needed", None)
        if resolution.get("source_document"):
            container.setdefault("dataSource", resolution["source_document"])
        return

    if kind == "stat":
        scalar = value.get("value")
        unit = value.get("unit")
        text = str(scalar) if scalar is not None else ""
        if unit:
            text = f"{text} {unit}".strip()
        # Replace common text-bearing keys.
        for key in ("text", "content", "value", "stat_value"):
            if key in container:
                container[key] = text
                break
        else:
            container["text"] = text
        return

    if kind == "list":
        container["items"] = value.get("items", [])
        return


# ----------------------------------------------------------------------------
# Public entrypoint
# ----------------------------------------------------------------------------


async def fill_data_requests(
    slide_json: Dict[str, Any],
    *,
    user_id: str,
    folder_ids: Optional[List[str]],
    log_prefix: str = "DATA-FILLER",
) -> Dict[str, Any]:
    """
    Walk ``slide_json``, resolve every ``_data_request`` against the user's
    structured files in parallel, and substitute the values in place.

    Returns a small report::

        {
            "resolved":        int,
            "failed":          int,
            "data_warnings":   [{"element_id": ..., "reason": ...}, ...],
            "source_documents": [str, ...],
        }
    """
    if not isinstance(slide_json, dict):
        return {"resolved": 0, "failed": 0, "data_warnings": [], "source_documents": []}

    descriptors = extract_data_requests(slide_json)
    if not descriptors:
        return {"resolved": 0, "failed": 0, "data_warnings": [], "source_documents": []}

    logger.info(
        f"📊 [{log_prefix}] resolving {len(descriptors)} data request(s) "
        f"(kinds={[d['request']['kind'] for d in descriptors]})"
    )

    sem = asyncio.Semaphore(MAX_CONCURRENT_RESOLUTIONS)

    async def _worker(d: Dict[str, Any]) -> Dict[str, Any]:
        async with sem:
            return await _resolve_one(user_id, folder_ids, d, log_prefix)

    resolutions = await asyncio.gather(
        *[_worker(d) for d in descriptors], return_exceptions=False
    )

    resolved = 0
    failed = 0
    warnings: List[Dict[str, Any]] = []
    source_docs: List[str] = []

    for descriptor, resolution in zip(descriptors, resolutions):
        _apply_one(descriptor, resolution)
        if resolution.get("ok"):
            resolved += 1
            src = resolution.get("source_document")
            if src and src not in source_docs:
                source_docs.append(src)
        else:
            failed += 1
            warnings.append({
                "element_id": resolution.get("element_id"),
                "kind": resolution.get("kind"),
                "reason": resolution.get("error") or "unknown",
            })

    logger.info(
        f"📊 [{log_prefix}] done: resolved={resolved} failed={failed} "
        f"sources={source_docs}"
    )

    return {
        "resolved": resolved,
        "failed": failed,
        "data_warnings": warnings,
        "source_documents": source_docs,
    }
