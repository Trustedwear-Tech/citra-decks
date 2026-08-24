# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
File Metadata Enricher
======================

Upload-time enrichment that uses the **large** LLM tier to produce
high-quality, query-able metadata for both structured (Excel/CSV/JSON) and
unstructured (PDF/DOCX/TXT/MD/HTML) vault files.

The enriched fields (``summary``, ``doc_type``, ``semantic_tags``,
``key_entities``) are then read by ``services/file_relevance_scorer.py`` at
chat time so the agent only mounts files that actually match the user's
query — avoiding context bloat without sacrificing recall on enterprise
queries like "the audit doc" → ``compliance_review.pdf``.

Why large tier and not small/medium?
------------------------------
Misses are unacceptable in enterprise scenarios. A small/cheap model can
mis-summarise or invent the wrong ``doc_type`` for nuanced files, which
then poisons every future relevance match. The large tier (e.g. deepseek-v3.1)
is invoked *once* per upload — the per-call cost is amortised across all
future chats that reference the file.

Resilience
----------
This is **non-blocking** enrichment. If the LLM call fails, returns
malformed JSON, or times out, we log and return empty fields. The caller
must fall back to filename + raw text/columns for matching.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cap how much raw content we feed the enricher. Bumped 2026-05-08 to give
# the model more of the file (titles, intros, exec-summaries, headings) so
# distinctive content past the first few pages survives into the summary.
# Trade-off: ~2× input tokens per upload (one-time amortised cost).
MAX_TEXT_CHARS = 6000
MAX_SAMPLE_ROWS = 8
MAX_COLUMNS_PREVIEW = 40

# Output-shape limits enforced after parsing. Bumped 2026-05-08 to give the
# chat-time relevance scorer richer signal — longer summaries match more
# nuanced queries; more tags + entities improve keyword coverage.
MAX_TAGS = 15
MAX_ENTITIES = 15
MAX_SUMMARY_CHARS = 800
MAX_DOC_TYPE_CHARS = 80


EMPTY_RESULT: Dict[str, Any] = {
    "summary": "",
    "doc_type": "",
    "semantic_tags": [],
    "key_entities": [],
}


def _build_prompt(
    *,
    filename: str,
    file_type: str,
    extracted_text: Optional[str],
    columns: Optional[List[Dict[str, Any]]],
    sample_rows: Optional[List[Dict[str, Any]]],
) -> str:
    """Compact, JSON-mode prompt. ~200 output tokens expected."""
    parts: List[str] = []
    parts.append(f"Filename: {filename}")
    parts.append(f"File type: {file_type}")

    if columns:
        cols_preview = []
        for c in columns[:MAX_COLUMNS_PREVIEW]:
            name = c.get("name", "?")
            ctype = c.get("type", "?")
            samples = c.get("samples") or []
            sample_str = ", ".join(str(s) for s in samples[:3])
            cols_preview.append(f"  - {name} ({ctype}) e.g. {sample_str}")
        parts.append("Columns:")
        parts.append("\n".join(cols_preview))

    if sample_rows:
        parts.append("Sample rows (first few):")
        try:
            parts.append(json.dumps(sample_rows[:MAX_SAMPLE_ROWS], default=str, ensure_ascii=False)[:1500])
        except Exception:
            pass

    if extracted_text:
        snippet = extracted_text.strip()[:MAX_TEXT_CHARS]
        parts.append("Content excerpt:")
        parts.append(snippet)

    return "\n\n".join(parts)


SYSTEM_PROMPT = (
    "You are a precise document indexer. Given a single file's filename, "
    "type, and a short content/schema preview, produce compact, retrieval-"
    "friendly metadata. Be specific and concrete — avoid generic words like "
    "'document', 'file', 'data'. The output is consumed by a relevance "
    "scorer that matches user queries against many files; the better your "
    "tags and summary, the better the match.\n\n"
    "Return ONLY a JSON object with this exact shape:\n"
    "{\n"
    '  "summary": "<2-4 sentences, <=800 chars, what is in this file, the key topics it covers, and why someone would query it>",\n'
    '  "doc_type": "<one of: contract | report | invoice | resume | spec | manual | meeting_notes | policy | presentation | tradebook | financial_statement | dataset | email | letter | research | other>",\n'
    '  "semantic_tags": ["<8-15 short keywords, lowercase, no spaces preferred, domain/topic-specific>"],\n'
    '  "key_entities": ["<8-15 named orgs, people, products, projects, locations actually mentioned>"]\n'
    "}\n\n"
    "Rules:\n"
    "- If the content is empty or unreadable, return empty arrays and empty strings.\n"
    "- Do not include any text outside the JSON object.\n"
    "- Tags and entities must be drawn from the actual content/columns/filename — do NOT invent.\n"
    "- The summary should pack as much distinctive detail as fits in the budget — proper nouns, dates, dollar amounts, scope (e.g. 'covers FY2025 Q1-Q3 motor-claims data, Maharashtra & Gujarat, ~12k claims, includes denied/approved status, payout amounts, examiner notes, and a fraud-flag column from rule engine v3.2'). Generic recaps waste the budget.\n"
)


