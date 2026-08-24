# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Structured Data Overview
========================

Goal-aware, file-grounded **data context** computed once and shared across
outline → slides / pages / sections / edits.

Why
---
The outline / slide / page LLMs only see ``format_schema_preview_for_prompt``
output today (column names + 3 sample values). That is not enough to write
slide titles or narrative anchored on the user's actual file — and the
per-slide ``services.structured_data_planner`` adds a second LLM round-trip
per slide that often returns ``0 aggregations`` for narrative slides, leaving
the slide ungrounded.

This module replaces both with a **single** flow:

1. ``list_structured_files`` → schema preview of every structured file in scope.
2. **One LLM call** that, given the user's goal + the schema, decides which
   files are relevant and authors a Python script (mirrors the
   ``quick_chat`` / ``run_structured_sandbox`` pattern). The script is
   instructed to print ONE JSON document containing per-file aggregates
   the LLM judges useful for the goal (totals, top-N, breakdowns, date
   range, …).
3. **One sandbox run** executes the script against the mounted files.
4. The JSON is rendered as a compact markdown block ready to inject into
   any downstream prompt — outline, per-slide, per-page, per-section.
5. Result is cached in Redis keyed by ``(user_id, folder_ids, file_hashes,
   goal_fingerprint)`` so every consumer in the same generation flow gets
   a hot hit.

The downstream LLM is then trusted to decide per element whether to render
a chart, a stat, bullets, or narrative — using the values verbatim.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from services.structured_file_listing import (
    list_structured_files,
    format_schema_preview_for_prompt,
    StructuredFileEntry,
)

logger = logging.getLogger(__name__)


# ─── Tunables ────────────────────────────────────────────────────────────────

CACHE_TTL_SECONDS = 1800           # 30 min — outline + all slides finish well within this
CACHE_KEY_PREFIX = "data_overview:v2:"
RELEVANCE_CACHE_KEY_PREFIX = "data_overview_rel:v2:"
RELEVANCE_CACHE_TTL_SECONDS = 1800
PROMPT_BLOCK_MAX_CHARS = 6000      # markdown injected into prompts
JSON_BUNDLE_MAX_CHARS = 24000      # cached JSON dump cap
LLM_TIER = "large"                 # large tier (deepseek-chat-v3.1) — code authoring is hard reasoning
RELEVANCE_TIER = "large"           # large tier — unified per user override (was small)
SCRIPT_MAX_OUTPUT_TOKENS = 16000   # scripts can exceed 4k tokens; truncation → unparseable
SCRIPT_TIMEOUT_HINT = 30           # logged only; sandbox enforces its own limit

# In-flight de-dup: if N callers race for the same key (e.g. 5 report
# sections firing in parallel), only ONE actually computes — the rest await
# its result. Without this we pay N× the LLM cost on cold misses.
_inflight_locks: Dict[str, asyncio.Lock] = {}
_inflight_locks_guard = asyncio.Lock()


# ─── Public surface ──────────────────────────────────────────────────────────


