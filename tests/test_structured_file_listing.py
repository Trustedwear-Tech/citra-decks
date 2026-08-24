# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""Tests for ``services.structured_file_listing``.

These tests stub MongoDB at the boundary so we exercise the joining +
capping behaviour without needing a real database.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.structured_file_listing import (
    StructuredFileEntry,
    list_structured_files,
    format_schema_preview_for_prompt,
    entries_to_sandbox_files,
)


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length=None):
        return list(self._docs)


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs
        self.last_filter = None

    def find(self, query, projection=None):
        self.last_filter = query
        return _FakeCursor(list(self._docs))


class _FakeDB:
    def __init__(self, metadata_docs, files_docs):
        self._collections = {
            "structured_file_metadata": _FakeCollection(metadata_docs),
            "files": _FakeCollection(files_docs),
        }

    def __getitem__(self, name):
        return self._collections[name]


def _meta(doc_id, filename, folder_id="f1", rows=10, cols=None):
    return {
        "document_id": doc_id,
        "filename": filename,
        "folder_id": folder_id,
        "user_id": "user-a",
        "total_rows": rows,
        "file_hash": f"hash-{doc_id}",
        "columns": cols or [
            {"name": "amount", "type": "number", "samples": [1, 2, 3]},
            {"name": "category", "type": "string", "samples": ["a", "b", "c"]},
        ],
        "source_type": "excel" if filename.endswith(".xlsx") else "csv",
    }


def _file(doc_id, filename, size=1024):
    return {"_id": doc_id, "s3_key": f"s3/{doc_id}", "size": size, "filename": filename}


def _file_with_url(doc_id, filename, size=1024, bucket="citra-documents"):
    """Mimic the real ``files`` collection: ``s3_url`` + ``file_size_bytes``."""
    return {
        "_id": doc_id,
        "s3_url": f"https://{bucket}.s3.amazonaws.com/dev/uploads/{doc_id}/{filename}",
        "file_size_bytes": size,
        "filename": filename,
    }


def _run(coro):
    """Run a coroutine on a fresh event loop. See test_personal_rag_isolation
    for why ``asyncio.get_event_loop()`` is unsafe under pytest-asyncio
    asyncio_mode=auto (loops get closed between async tests, raising
    RuntimeError on the next get_event_loop call from a sync test)."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            asyncio.set_event_loop(None)
        finally:
            loop.close()


def _fake_get_async_mongo_client(metadata_docs, files_docs):
    db = _FakeDB(metadata_docs, files_docs)

    class _Client:
        def __getitem__(self, name):
            return db

    return _Client()


def _patch_mongo(metadata_docs, files_docs):
    import sys
    fake = SimpleNamespace(
        get_async_mongo_client=lambda: _fake_get_async_mongo_client(metadata_docs, files_docs),
        MONGODB_DATABASE="test",
    )
    return patch.dict(sys.modules, {"mongodb_manager": fake})


def test_list_returns_entries_joined_with_files():
    metadata = [_meta("d1", "sales.xlsx"), _meta("d2", "rev.csv")]
    files = [_file("d1", "sales.xlsx"), _file("d2", "rev.csv")]

    with _patch_mongo(metadata, files):
        result = _run(list_structured_files("user-a", folder_ids=["f1"]))

    assert len(result["entries"]) == 2
    assert {e.filename for e in result["entries"]} == {"sales.xlsx", "rev.csv"}
    assert all(e.s3_key for e in result["entries"])
    assert result["truncated_files"] == []


def test_list_caps_at_max_files():
    metadata = [_meta(f"d{i}", f"f{i}.csv") for i in range(7)]
    files = [_file(f"d{i}", f"f{i}.csv") for i in range(7)]

    with _patch_mongo(metadata, files):
        result = _run(list_structured_files("user-a", folder_ids=None, max_files=5))

    assert len(result["entries"]) == 5
    assert len(result["truncated_files"]) == 2


def test_list_caps_at_max_total_bytes():
    metadata = [_meta(f"d{i}", f"f{i}.csv") for i in range(4)]
    files = [_file(f"d{i}", f"f{i}.csv", size=30 * 1024 * 1024) for i in range(4)]

    with _patch_mongo(metadata, files):
        result = _run(list_structured_files("user-a", folder_ids=None,
                                            max_files=10, max_total_bytes=50 * 1024 * 1024))

    assert len(result["entries"]) == 1
    assert len(result["truncated_files"]) == 3


def test_list_skips_metadata_with_no_files_row():
    metadata = [_meta("d1", "sales.xlsx"), _meta("d-orphan", "deleted.csv")]
    files = [_file("d1", "sales.xlsx")]  # no row for d-orphan

    with _patch_mongo(metadata, files):
        result = _run(list_structured_files("user-a"))

    assert len(result["entries"]) == 1
    assert result["entries"][0].filename == "sales.xlsx"


def test_list_resolves_s3_key_from_s3_url():
    """Real ``files`` rows store ``s3_url`` (full URL), not ``s3_key``."""
    metadata = [_meta("d1", "equity.xlsx")]
    files = [_file_with_url("d1", "equity.xlsx", size=2048)]

    with _patch_mongo(metadata, files):
        result = _run(list_structured_files("user-a"))

    assert len(result["entries"]) == 1
    entry = result["entries"][0]
    assert entry.s3_key == "dev/uploads/d1/equity.xlsx"
    assert entry.file_size == 2048


def test_list_warns_on_orphan_metadata(caplog):
    import logging
    metadata = [_meta("d-orphan", "deleted.csv")]
    files = []

    with caplog.at_level(logging.WARNING, logger="services.structured_file_listing"):
        with _patch_mongo(metadata, files):
            result = _run(list_structured_files("user-a"))

    assert result["entries"] == []
    assert any("orphan metadata" in r.message for r in caplog.records)



def test_format_schema_preview_for_prompt_includes_filename_and_samples():
    entries = [
        StructuredFileEntry(
            document_id="d1", filename="sales.xlsx", s3_key="s3/d1",
            columns=[{"name": "amount", "type": "number", "samples": [10, 20, 30]}],
            total_rows=42, source_type="excel",
        ),
    ]
    text = format_schema_preview_for_prompt(entries)
    assert "sales.xlsx" in text
    assert "/workspace/input/sales.xlsx" in text
    assert "amount" in text
    assert "rows: 42" in text


def test_format_preview_mentions_truncated_files():
    entries = [StructuredFileEntry(document_id="d1", filename="a.csv", s3_key="s3/d1")]
    text = format_schema_preview_for_prompt(entries, truncated_files=["x.csv", "y.csv"])
    assert "x.csv" in text and "y.csv" in text


def test_entries_to_sandbox_files_shape():
    entries = [
        StructuredFileEntry(document_id="d1", filename="a.xlsx", s3_key="s3/d1"),
        StructuredFileEntry(document_id="d2", filename="b.csv", s3_key="s3/d2"),
    ]
    out = entries_to_sandbox_files(entries)
    assert out == [
        {"filename": "a.xlsx", "s3_key": "s3/d1"},
        {"filename": "b.csv", "s3_key": "s3/d2"},
    ]
