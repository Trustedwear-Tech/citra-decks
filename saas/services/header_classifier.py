# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""
Header Classifier
=================
LLM-based classifier that decides whether a tabular file has "proper" column
headers (descriptive column names) or not (auto-generated / title-row / data-as-headers).

Files WITHOUT proper headers should be ingested as plain text chunks into the
citra collection, not embedded into the SaaS record-level collection, because
record-level embedding is only useful when columns are meaningfully named.

Fallback: on any failure (LLM error, timeout, invalid JSON) we default to
`proper_headers=False` so the file still gets indexed via the safe text path.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Short-circuit syntactic patterns that are obviously NOT proper headers.
# If ALL headers match these patterns we don't even bother calling the LLM.
_AUTO_HEADER_RE = re.compile(r"^\s*(unnamed:\s*\d+|column_\d+|col_?\d+|field_?\d+|)\s*$", re.IGNORECASE)


def _looks_obviously_auto(headers: List[str]) -> bool:
    """Return True if every header looks auto-generated or empty."""
    if not headers:
        return True
    return all(_AUTO_HEADER_RE.match(str(h) or "") is not None for h in headers)


def _coerce_sample_rows(records: List[Dict[str, Any]], headers: List[str], max_rows: int = 3) -> List[List[Any]]:
    """Turn the first N record dicts into row lists aligned to `headers`."""
    rows: List[List[Any]] = []
    for rec in records[:max_rows]:
        if isinstance(rec, dict):
            rows.append([rec.get(h, "") for h in headers])
        elif isinstance(rec, (list, tuple)):
            rows.append(list(rec)[: len(headers)])
    return rows


_CLASSIFIER_PROMPT = """You are classifying whether a tabular file has PROPER column headers.

A file has PROPER headers when the header row contains descriptive column names
(words, codes, or abbreviations) that meaningfully label the data below.
Examples of proper headers: "Symbol", "Quantity", "Buy Price", "Q1", "FY24 Revenue",
"customer_id", "created_at".

A file does NOT have proper headers when:
- Headers are auto-generated placeholders ("Column_1", "Unnamed: 0", "Field_3", "")
- The "header" row actually looks like DATA (dates, amounts, names) and the first
  data rows look similar in kind (i.e. the file has no real header row)
- Headers are single characters or purely numeric with no semantic meaning

Headers:
{headers}

First data rows:
{sample_rows}

Respond with JSON only, no prose, in this exact shape:
{{"proper_headers": true|false, "reason": "<one short sentence>"}}
"""


async def classify_headers_with_llm(
    headers: List[str],
    sample_records: Optional[List[Dict[str, Any]]] = None,
    *,
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    """
    Ask the configured LLM whether `headers` looks like a proper header row.

    Args:
        headers: column names
        sample_records: up to a handful of record dicts from the file (used as
            first-row context for the LLM)
        timeout_seconds: hard cap on the LLM call

    Returns:
        {"proper_headers": bool, "reason": str, "source": "shortcut"|"llm"|"fallback"}
    """
    headers = [str(h) if h is not None else "" for h in (headers or [])]

    # Cheap short-circuits — no LLM needed.
    if not headers:
        return {"proper_headers": False, "reason": "no headers present", "source": "shortcut"}
    if _looks_obviously_auto(headers):
        return {
            "proper_headers": False,
            "reason": "all headers are auto-generated or empty",
            "source": "shortcut",
        }

    sample_rows = _coerce_sample_rows(sample_records or [], headers)

    try:
        # Lazy import so the extractor module doesn't require the LLM client at import time.
        # Header classification is a tiny JSON-only task — route to the MEDIUM tier
        # (e.g. GLM-4.7) for reliable classification of proper column headers.
        from citra_llm import get_llm_client, get_default_model
        import asyncio

        client = get_llm_client(async_=True, tier="large")
        model = get_default_model(tier="large")

        prompt = _CLASSIFIER_PROMPT.format(
            headers=json.dumps(headers, ensure_ascii=False),
            sample_rows=json.dumps(sample_rows, ensure_ascii=False, default=str),
        )

        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a strict JSON-only classifier."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=4000,
                response_format={"type": "json_object"},
            ),
            timeout=timeout_seconds,
        )

        content = (resp.choices[0].message.content or "").strip()
        parsed = json.loads(content)
        proper = bool(parsed.get("proper_headers", False))
        reason = str(parsed.get("reason", "")).strip() or ("proper headers" if proper else "no proper headers")
        logger.info(f"[HEADER_CLASSIFIER] proper={proper} reason={reason}")
        return {"proper_headers": proper, "reason": reason, "source": "llm"}

    except Exception as e:  # noqa: BLE001 — any failure should fall back safely
        logger.warning(f"[HEADER_CLASSIFIER] LLM classification failed ({e!r}); defaulting to proper_headers=False")
        return {
            "proper_headers": False,
            "reason": f"classifier unavailable: {type(e).__name__}",
            "source": "fallback",
        }