async def get_data_overview(
    user_id: str,
    folder_ids: Optional[List[str]],
    goal: str,
    *,
    log_prefix: str = "DATA_OVERVIEW",
) -> Optional[Dict[str, Any]]:
    """
    Return a goal-aware overview of the user's structured files.

    Cached per ``(user, folders, file fingerprints, goal fingerprint)``. Safe
    to call from outline + every per-slide / per-page generator — the heavy
    work runs at most once per goal.

    Returns ``None`` if the user has no structured files in scope or the
    overview compute fails — callers should fall back to the schema-only
    preview path.

    Result shape::

        {
            "markdown":      str,              # ready to inject in prompts
            "json_bundle":   str,              # raw JSON from the script (truncated)
            "source_files":  [filename, ...],  # files the LLM actually used
            "all_files":     [filename, ...],  # every file in scope
            "cache_hit":     bool,
            "cache_key":     str,
            "computed_at":   float,            # unix epoch
        }
    """
    listing = await list_structured_files(user_id, folder_ids=folder_ids)
    entries: List[StructuredFileEntry] = listing.get("entries", []) or []
    if not entries:
        return None

    cache_key = _build_cache_key(user_id, folder_ids, entries, goal)

    cached = _cache_get(cache_key)
    if cached is not None:
        cached["cache_hit"] = True
        logger.info(
            f"📊 [{log_prefix}] cache HIT key=…{cache_key[-12:]} "
            f"files={len(cached.get('source_files') or [])}"
        )
        return cached

    # Cheap small-LLM relevance gate. Skips the costly large-LLM + sandbox
    # round-trip when the user's goal is unrelated to any uploaded file
    # (e.g. "write a poem" while a tradebook.csv sits in the folder).
    # `entries` is guaranteed non-empty at this point.
    if not await _is_goal_relevant(
        user_id=user_id, goal=goal, entries=entries, log_prefix=log_prefix,
    ):
        return None

    # Acquire (or create) an asyncio lock for this cache key so concurrent
    # callers serialize on it. The first one computes; the rest wake up,
    # find the cache populated, and return immediately.
    async with _inflight_locks_guard:
        lock = _inflight_locks.get(cache_key)
        if lock is None:
            lock = asyncio.Lock()
            _inflight_locks[cache_key] = lock

    async with lock:
        # Re-check cache: another coroutine may have just populated it.
        cached = _cache_get(cache_key)
        if cached is not None:
            cached["cache_hit"] = True
            logger.info(
                f"📊 [{log_prefix}] cache HIT (after lock) key=…{cache_key[-12:]} "
                f"files={len(cached.get('source_files') or [])}"
            )
            return cached

        result = await _compute_overview_locked(
            user_id=user_id, goal=goal, listing=listing, entries=entries,
            cache_key=cache_key, log_prefix=log_prefix,
        )

    # Best-effort cleanup: drop the lock object if no one else is waiting.
    async with _inflight_locks_guard:
        if cache_key in _inflight_locks and not _inflight_locks[cache_key].locked():
            _inflight_locks.pop(cache_key, None)

    return result


async def _compute_overview_locked(
    *,
    user_id: str,
    goal: str,
    listing: Dict[str, Any],
    entries: List[StructuredFileEntry],
    cache_key: str,
    log_prefix: str,
) -> Optional[Dict[str, Any]]:
    started = time.perf_counter()
    schema_preview = format_schema_preview_for_prompt(
        entries, truncated_files=listing.get("truncated_files"),
    )

    # ── Attempt 1: author + execute. ──────────────────────────────────
    script = await _author_script(
        user_id=user_id, goal=goal, schema_preview=schema_preview,
        log_prefix=log_prefix,
    )
    if not script:
        logger.warning(f"📊 [{log_prefix}] LLM returned no usable script — falling back")
        return None

    json_text, exec_meta = await _run_script(
        user_id=user_id, entries=entries, script=script, log_prefix=log_prefix,
    )

    # ── Attempt 2: error-aware retry on script failure. ───────────────
    # The first author-pass sometimes emits broken Python (e.g. an
    # unterminated f-string). Re-prompting once with the stderr lets the
    # LLM fix the bug without burning the user's time on a fall-through
    # to schema-only at outline + a regenerate at pages-phase (the bug
    # we saw on tradebook P&L).
    if not json_text:
        stderr = (exec_meta or {}).get("stderr") or ""
        exit_code = (exec_meta or {}).get("exit_code")
        if stderr or exit_code not in (0, None):
            logger.warning(
                f"📊 [{log_prefix}] script attempt 1 failed (exit={exit_code}) "
                f"— retrying with error context"
            )
            script_retry = await _author_script(
                user_id=user_id, goal=goal, schema_preview=schema_preview,
                log_prefix=log_prefix,
                previous_error=stderr or f"exit code {exit_code}",
            )
            if script_retry:
                json_text, exec_meta = await _run_script(
                    user_id=user_id, entries=entries, script=script_retry,
                    log_prefix=log_prefix,
                )

    if not json_text:
        logger.warning(
            f"📊 [{log_prefix}] sandbox produced no JSON after retry "
            f"(exit={(exec_meta or {}).get('exit_code')}) — falling back to schema preview"
        )
        return None

    bundle = _safe_parse_json(json_text)
    if bundle is None:
        logger.warning(f"📊 [{log_prefix}] JSON parse failed — falling back")
        return None

    used_files = _extract_used_filenames(bundle, entries)
    markdown = _render_markdown(
        bundle=bundle,
        all_entries=entries,
        used_files=used_files,
        truncated_files=listing.get("truncated_files") or [],
        goal=goal,
    )

    json_dump = json.dumps(bundle, ensure_ascii=False, default=str)
    if len(json_dump) > JSON_BUNDLE_MAX_CHARS:
        json_dump = json_dump[:JSON_BUNDLE_MAX_CHARS] + "...<truncated>"

    result = {
        "markdown": markdown,
        "json_bundle": json_dump,
        "source_files": used_files,
        "all_files": [e.filename for e in entries],
        "cache_hit": False,
        "cache_key": cache_key,
        "computed_at": time.time(),
    }
    _cache_set(cache_key, result)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        f"📊 [{log_prefix}] computed overview in {elapsed_ms}ms "
        f"used={len(used_files)}/{len(entries)} files md={len(markdown)}c"
    )
    return result


