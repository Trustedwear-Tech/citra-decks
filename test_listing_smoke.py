"""Smoke tests for unstructured + structured listings with mocked Mongo + scorer."""
import asyncio
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock


def _async_cursor(docs):
    """Return a fake Motor cursor that yields ``docs`` from to_list()."""
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.limit = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=docs)
    return cursor


def _fake_db(metadata_docs, files_docs, *, meta_collection):
    db = MagicMock()
    def _find(*args, **kwargs):
        # Heuristic: the first call goes to the metadata collection, second to "files".
        return _async_cursor([])
    coll_meta = MagicMock()
    coll_meta.find = MagicMock(side_effect=lambda *a, **k: _async_cursor(metadata_docs))
    coll_files = MagicMock()
    coll_files.find = MagicMock(side_effect=lambda *a, **k: _async_cursor(files_docs))

    def _getitem(name):
        if name == meta_collection:
            return coll_meta
        if name == "files":
            return coll_files
        return MagicMock()
    db.__getitem__.side_effect = _getitem
    return db


async def test_unstructured_listing_attached():
    """Tier 1: attached_document_ids dominates — no LLM call needed."""
    metadata_docs = [
        {"document_id": "d1", "user_id": "u1", "folder_id": "f1",
         "filename": "audit.pdf", "file_type": ".pdf",
         "summary": "SOC2 audit", "doc_type": "report",
         "semantic_tags": ["audit"], "key_entities": ["Acme"],
         "text_length": 1000, "updated_at": datetime.utcnow()},
        {"document_id": "d2", "user_id": "u1", "folder_id": "f1",
         "filename": "cat.pdf", "file_type": ".pdf",
         "summary": "cats", "doc_type": "image",
         "updated_at": datetime.utcnow()},
    ]
    files_docs = [
        {"_id": "d1", "s3_url": "https://s3.amazonaws.com/bucket/path/d1_audit.pdf",
         "file_size_bytes": 50_000, "filename": "audit.pdf"},
        {"_id": "d2", "s3_url": "https://s3.amazonaws.com/bucket/path/d2_cat.pdf",
         "file_size_bytes": 30_000, "filename": "cat.pdf"},
    ]

    fake_client = MagicMock()
    fake_client.__getitem__.return_value = _fake_db(metadata_docs, files_docs,
                                                   meta_collection="unstructured_file_metadata")

    with patch("mongodb_manager.get_async_mongo_client", return_value=fake_client), \
         patch("mongodb_manager.MONGODB_DATABASE", "test"):
        from services.unstructured_file_listing import list_unstructured_files
        result = await list_unstructured_files(
            user_id="u1",
            folder_ids=["f1"],
            attached_document_ids=["d1"],
        )
    entries = result["entries"]
    assert len(entries) == 1, f"expected 1 entry, got {len(entries)}"
    assert entries[0].document_id == "d1"
    assert entries[0].relevance_reason == "attached this turn"
    assert entries[0].s3_key == "bucket/path/d1_audit.pdf"
    print("[OK] unstructured listing — attached_document_ids tier 1")


async def test_unstructured_listing_scorer():
    """Tier 2: query → scorer keeps only matching files."""
    metadata_docs = [
        {"document_id": "d1", "user_id": "u1", "folder_id": "f1",
         "filename": "audit.pdf", "file_type": ".pdf",
         "summary": "SOC2 audit", "doc_type": "report",
         "semantic_tags": ["audit"], "key_entities": ["Acme"],
         "updated_at": datetime.utcnow()},
        {"document_id": "d2", "user_id": "u1", "folder_id": "f1",
         "filename": "cat.pdf", "file_type": ".pdf",
         "summary": "cats", "doc_type": "image",
         "updated_at": datetime.utcnow()},
    ]
    files_docs = [
        {"_id": "d1", "s3_url": "s3://bucket/path/d1.pdf", "file_size_bytes": 1000},
        {"_id": "d2", "s3_url": "s3://bucket/path/d2.pdf", "file_size_bytes": 1000},
    ]

    fake_client = MagicMock()
    fake_client.__getitem__.return_value = _fake_db(metadata_docs, files_docs,
                                                   meta_collection="unstructured_file_metadata")

    # Mock scorer to return only d1
    from services.file_relevance_scorer import ScoredFile
    async def fake_score(**kw):
        return [ScoredFile(document_id="d1", filename="audit.pdf", score=0.9, reason="audit match")]

    with patch("mongodb_manager.get_async_mongo_client", return_value=fake_client), \
         patch("mongodb_manager.MONGODB_DATABASE", "test"), \
         patch("services.file_relevance_scorer.score_files_against_query", side_effect=fake_score):
        from services.unstructured_file_listing import list_unstructured_files
        result = await list_unstructured_files(
            user_id="u1",
            folder_ids=["f1"],
            query="show me the audit doc",
        )
    entries = result["entries"]
    assert len(entries) == 1
    assert entries[0].document_id == "d1"
    assert entries[0].relevance_score == 0.9
    print("[OK] unstructured listing — query scorer tier 2")


