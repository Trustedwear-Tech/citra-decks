"""Suggest column values for clarify-chip UX.

Given a column name and a (possibly typo'd) value the user typed against an
uploaded structured file (CSV / Excel / JSON), return the closest matching
distinct values with their occurrence counts. The chat handler turns these
into <clarify> JSON blocks so the UI can render clickable chips.

Public API:
    suggest_column_values(file_bytes, filename, column, user_input, top_k=5)
        -> list[dict] each with keys: value, label, count, score

Notes:
- Pure pandas; no DuckDB dependency, since uploaded files are already loaded
  as bytes elsewhere in Citra-Service.
- Tries rapidfuzz first (token_set_ratio + WRatio); falls back to difflib.
- Distinct-values cache keyed by (filename, column) is kept in-memory with a
  small bounded LRU. Callers pass the same bytes for a given file so caching
  by filename only is safe within a session.
"""

from __future__ import annotations

import io
import logging
import os
from collections import OrderedDict
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# (filename, column) -> [(value_str, count), ...]  bounded LRU
_DISTINCT_CACHE: "OrderedDict[Tuple[str, str], List[Tuple[str, int]]]" = OrderedDict()
_CACHE_MAX = 64


def _excel_engine(filename: str) -> str:
    return 'xlrd' if filename.lower().endswith('.xls') else 'openpyxl'


def _load_dataframe(file_bytes: bytes, filename: str):
    """Load a structured file into a pandas DataFrame. Returns None on failure."""
    import pandas as pd

    ext = os.path.splitext(filename)[1].lower()
    buf = io.BytesIO(file_bytes)
    try:
        if ext in ('.xlsx', '.xls', '.xlsm'):
            sheets = pd.read_excel(buf, sheet_name=None, engine=_excel_engine(filename))
            # Concat all sheets so column lookup works even if user did not
            # specify a sheet. Disambiguation by sheet is a future refinement.
            frames = [df for df in sheets.values() if df is not None and not df.empty]
            if not frames:
                return None
            return pd.concat(frames, ignore_index=True, sort=False)
        if ext == '.csv':
            return pd.read_csv(buf)
        if ext == '.json':
            return pd.read_json(buf)
        if ext == '.tsv':
            return pd.read_csv(buf, sep='\t')
    except Exception as e:
        logger.warning(f"[value_suggester] failed to load {filename}: {e}")
        return None
    return None


def _resolve_column(df, column: str) -> Optional[str]:
    """Case-insensitive / whitespace-tolerant column lookup."""
    if column in df.columns:
        return column
    norm = column.strip().lower()
    for c in df.columns:
        if str(c).strip().lower() == norm:
            return c
    return None


def _distinct_with_counts(file_bytes: bytes, filename: str, column: str) -> List[Tuple[str, int]]:
    key = (filename, column)
    cached = _DISTINCT_CACHE.get(key)
    if cached is not None:
        _DISTINCT_CACHE.move_to_end(key)
        return cached

    df = _load_dataframe(file_bytes, filename)
    if df is None:
        return []
    actual_col = _resolve_column(df, column)
    if actual_col is None:
        return []

    series = df[actual_col].dropna().astype(str).str.strip()
    series = series[series != ""]
    counts = series.value_counts()
    pairs = [(str(v), int(c)) for v, c in counts.items()]

    _DISTINCT_CACHE[key] = pairs
    _DISTINCT_CACHE.move_to_end(key)
    while len(_DISTINCT_CACHE) > _CACHE_MAX:
        _DISTINCT_CACHE.popitem(last=False)
    return pairs


def _score_matches(user_input: str, candidates: List[Tuple[str, int]], top_k: int) -> List[Dict]:
    """Return top_k candidates ranked by fuzzy similarity to user_input."""
    if not candidates:
        return []

    user_norm = user_input.strip()
    if not user_norm:
        # No query — return most frequent values.
        return [
            {"value": val, "label": val, "count": cnt, "score": 0}
            for val, cnt in candidates[:top_k]
        ]

    try:
        from rapidfuzz import fuzz, process

        choices = [val for val, _ in candidates]
        # token_set_ratio handles word-order differences; WRatio handles typos.
        scored = process.extract(
            user_norm, choices, scorer=fuzz.WRatio, limit=top_k * 3
        )
        out: List[Dict] = []
        seen = set()
        for val, score, idx in scored:
            if val in seen:
                continue
            seen.add(val)
            cnt = candidates[idx][1]
            out.append({"value": val, "label": val, "count": cnt, "score": int(score)})
        out.sort(key=lambda r: (-r["score"], -r["count"]))
        return out[:top_k]
    except ImportError:
        import difflib
        choices = [val for val, _ in candidates]
        matches = difflib.get_close_matches(user_norm, choices, n=top_k, cutoff=0.4)
        out = []
        count_map = {v: c for v, c in candidates}
        for m in matches:
            ratio = int(round(difflib.SequenceMatcher(None, user_norm.lower(), m.lower()).ratio() * 100))
            out.append({"value": m, "label": m, "count": count_map.get(m, 0), "score": ratio})
        return out


async def suggest_column_values(
    file_bytes: bytes,
    filename: str,
    column: str,
    user_input: str,
    top_k: int = 5,
) -> List[Dict]:
    """Return up to ``top_k`` closest distinct values for a column.

    Each result dict has: ``value``, ``label``, ``count``, ``score`` (0-100).
    Returns [] if the file or column cannot be resolved.
    """
    import asyncio

    def _do() -> List[Dict]:
        candidates = _distinct_with_counts(file_bytes, filename, column)
        return _score_matches(user_input, candidates, top_k)

    return await asyncio.to_thread(_do)