def format_overview_for_prompt(
    overview: Optional[Dict[str, Any]],
    *,
    role: str = "outline",
) -> str:
    """
    Render the overview as a labelled prompt block with a role-specific
    instruction footer. Returns ``""`` if ``overview`` is falsy.

    ``role`` ∈ ``{"outline", "slide", "page", "section"}``.
    """
    if not overview or not overview.get("markdown"):
        return ""

    md = overview["markdown"]
    used = overview.get("source_files") or []

    if role == "slide":
        footer = (
            "\nFor THIS SLIDE: decide per element whether to render a chart "
            "(use the categories/values verbatim), a stat (cite the exact "
            "number), bullet points (each point grounded in a value above), "
            "or narrative prose. NEVER invent numbers, dates, or names. If "
            "the overview lacks a value relevant to this slide, write "
            "qualitative prose or skip the element."
        )
    elif role == "page":
        footer = (
            "\nFor THIS PAGE: pick the data points above that match the "
            "page intent and use them verbatim in tables / stats / charts / "
            "prose. NEVER invent numbers."
        )
    elif role == "section":
        footer = (
            "\nUse the data above to drive section structure and to ground "
            "every claim. NEVER invent numbers."
        )
    else:  # outline / default
        footer = (
            "\nUse this REAL data to drive the outline: slide / page / "
            "section titles must reflect the actual values present "
            "(top categories, totals, date range). Do not write generic "
            "narrative when concrete facts are available."
        )

    header = (
        "=== STRUCTURED DATA OVERVIEW (real precomputed values from user's files) ==="
    )
    if used:
        header += f"\nFiles used: {', '.join(used)}"
    return f"{header}\n{md}\n=== END STRUCTURED DATA OVERVIEW ==={footer}"


def invalidate_overview(user_id: str, folder_ids: Optional[List[str]]) -> int:
    """
    Drop every cached overview for this user+folder combination (regardless
    of goal). Call after a structured-file upload / delete affecting these
    folders.

    Returns the number of keys removed.
    """
    try:
        from citra_cache import get_cache_manager
        cm = get_cache_manager()
    except Exception:  # noqa: BLE001
        return 0

    folder_part = ",".join(sorted(folder_ids or []))
    base = hashlib.sha1(
        f"{user_id}|{folder_part}".encode("utf-8")
    ).hexdigest()[:16]
    pattern = f"{CACHE_KEY_PREFIX}{base}:*"
    try:
        keys = cm.keys(pattern)
        if not keys:
            return 0
        return cm.delete(*keys)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"📊 [DATA_OVERVIEW] invalidate failed: {exc}")
        return 0


# ─── Internals ───────────────────────────────────────────────────────────────


_RELEVANCE_SYSTEM = (
    "You are a strict routing classifier. The user has a GOAL and uploaded "
    "structured data files (Excel/CSV/JSON, with filenames + column lists). "
    "Decide whether running aggregations / computations over these files "
    "would directly answer the goal.\n\n"
    "Read the GOAL LITERALLY. Do NOT invent metaphorical, analogical, or "
    "creative bridges between the goal's subject and the file's columns. "
    "If the goal is about topic X and the file's columns describe topic "
    "Y, the answer is NO — even if you can imagine some abstract link.\n\n"
    "Answer YES only when the file's columns plainly contain the entities, "
    "metrics, or facts the goal is asking about. Examples:\n"
    "  • Goal 'analyze my trades' + file with symbol/qty/price → YES.\n"
    "  • Goal 'sales summary Q3' + file with order_date/revenue → YES.\n"
    "  • Goal 'overview of this data' + any file → YES.\n"
    "  • Goal 'what is a black hole' + tradebook file → NO "
    "(astrophysics is not in the columns).\n"
    "  • Goal 'write a poem about sunsets' + sales file → NO.\n"
    "  • Goal 'explain quantum physics' + any business file → NO.\n"
    "  • Goal 'lifecycle of stars' + tradebook → NO (do not stretch).\n\n"
    "When in doubt and the goal's topic is clearly outside what the "
    "columns describe, choose NO. Better to skip than to fabricate "
    "relevance.\n\n"
    'Output STRICT JSON: {"relevant": true|false, "reason": "<≤15 words>"}. '
    "No prose, no markdown, no code fences."
)


