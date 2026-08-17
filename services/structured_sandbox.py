# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""
Helpers that drive the LLM ➜ sandbox `execute_code` pipeline against a user's
structured vault files (Excel/CSV/JSON).

The flow is:

1. List the user's structured files for the requested folders via
   :func:`services.structured_file_listing.list_structured_files`.
2. Hand the schema preview to the LLM with a system prompt that asks for a
   small Python script.
3. Run the returned script in the action sandbox with the original files
   mounted at ``/workspace/input/``.
4. Return the raw stdout / stderr to the caller along with the parsed file
   entries — the caller is responsible for interpreting stdout (JSON, markdown
   table, etc.) and shaping the API response.

This module is the single source of truth for the sandbox path so multiple
endpoints (composer chart/table, presentation editor, …) stay in lock-step.
"""

from __future__ import annotations

import asyncio
import logging
import re
import textwrap
import uuid
from typing import Any, Dict, List, Optional

from services.structured_file_listing import (
    list_structured_files,
    format_schema_preview_for_prompt,
)

logger = logging.getLogger(__name__)


_DATETIME_PRELUDE = textwrap.dedent(
    """
    import pandas as pd

    def _citra_enforce_datetime(df):
        try:
            cols = set(str(c) for c in getattr(df, 'columns', []))
            required = {'Date', 'Start Time', 'End Time'}
            if not required.issubset(cols):
                return df
            df = df.copy()
            df['Start_DateTime'] = pd.to_datetime(
                df['Date'].astype(str) + ' ' + df['Start Time'].astype(str),
                errors='coerce'
            )
            df['End_DateTime'] = pd.to_datetime(
                df['Date'].astype(str) + ' ' + df['End Time'].astype(str),
                errors='coerce'
            )
            overnight = df['End_DateTime'] < df['Start_DateTime']
            if overnight.any():
                df.loc[overnight, 'End_DateTime'] = df.loc[overnight, 'End_DateTime'] + pd.Timedelta(days=1)
            df = df.dropna(subset=['Start_DateTime', 'End_DateTime'])
            if 'duration_minutes' not in df.columns:
                df['duration_minutes'] = (df['End_DateTime'] - df['Start_DateTime']).dt.total_seconds() / 60.0
            return df
        except Exception:
            return df

    _orig_read_csv = pd.read_csv
    _orig_read_excel = pd.read_excel
    _orig_read_json = pd.read_json

    def _citra_read_csv(*args, **kwargs):
        return _citra_enforce_datetime(_orig_read_csv(*args, **kwargs))

    def _citra_read_excel(*args, **kwargs):
        return _citra_enforce_datetime(_orig_read_excel(*args, **kwargs))

    def _citra_read_json(*args, **kwargs):
        return _citra_enforce_datetime(_orig_read_json(*args, **kwargs))

    pd.read_csv = _citra_read_csv
    pd.read_excel = _citra_read_excel
    pd.read_json = _citra_read_json
    """
).strip()


def _strip_conflicting_datetime_code(script: str) -> str:
    """Remove LLM-authored lines that conflict with enforced datetime columns."""
    out: List[str] = []
    for line in script.splitlines():
        lowered = line.lower()
        if (
            "start_datetime" in lowered
            or "end_datetime" in lowered
            or "dropna(subset=['start_datetime', 'end_datetime']" in lowered
            or 'dropna(subset=["start_datetime", "end_datetime"]' in lowered
        ):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _build_executable_script(script: str) -> str:
    cleaned = _strip_conflicting_datetime_code(script)
    return f"{_DATETIME_PRELUDE}\n\n{cleaned}\n"


def _repair_hint(stderr: str) -> str:
    low = (stderr or "").lower()
    hints: List[str] = []
    if "keyerror" in low or "column" in low:
        hints.append("Handle missing columns defensively: check columns before selecting/grouping and fall back to available alternatives.")
    if "to_datetime" in low or "datetime" in low or "time" in low:
        hints.append("Use already-enforced Start_DateTime/End_DateTime/duration_minutes columns if present; do not recreate or override them.")
    if "typeerror" in low or "could not convert" in low or "ufunc" in low:
        hints.append("Coerce numeric columns with pandas.to_numeric(errors='coerce') before aggregates and drop only invalid rows involved in that metric.")
    if not hints:
        hints.append("Fix the runtime error while keeping output contract: print exactly one JSON object and no extra text.")
    return "\n".join(f"- {h}" for h in hints)


async def _execute_structured_script(
    *,
    script: str,
    user_id: str,
    entries: List[Any],
) -> Dict[str, Any]:
    from services.code_executor import execute_code

    files_for_docker = [{"filename": e.filename, "s3_key": e.s3_key} for e in entries]
    session_id = f"structured_{user_id}_{uuid.uuid4().hex[:8]}"
    return await execute_code(
        script=script,
        session_id=session_id,
        files=files_for_docker,
        output_filename="structured_output.txt",
    )


def extract_python_script(text: str) -> Optional[str]:
    """Pull a Python script out of a fenced code block (or plain text)."""
    if not text:
        return None
    for marker in ("```python", "```py", "```Python"):
        idx = text.find(marker)
        if idx != -1:
            start = idx + len(marker)
            end = text.find("```", start)
            if end != -1:
                return text[start:end].strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            candidate = parts[1].strip()
            if candidate.startswith(("python", "py")):
                candidate = candidate.split("\n", 1)[1] if "\n" in candidate else ""
            return candidate.strip() or None
    stripped = text.strip()
    if any(kw in stripped for kw in ("import ", "def ", "print(", "pandas")):
        return stripped
    return None


async def run_structured_sandbox(
    user_id: str,
    folder_ids: Optional[List[str]],
    instruction_prompt: str,
    *,
    log_prefix: str = "STRUCTURED",
) -> Dict[str, Any]:
    """
    Drive an LLM ➜ sandbox round-trip against the user's structured files.

    Returns a dict shaped like::

        {
            "success":      bool,
            "stdout":       str,
            "stderr":       str,
            "entries":      List[StructuredFileEntry],
            "error":        Optional[str],   # 'no_structured_data' | 'no_script' | 'exec_failed' | None
            "raw_response": Optional[str],
        }
    """
    listing = await list_structured_files(user_id, folder_ids=folder_ids)
    entries = listing.get("entries", [])
    if not entries:
        return {
            "success": False, "stdout": "", "stderr": "",
            "entries": [], "error": "no_structured_data", "raw_response": None,
        }

    schema_text = format_schema_preview_for_prompt(
        entries, truncated_files=listing.get("truncated_files"),
    )

    system_prompt = (
        "You write small, deterministic Python scripts that compute against user data files. "
        "The files are mounted read-only at /workspace/input/ and you have pandas, openpyxl, "
        "json, csv, and stdlib available. Your script must:\n"
        "1. Load only the files relevant to the user's request.\n"
        "2. Compute the requested aggregation / filter / chart data.\n"
        "3. Print exactly ONE JSON object (or markdown table) to stdout — no logs, no explanations.\n"
        "4. Assume execution layer enforces Date/Start Time/End Time normalization and duration_minutes; "
        "use those columns if present and do not redefine them.\n"
        "Return ONLY a fenced Python code block (```python ... ```) with the script. No prose."
    )
    user_prompt = (
        f"{schema_text}\n\n"
        f"Task:\n{instruction_prompt}\n\n"
        "Write the Python script now."
    )

    from llm_oss import llm_call
    ai_response = await asyncio.to_thread(
        llm_call,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=None,
        user_id=user_id,
        temperature=0.2,
        top_p=0.95,
        # Code that will actually be executed in the sandbox — must be the
        # strongest reasoning model. The medium tier (GLM-4.7) was producing
        # scripts that ran but gave subtly wrong results on aggregations.
        tier="large",
    )

    script = extract_python_script(ai_response)
    if not script:
        logger.warning(f"📊 [{log_prefix}] LLM returned no usable script")
        return {
            "success": False, "stdout": "", "stderr": "",
            "entries": entries, "error": "no_script", "raw_response": ai_response,
        }

    prepared_script = _build_executable_script(script)
    exec_result = await _execute_structured_script(
        script=prepared_script,
        user_id=user_id,
        entries=entries,
    )

    # Controlled retries: at most 2, and each retry must rewrite script based on concrete stderr.
    max_retries = 2
    retry_count = 0
    while (not exec_result.get("success")) and retry_count < max_retries:
        retry_count += 1
        stderr = (exec_result.get("stderr") or "").strip()
        repair_prompt = (
            f"{schema_text}\n\n"
            f"Original task:\n{instruction_prompt}\n\n"
            "Previous script failed at runtime. Rewrite a corrected script.\n"
            "Execution-layer note: Date/Start Time/End Time normalization is already enforced before your code runs.\n"
            "Use those enforced columns if present and DO NOT redefine Start_DateTime/End_DateTime.\n"
            "Failure stderr (for debugging):\n"
            f"{stderr[:2000]}\n\n"
            "Repair guidance:\n"
            f"{_repair_hint(stderr)}\n\n"
            "Return ONLY a fenced Python code block. Keep output contract: print exactly one JSON object."
        )
        try:
            repaired_response = await asyncio.to_thread(
                llm_call,
                system_prompt=system_prompt,
                user_prompt=repair_prompt,
                model=None,
                user_id=user_id,
                temperature=0.05,
                top_p=0.85,
                tier="large",
            )
            repaired_script = extract_python_script(repaired_response)
            if not repaired_script:
                logger.warning(f"📊 [{log_prefix}] retry {retry_count} produced no script")
                break
            retry_result = await _execute_structured_script(
                script=_build_executable_script(repaired_script),
                user_id=user_id,
                entries=entries,
            )
            ai_response = repaired_response
            exec_result = retry_result
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"📊 [{log_prefix}] retry {retry_count} generation failed: {exc}")
            break

    return {
        "success": bool(exec_result.get("success")),
        "stdout": exec_result.get("stdout", "") or "",
        "stderr": exec_result.get("stderr", "") or "",
        "entries": entries,
        "error": None if exec_result.get("success") else "exec_failed",
        "raw_response": ai_response,
    }