async def test_unstructured_no_query_no_attached():
    """No query and no attached → tier 4: empty (do NOT mount everything)."""
    metadata_docs = [
        {"document_id": "d1", "user_id": "u1", "folder_id": "f1",
         "filename": "audit.pdf", "updated_at": datetime.utcnow()},
    ]
    files_docs = [{"_id": "d1", "s3_url": "s3://bucket/d1.pdf"}]

    fake_client = MagicMock()
    fake_client.__getitem__.return_value = _fake_db(metadata_docs, files_docs,
                                                   meta_collection="unstructured_file_metadata")
    with patch("mongodb_manager.get_async_mongo_client", return_value=fake_client), \
         patch("mongodb_manager.MONGODB_DATABASE", "test"):
        from services.unstructured_file_listing import list_unstructured_files
        result = await list_unstructured_files(user_id="u1", folder_ids=["f1"])
    assert result["entries"] == []
    assert result["total_available"] == 1
    print("[OK] unstructured listing - no query - empty (no bloat)")


async def test_structured_legacy_no_query():
    """structured_file_listing without query → returns full list (back-compat)."""
    metadata_docs = [
        {"document_id": "d1", "user_id": "u1", "folder_id": "f1",
         "filename": "sales.xlsx", "source_type": "excel_row",
         "columns": [{"name": "amount", "type": "float", "samples": ["100.0"]}],
         "total_rows": 500, "updated_at": datetime.utcnow()},
    ]
    files_docs = [
        {"_id": "d1", "s3_url": "https://s3.amazonaws.com/bucket/d1.xlsx",
         "file_size_bytes": 10_000, "filename": "sales.xlsx"},
    ]
    fake_client = MagicMock()
    fake_client.__getitem__.return_value = _fake_db(metadata_docs, files_docs,
                                                   meta_collection="structured_file_metadata")

    with patch("mongodb_manager.get_async_mongo_client", return_value=fake_client), \
         patch("mongodb_manager.MONGODB_DATABASE", "test"):
        from services.structured_file_listing import list_structured_files
        result = await list_structured_files(user_id="u1", folder_ids=["f1"])
    assert len(result["entries"]) == 1
    assert result["entries"][0].document_id == "d1"
    print("[OK] structured listing — legacy no-query returns full list")


async def test_structured_with_query_uses_scorer():
    """structured_file_listing with query → invokes scorer."""
    metadata_docs = [
        {"document_id": "d1", "user_id": "u1", "folder_id": "f1",
         "filename": "sales.xlsx", "source_type": "excel_row",
         "columns": [], "total_rows": 0, "updated_at": datetime.utcnow()},
        {"document_id": "d2", "user_id": "u1", "folder_id": "f1",
         "filename": "expenses.csv", "source_type": "excel_row",
         "columns": [], "total_rows": 0, "updated_at": datetime.utcnow()},
    ]
    files_docs = [
        {"_id": "d1", "s3_url": "s3://bucket/d1.xlsx"},
        {"_id": "d2", "s3_url": "s3://bucket/d2.csv"},
    ]
    fake_client = MagicMock()
    fake_client.__getitem__.return_value = _fake_db(metadata_docs, files_docs,
                                                   meta_collection="structured_file_metadata")

    from services.file_relevance_scorer import ScoredFile
    async def fake_score(**kw):
        return [ScoredFile(document_id="d2", filename="expenses.csv", score=0.8, reason="exp")]

    with patch("mongodb_manager.get_async_mongo_client", return_value=fake_client), \
         patch("mongodb_manager.MONGODB_DATABASE", "test"), \
         patch("services.file_relevance_scorer.score_files_against_query", side_effect=fake_score):
        from services.structured_file_listing import list_structured_files
        result = await list_structured_files(user_id="u1", folder_ids=["f1"], query="show expenses")
    assert len(result["entries"]) == 1
    assert result["entries"][0].document_id == "d2"
    print("[OK] structured listing — query routes through scorer")


async def main():
    await test_unstructured_listing_attached()
    await test_unstructured_listing_scorer()
    await test_unstructured_no_query_no_attached()
    await test_structured_legacy_no_query()
    await test_structured_with_query_uses_scorer()
    print("\nALL LISTING TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