async def _is_goal_relevant(
    *,
    user_id: str,
    goal: str,
    entries: List[StructuredFileEntry],
    log_prefix: str,
) -> bool:
    """Cheap small-LLM gate. Returns True if any file is plausibly useful.

    Fail-open on any LLM/parse error so we never accidentally hide real
    data behind a flaky classifier.
    """
    rel_key = _build_relevance_cache_key(user_id, entries, goal)
    cached = _cache_get_text(rel_key)
    if cached is not None:
        relevant = cached == "1"
        logger.info(
            f"📊 [{log_prefix}] relevance cache HIT → "
            f"{'RELEVANT' if relevant else 'SKIP'}"
        )
        return relevant

    # Compact files block: filename + first 12 column names. Keeps the
    # prompt tiny (small-tier context is precious).
    file_lines: List[str] = []
    for e in entries[:8]:
        col_names: List[str] = []
        for col in (e.columns or [])[:12]:
            if isinstance(col, dict):
                name = col.get("name") or col.get("column") or ""
                if name:
                    col_names.append(str(name))
        cols_str = ", ".join(col_names) if col_names else "<no columns>"
        file_lines.append(f"- {e.filename}: {cols_str}")
    files_block = "\n".join(file_lines) or "<no files>"

    user_prompt = (
        f"GOAL: {goal.strip()}\n\n"
        f"FILES IN SCOPE:\n{files_block}\n\n"
        "Is computing aggregates / analytics over any of these files "
        "useful for the goal? Output JSON."
    )

    try:
        from llm_oss import llm_call
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"📊 [{log_prefix}] relevance: llm_oss import failed: {exc} — fail-open"
        )
        return True

    started = time.perf_counter()
    try:
        raw = await asyncio.to_thread(
            llm_call,
            system_prompt=_RELEVANCE_SYSTEM,
            user_prompt=user_prompt,
            model=None,
            user_id=user_id,
            temperature=0.0,
            top_p=0.9,
            tier=RELEVANCE_TIER,
            max_tokens=4000,
            json_mode=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"📊 [{log_prefix}] relevance LLM raised: {exc} — fail-open"
        )
        return True

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    parsed = _safe_parse_json(raw or "") or {}
    relevant_val = parsed.get("relevant")
    if isinstance(relevant_val, str):
        relevant_val = relevant_val.strip().lower() in {"true", "yes", "1"}
    relevant = bool(relevant_val) if relevant_val is not None else True  # fail-open
    reason = str(parsed.get("reason") or "").strip()[:120]

    _cache_set_text(rel_key, "1" if relevant else "0", RELEVANCE_CACHE_TTL_SECONDS)

    logger.info(
        f"📊 [{log_prefix}] relevance gate → "
        f"{'RELEVANT' if relevant else 'SKIP'} in {elapsed_ms}ms "
        f"(reason={reason!r})"
    )
    return relevant