def _coerce_str_list(v: Any, *, max_items: int) -> List[str]:
    if not isinstance(v, list):
        return []
    out: List[str] = []
    for item in v:
        if isinstance(item, str):
            s = item.strip()
            if s:
                out.append(s[:80])
        if len(out) >= max_items:
            break
    return out


def _validate(result: Any) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return dict(EMPTY_RESULT)

    summary = result.get("summary")
    summary = (summary.strip() if isinstance(summary, str) else "")[:MAX_SUMMARY_CHARS]

    doc_type = result.get("doc_type")
    doc_type = (doc_type.strip() if isinstance(doc_type, str) else "")[:MAX_DOC_TYPE_CHARS]

    tags = _coerce_str_list(result.get("semantic_tags"), max_items=MAX_TAGS)
    entities = _coerce_str_list(result.get("key_entities"), max_items=MAX_ENTITIES)

    return {
        "summary": summary,
        "doc_type": doc_type,
        "semantic_tags": tags,
        "key_entities": entities,
    }


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_response(raw: str) -> Dict[str, Any]:
    if not raw:
        return dict(EMPTY_RESULT)
    text = raw.strip()
    # Strip code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    try:
        parsed = json.loads(text)
        return _validate(parsed)
    except json.JSONDecodeError:
        # Best-effort extract first JSON object from response.
        m = _JSON_OBJECT_RE.search(text)
        if m:
            try:
                return _validate(json.loads(m.group(0)))
            except Exception:
                pass
    logger.warning("file_metadata_enricher: could not parse LLM response as JSON")
    return dict(EMPTY_RESULT)


async def enrich_file_metadata(
    *,
    filename: str,
    file_type: str,
    extracted_text: Optional[str] = None,
    columns: Optional[List[Dict[str, Any]]] = None,
    sample_rows: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[str] = None,
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    """
    Run the large-tier LLM to produce enriched metadata for a single file.

    Returns
    -------
    dict
        ``{summary, doc_type, semantic_tags, key_entities}`` — empty fields
        on any failure (never raises).
    """
    if not filename and not extracted_text and not columns:
        return dict(EMPTY_RESULT)

    try:
        from llm_oss import llm_call  # local import to avoid cycle on cold start
    except Exception:
        logger.exception("file_metadata_enricher: cannot import llm_oss.llm_call")
        return dict(EMPTY_RESULT)

    user_prompt = _build_prompt(
        filename=filename,
        file_type=file_type,
        extracted_text=extracted_text,
        columns=columns,
        sample_rows=sample_rows,
    )

    def _sync_call() -> str:
        try:
            return llm_call(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                user_id=user_id,
                # Large tier is a reasoning model — reasoning tokens (~600-1000)
                # are spent BEFORE any content is emitted. The visible JSON is
                # only ~500-700 tokens, but the total budget must cover both.
                # reasoning_effort=low keeps the reasoning bounded for this
                # structured-extraction task.
                max_tokens=4000,
                temperature=0.1,
                top_p=0.9,
                json_mode=True,
                tier="large",
                reasoning_effort="low",
            )
        except Exception as e:
            logger.warning("file_metadata_enricher: llm_call failed: %s", e)
            return ""

    try:
        raw = await asyncio.wait_for(asyncio.to_thread(_sync_call), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.warning(
            "file_metadata_enricher: LLM call timed out after %.1fs for %s",
            timeout_seconds, filename,
        )
        return dict(EMPTY_RESULT)
    except Exception as e:
        logger.warning("file_metadata_enricher: unexpected error for %s: %s", filename, e)
        return dict(EMPTY_RESULT)

    parsed = _parse_response(raw)
    logger.info(
        "file_metadata_enricher: enriched %s — doc_type=%r tags=%d entities=%d summary_len=%d",
        filename, parsed["doc_type"], len(parsed["semantic_tags"]),
        len(parsed["key_entities"]), len(parsed["summary"]),
    )
    return parsed