_SCRIPT_SYSTEM = (
    "You are a senior data analyst. The user uploaded structured files "
    "(Excel/CSV/JSON) and stated a GOAL. Read the GOAL literally and "
    "decide YOURSELF which files matter and exactly what to compute so a "
    "downstream LLM can write a presentation/document/report grounded in "
    "the user's real data.\n\n"
    "Treat the GOAL as the only source of truth for WHAT to compute. "
    "Think carefully about what the answer actually requires before "
    "writing code. Pick the metric definition a domain expert would use "
    "for this goal — not the easiest aggregation. If the goal is broad "
    "('overview of the data'), pick 4-8 facts that genuinely "
    "characterise the file. Do NOT default to a generic menu of sums/"
    "averages/min/max if the goal does not call for them.\n\n"
    "Write ONE Python script that:\n"
    "1. Loads ONLY the files relevant to the goal from /workspace/input/ "
    "using pandas / openpyxl / json. Skip the rest.\n"
    "2. Computes exactly what the goal asks for — use a `findings` dict "
    "per file where each key is a short snake_case label that names the "
    "finding (e.g. `per_ticker_pnl`, `top_5_losers`, `net_realised_pnl`). "
    "Aim for 4-8 findings per relevant file, ALL directly serving the "
    "goal.\n"
    "3. Prints ONE JSON object to stdout. Nothing else — no logs, no "
    "prose, no markdown.\n\n"
    "Output JSON shape (strict):\n"
    "{\n"
    '  "goal_interpretation": "<one short sentence — your reading of the goal>",\n'
    '  "files_used":    ["filename1", ...],\n'
    '  "files_skipped": [{"filename": "...", "reason": "..."}],\n'
    '  "per_file": {\n'
    '    "filename1": {\n'
    '      "total_rows": <int>,\n'
    '      "columns_used": [...],\n'
    '      "findings": { "<label>": <value | list | dict>, ... }\n'
    "    }\n"
    "  },\n"
    '  "headline_facts": ["<one-line factual takeaway grounded in findings>", ...]\n'
    "}\n\n"
    "Hard rules:\n"
    "- Answer the goal literally. If the goal says 'pnl', compute P&L — "
    "  not unrelated counts or averages.\n"
    "- Always wrap column refs as df['col'] (NEVER df.col) to handle spaces.\n"
    "- Coerce dtypes defensively (pd.to_numeric/errors='coerce', "
    "  pd.to_datetime/errors='coerce').\n"
    "- For ranked / breakdown findings, include top 5-10 entries.\n"
    "- Round floats to 4 sig-figs.\n"
    "- 3-6 headline_facts, each grounded in an actual finding above.\n"
    "- Output ONLY a fenced ```python ... ``` code block. No prose."
)


async def _author_script(
    *,
    user_id: str,
    goal: str,
    schema_preview: str,
    log_prefix: str,
    previous_error: Optional[str] = None,
) -> Optional[str]:
    """Ask the LLM to write the analysis script.

    ``previous_error`` lets the caller retry with the prior stderr
    appended so the LLM can fix syntax/runtime bugs (e.g. unterminated
    f-strings) on the second attempt.
    """
    # ── 1. Build the user prompt ──────────────────────────────────────
    user_prompt = (
        f"=== GOAL ===\n{goal.strip()}\n\n"
        f"{schema_preview}\n\n"
        "Decide which files are relevant to the goal and write the Python "
        "script now. Compute exactly what the goal asks for — nothing more, "
        "nothing less."
    )
    if previous_error:
        user_prompt += (
            f"\n\n=== PREVIOUS ATTEMPT FAILED ===\n"
            f"{previous_error.strip()[:1500]}\n"
            "Fix the bug and rewrite the entire script. Common causes: "
            "unterminated f-strings, missing commas, undefined variables, "
            "column name mismatches, integer/string type errors. Output the "
            "corrected complete script."
        )

    # ── 2. LLM call ───────────────────────────────────────────────────
    try:
        from llm_oss import llm_call
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"📊 [{log_prefix}] llm_oss import failed: {exc}")
        return None

    try:
        raw = await asyncio.to_thread(
            llm_call,
            system_prompt=_SCRIPT_SYSTEM,
            user_prompt=user_prompt,
            model=None,
            user_id=user_id,
            temperature=0.1,
            top_p=0.9,
            tier=LLM_TIER,
            max_tokens=SCRIPT_MAX_OUTPUT_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"📊 [{log_prefix}] script-author LLM raised: {exc}")
        return None

    script = _extract_python_script(raw)
    if not script:
        logger.warning(
            f"📊 [{log_prefix}] could not extract python from LLM output "
            f"(raw_len={len(raw or '')}, tail=%r)",
            (raw or "")[-200:],
        )
    return script


_PY_FENCE_RE = re.compile(r"```(?:python|py|Python)\s*\n(.*?)```", re.DOTALL)


def _extract_python_script(text: str) -> Optional[str]:
    if not text:
        return None
    m = _PY_FENCE_RE.search(text)
    if m:
        return m.group(1).strip() or None
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            cand = parts[1].strip()
            if cand.lower().startswith(("python", "py")):
                cand = cand.split("\n", 1)[1] if "\n" in cand else ""
            return cand.strip() or None
    stripped = text.strip()
    if any(tok in stripped for tok in ("import ", "def ", "print(", "pandas")):
        return stripped
    return None


async def _run_script(
    *,
    user_id: str,
    entries: List[StructuredFileEntry],
    script: str,
    log_prefix: str,
) -> Tuple[Optional[str], Dict[str, Any]]:
    from services.code_executor import execute_code

    files_for_docker = [{"filename": e.filename, "s3_key": e.s3_key} for e in entries]
    session_id = f"overview_{user_id[:12]}_{uuid.uuid4().hex[:8]}"

    exec_result = await execute_code(
        script=script,
        session_id=session_id,
        files=files_for_docker,
        output_filename="overview_output.txt",
    )

    success = bool(exec_result.get("success"))
    stdout = (exec_result.get("stdout") or "").strip()
    stderr = (exec_result.get("stderr") or "").strip()

    if not success:
        # Loud diagnostic — Phase 5 of plan.
        logger.warning(
            f"📊 [{log_prefix}] script exec FAILED — stderr[:500]={stderr[:500]!r}"
        )
        # Log first ~300 chars of script too so we can see what was attempted.
        logger.warning(
            f"📊 [{log_prefix}] script preview[:300]={script[:300]!r}"
        )
        return None, {"exit_code": exec_result.get("exit_code", 1), "stderr": stderr}

    if not stdout:
        logger.warning(f"📊 [{log_prefix}] script exited 0 but stdout empty")
        return None, {"exit_code": 0, "stderr": stderr}

    return stdout, {"exit_code": 0, "stderr": stderr}


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    # Strip code fences if the script ignored instructions.
    if text.startswith("```"):
        m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        m = _JSON_OBJECT_RE.search(text)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None


def _extract_used_filenames(
    bundle: Dict[str, Any], entries: List[StructuredFileEntry],
) -> List[str]:
    declared = bundle.get("files_used")
    if isinstance(declared, list) and declared:
        return [str(x) for x in declared if x]
    per_file = bundle.get("per_file")
    if isinstance(per_file, dict) and per_file:
        return list(per_file.keys())
    return [e.filename for e in entries]


def _render_markdown(
    *,
    bundle: Dict[str, Any],
    all_entries: List[StructuredFileEntry],
    used_files: List[str],
    truncated_files: List[str],
    goal: str,
) -> str:
    lines: List[str] = []

    interp = bundle.get("goal_interpretation")
    if isinstance(interp, str) and interp.strip():
        lines.append(f"GOAL READ AS: {interp.strip()}")
        lines.append("")

    headline = bundle.get("headline_facts")
    if isinstance(headline, list) and headline:
        lines.append("HEADLINE FACTS:")
        for fact in headline[:8]:
            lines.append(f"- {fact}")
        lines.append("")

    per_file = bundle.get("per_file")
    if isinstance(per_file, dict):
        for fname, payload in per_file.items():
            if not isinstance(payload, dict):
                continue
            lines.append(f"FILE: {fname}")
            total = payload.get("total_rows")
            if total is not None:
                lines.append(f"  rows: {total}")
            cols = payload.get("columns_used")
            if isinstance(cols, list) and cols:
                lines.append(f"  columns_used: {', '.join(map(str, cols[:20]))}")

            # Preferred schema: findings dict (label → value).
            findings = payload.get("findings")
            if isinstance(findings, dict) and findings:
                lines.append("  findings:")
                for label, value in findings.items():
                    lines.append(f"    - {label}: {_render_value(value)}")
            else:
                # Backward-compat with older schemas.
                answers = payload.get("answers")
                if isinstance(answers, dict) and answers:
                    lines.append("  findings:")
                    for qid, entry in answers.items():
                        if isinstance(entry, dict) and "value" in entry:
                            ask = entry.get("ask") or qid
                            lines.append(
                                f"    - {ask}: {_render_value(entry.get('value'))}"
                            )
                        else:
                            lines.append(f"    - {qid}: {_render_value(entry)}")
                else:
                    aggregates = payload.get("aggregates")
                    if isinstance(aggregates, dict) and aggregates:
                        lines.append("  findings:")
                        for label, value in aggregates.items():
                            lines.append(f"    - {label}: {_render_value(value)}")
            lines.append("")

    skipped = bundle.get("files_skipped")
    if isinstance(skipped, list) and skipped:
        skip_lines = []
        for item in skipped:
            if isinstance(item, dict):
                skip_lines.append(
                    f"{item.get('filename', '?')} ({item.get('reason', 'not relevant')})"
                )
            else:
                skip_lines.append(str(item))
        if skip_lines:
            lines.append("FILES NOT USED (deemed unrelated to goal): " + "; ".join(skip_lines))

    if truncated_files:
        lines.append(
            "FILES DROPPED (size/count cap, not analysed): " + ", ".join(truncated_files)
        )

    rendered = "\n".join(lines).rstrip()
    if len(rendered) > PROMPT_BLOCK_MAX_CHARS:
        rendered = rendered[:PROMPT_BLOCK_MAX_CHARS] + "\n…<overview truncated>"
    return rendered


def _render_value(value: Any) -> str:
    """Compact value rendering for the markdown block."""
    if value is None:
        return "null"
    if isinstance(value, (int, float, bool, str)):
        return str(value)
    if isinstance(value, list):
        # Render lists of dicts as JSON; lists of scalars space-separated.
        if value and isinstance(value[0], dict):
            try:
                return json.dumps(value[:10], ensure_ascii=False, default=str)
            except Exception:
                return str(value[:10])
        return ", ".join(str(v) for v in value[:15])
    if isinstance(value, dict):
        # Show up to 10 entries inline.
        items = list(value.items())[:10]
        return ", ".join(f"{k}={_render_value(v)}" for k, v in items)
    return str(value)


# ─── Cache helpers ───────────────────────────────────────────────────────────


def _build_cache_key(
    user_id: str,
    folder_ids: Optional[List[str]],
    entries: List[StructuredFileEntry],
    goal: str,
) -> str:
    folder_part = ",".join(sorted(folder_ids or []))
    file_part = ",".join(sorted(
        f"{e.document_id}:{e.file_hash or ''}" for e in entries
    ))
    base = hashlib.sha1(
        f"{user_id}|{folder_part}|{file_part}".encode("utf-8")
    ).hexdigest()[:16]
    goal_part = hashlib.sha1(
        (goal or "").strip().lower().encode("utf-8")
    ).hexdigest()[:12]
    return f"{CACHE_KEY_PREFIX}{base}:{goal_part}"


def _build_relevance_cache_key(
    user_id: str,
    entries: List[StructuredFileEntry],
    goal: str,
) -> str:
    file_part = ",".join(sorted(
        f"{e.document_id}:{e.file_hash or ''}" for e in entries
    ))
    base = hashlib.sha1(
        f"{user_id}|{file_part}".encode("utf-8")
    ).hexdigest()[:16]
    goal_part = hashlib.sha1(
        (goal or "").strip().lower().encode("utf-8")
    ).hexdigest()[:12]
    return f"{RELEVANCE_CACHE_KEY_PREFIX}{base}:{goal_part}"


def _cache_get_text(key: str) -> Optional[str]:
    try:
        from citra_cache import get_cache_manager
        raw = get_cache_manager().get(key)
    except Exception:  # noqa: BLE001
        return None
    if raw is None:
        return None
    if isinstance(raw, bytes):
        try:
            return raw.decode("utf-8")
        except Exception:
            return None
    return str(raw)


def _cache_set_text(key: str, value: str, ttl: int) -> None:
    try:
        from citra_cache import get_cache_manager
        get_cache_manager().setex(key, ttl, value)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"📊 [DATA_OVERVIEW] cache set_text failed: {exc}")


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    try:
        from citra_cache import get_cache_manager
        raw = get_cache_manager().get(key)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"📊 [DATA_OVERVIEW] cache get failed: {exc}")
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _cache_set(key: str, value: Dict[str, Any]) -> None:
    try:
        from citra_cache import get_cache_manager
        payload = json.dumps(value, ensure_ascii=False, default=str)
        get_cache_manager().setex(key, CACHE_TTL_SECONDS, payload)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"📊 [DATA_OVERVIEW] cache set failed: {exc}")
