"""
Test script to verify all 4 source types work correctly:
- document: Uses document_chunked collection
- audio: Uses audio_transcripts collection
- video: Uses video_transcripts collection
- note: Uses Notes collection

Tests:
1. Verify source_type is correctly set in Milvus metadata
2. Verify text is NOT stored in Milvus metadata
3. Verify batch_fetch_chunk_texts routes to correct MongoDB collections
4. Verify chunk_id to document_id mapping works correctly

REQUIRES: live MongoDB (Atlas) + Milvus connections with WRITE access on
audio_transcripts, video_transcripts, Notes, and document_chunked
collections. Marked `integration` so unit-test sweeps skip them. Run
explicitly with `pytest -m integration tests/test_source_types.py`.
"""

import asyncio
import logging
import pytest
from datetime import datetime
from mongodb_manager import get_async_mongo_client, MONGODB_DATABASE
from services.enhanced_chunked_document_service import EnhancedChunkedDocumentService
from pymilvus import MilvusClient
from config.milvus_config import get_collection_name, get_milvus_uri, get_milvus_api_key

# Skip until infrastructure issue is resolved: tests require WRITE access to
# audio_transcripts / video_transcripts / Notes / document_chunked Mongo
# collections, which the configured Atlas user lacks (`OperationFailure: user
# is not allowed to do action [insert]`). When Atlas IAM is updated,
# replace this skip with `pytest.mark.integration` so they run only under
# `pytest -m integration`.
pytestmark = pytest.mark.skip(
    reason="Requires Mongo write permission on transcript/Notes collections; "
    "Atlas user currently denied. Re-enable when IAM is updated."
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Test user ID
TEST_USER_ID = "test_source_types_user"

async def cleanup_test_data():
    """Clean up any existing test data"""
    logger.info("🧹 Cleaning up test data...")
    
    async_client = get_async_mongo_client()
    db = async_client[MONGODB_DATABASE]
    
    # Clean MongoDB collections
    await db["document_chunked"].delete_many({"user_id": TEST_USER_ID})
    await db["audio_transcripts"].delete_many({"user_id": TEST_USER_ID})
    await db["video_transcripts"].delete_many({"user_id": TEST_USER_ID})
    await db["Notes"].delete_many({"user_id": TEST_USER_ID})
    
    # Clean Milvus - delete vectors for test user
    try:
        uri = get_milvus_uri()
        api_key = get_milvus_api_key()
        milvus_client = MilvusClient(uri=uri, token=api_key)
        collection_name = get_collection_name()
        
        if milvus_client.has_collection(collection_name):
            # Delete test user's vectors using filter
            milvus_client.delete(
                collection_name=collection_name,
                filter=f'user_id == "{TEST_USER_ID}"'
            )
            logger.info(f"✅ Deleted test vectors for {TEST_USER_ID} from {collection_name}")
    except Exception as e:
        logger.warning(f"Could not clean Milvus collection: {e}")
    
    logger.info("✅ Cleanup complete")

async def test_document_source_type():
    """Test document source type"""
    logger.info("\n" + "="*80)
    logger.info("TEST 1: Document Source Type")
    logger.info("="*80)
    
    async_client = get_async_mongo_client()
    enhanced_service = EnhancedChunkedDocumentService(async_client, MONGODB_DATABASE)
    
    # Create test document
    doc_id = "test_doc_001"
    test_text = "This is a test document. " * 100  # Long enough to create multiple chunks
    
    result = await enhanced_service.create_embeddings_and_store_Milvus_only(
        document_id=doc_id,
        text=test_text,
        topic="Test Document",
        user_id=TEST_USER_ID,
        utc_date=datetime.utcnow().isoformat(),
        file_metadata={'filename': 'test.pdf', 'file_type': 'pdf'},
        folder_id='test_folder',
        include_topic_header=False,
        department=None,
        store_chunks_in_mongodb=True  # Documents store chunks
    )
    
    logger.info(f"✅ Created {result['vectors_created']} vectors for document")
    
    # Verify Milvus metadata
    uri = get_milvus_uri()
    api_key = get_milvus_api_key()
    milvus_client = MilvusClient(uri=uri, token=api_key)
    collection_name = get_collection_name()
    
    # Create a dummy dense vector for search (768 dimensions matching LLM)
    dummy_vector = [0.1] * 768
    
    # Search to get metadata
    results = milvus_client.search(
        collection_name=collection_name,
        data=[dummy_vector],
        anns_field="dense_vector",  # Specify dense vector field for hybrid collections
        limit=5,
        output_fields=["chunk_id", "source_type", "document_id", "text"],
        filter=f'user_id == "{TEST_USER_ID}" && document_id == "{doc_id}"'
    )[0]
    
    assert len(results) > 0, "No results found in Milvus"
    
    for hit in results:
        metadata = hit['entity']
        logger.info(f"📊 Milvus metadata: chunk_id={metadata.get('chunk_id')}, source_type={metadata.get('source_type')}, has_text={metadata.get('text') is not None}")
        
        # Assertions
        assert metadata.get('source_type') == 'document', f"Expected source_type='document', got '{metadata.get('source_type')}'"
        assert metadata.get('text') is None or metadata.get('text') == '', f"Text should NOT be stored in Milvus metadata"
        assert metadata.get('chunk_id') is not None, "chunk_id must be present"
    
    # Verify MongoDB storage
    db = async_client[MONGODB_DATABASE]
    doc_chunks = await db["document_chunked"].count_documents({
        "document_id": doc_id,
        "user_id": TEST_USER_ID
    })
    
    logger.info(f"✅ Found {doc_chunks} chunks in document_chunked collection")
    assert doc_chunks > 0, "Document chunks should be stored in document_chunked"
    
    # Test batch fetch
    chunk_ids = [metadata.get('chunk_id') for hit in results for metadata in [hit['entity']]]
    source_types = {cid: 'document' for cid in chunk_ids}
    
    chunk_texts = await enhanced_service.batch_fetch_chunk_texts(
        chunk_ids=chunk_ids,
        user_id=TEST_USER_ID,
        source_types=source_types
    )
    
    logger.info(f"✅ Fetched {len(chunk_texts)} texts via batch_fetch_chunk_texts")
    assert len(chunk_texts) > 0, "Should fetch text from document_chunked"
    
    for chunk_id, text in chunk_texts.items():
        assert text and len(text) > 0, f"Text for {chunk_id} should not be empty"
    
    logger.info("✅ Document source type test PASSED")
    return True

async def test_audio_source_type():
    """Test audio source type"""
    logger.info("\n" + "="*80)
    logger.info("TEST 2: Audio Source Type")
    logger.info("="*80)
    
    async_client = get_async_mongo_client()
    db = async_client[MONGODB_DATABASE]
    enhanced_service = EnhancedChunkedDocumentService(async_client, MONGODB_DATABASE)
    
    # Create test audio transcript
    audio_id = "test_audio_001"
    test_transcript = "This is a test audio transcript. " * 100
    
    # Store full transcript in audio_transcripts collection first
    await db["audio_transcripts"].insert_one({
        "_id": audio_id,
        "user_id": TEST_USER_ID,
        "full_transcription": test_transcript,
        "created_at": datetime.utcnow()
    })
    
    result = await enhanced_service.create_embeddings_and_store_Milvus_only(
        document_id=audio_id,
        text=test_transcript,
        topic="Test Audio",
        user_id=TEST_USER_ID,
        utc_date=datetime.utcnow().isoformat(),
        file_metadata={'filename': 'test.mp3', 'file_type': 'audio'},
        folder_id='test_folder',
        include_topic_header=False,
        department=None,
        store_chunks_in_mongodb=False  # Audio does NOT store chunks
    )
    
    logger.info(f"✅ Created {result['vectors_created']} vectors for audio")
    
    # Verify Milvus metadata
    uri = get_milvus_uri()
    api_key = get_milvus_api_key()
    milvus_client = MilvusClient(uri=uri, token=api_key)
    collection_name = get_collection_name()
    
    # Create a dummy dense vector for search
    dummy_vector = [0.1] * 768
    
    results = milvus_client.search(
        collection_name=collection_name,
        data=[dummy_vector],
        anns_field="dense_vector",  # Specify dense vector field for hybrid collections
        limit=5,
        output_fields=["chunk_id", "source_type", "document_id", "text"],
        filter=f'user_id == "{TEST_USER_ID}" && document_id == "{audio_id}"'
    )[0]
    
    assert len(results) > 0, "No results found in Milvus"
    
    chunk_ids = []
    for hit in results:
        metadata = hit['entity']
        chunk_id = metadata.get('chunk_id')
        if chunk_id and chunk_id.startswith(audio_id):
            chunk_ids.append(chunk_id)
            logger.info(f"📊 Milvus metadata: chunk_id={chunk_id}, source_type={metadata.get('source_type')}")
            
            # Assertions
            assert metadata.get('source_type') == 'audio', f"Expected source_type='audio', got '{metadata.get('source_type')}'"
            assert metadata.get('text') is None or metadata.get('text') == '', f"Text should NOT be stored in Milvus metadata"
    
    # Verify NOT in document_chunked
    doc_chunks = await db["document_chunked"].count_documents({
        "document_id": audio_id,
        "user_id": TEST_USER_ID
    })
    
    logger.info(f"✅ Found {doc_chunks} chunks in document_chunked (should be 0)")
    assert doc_chunks == 0, "Audio should NOT store chunks in document_chunked"
    
    # Test batch fetch
    source_types = {cid: 'audio' for cid in chunk_ids}
    
    chunk_texts = await enhanced_service.batch_fetch_chunk_texts(
        chunk_ids=chunk_ids,
        user_id=TEST_USER_ID,
        source_types=source_types
    )
    
    logger.info(f"✅ Fetched {len(chunk_texts)} texts via batch_fetch_chunk_texts")
    assert len(chunk_texts) > 0, "Should fetch text from audio_transcripts"
    
    for chunk_id, text in chunk_texts.items():
        assert text == test_transcript, f"All chunks should map to full transcript"
    
    logger.info("✅ Audio source type test PASSED")
    return True

async def test_video_source_type():
    """Test video source type"""
    logger.info("\n" + "="*80)
    logger.info("TEST 3: Video Source Type")
    logger.info("="*80)
    
    async_client = get_async_mongo_client()
    db = async_client[MONGODB_DATABASE]
    enhanced_service = EnhancedChunkedDocumentService(async_client, MONGODB_DATABASE)
    
    # Create test video transcript
    video_id = "test_video_001"
    test_transcript = "This is a test video transcript. " * 100
    
    # Store full transcript in video_transcripts collection first
    await db["video_transcripts"].insert_one({
        "_id": video_id,
        "user_id": TEST_USER_ID,
        "full_transcription": test_transcript,
        "created_at": datetime.utcnow()
    })
    
    result = await enhanced_service.create_embeddings_and_store_Milvus_only(
        document_id=video_id,
        text=test_transcript,
        topic="Test Video",
        user_id=TEST_USER_ID,
        utc_date=datetime.utcnow().isoformat(),
        file_metadata={'filename': 'test.mp4', 'file_type': 'video'},
        folder_id='test_folder',
        include_topic_header=False,
        department=None,
        store_chunks_in_mongodb=False  # Video does NOT store chunks
    )
    
    logger.info(f"✅ Created {result['vectors_created']} vectors for video")
    
    # Verify Milvus metadata
    uri = get_milvus_uri()
    api_key = get_milvus_api_key()
    milvus_client = MilvusClient(uri=uri, token=api_key)
    collection_name = get_collection_name()
    
    # Create a dummy dense vector for search
    dummy_vector = [0.1] * 768
    
    results = milvus_client.search(
        collection_name=collection_name,
        data=[dummy_vector],
        anns_field="dense_vector",  # Specify dense vector field for hybrid collections
        limit=5,
        output_fields=["chunk_id", "source_type", "document_id", "text"],
        filter=f'user_id == "{TEST_USER_ID}" && document_id == "{video_id}"'
    )[0]
    
    assert len(results) > 0, "No results found in Milvus"
    
    chunk_ids = []
    for hit in results:
        metadata = hit['entity']
        chunk_id = metadata.get('chunk_id')
        if chunk_id and chunk_id.startswith(video_id):
            chunk_ids.append(chunk_id)
            logger.info(f"📊 Milvus metadata: chunk_id={chunk_id}, source_type={metadata.get('source_type')}")
            
            # Assertions
            assert metadata.get('source_type') == 'video', f"Expected source_type='video', got '{metadata.get('source_type')}'"
            assert metadata.get('text') is None or metadata.get('text') == '', f"Text should NOT be stored in Milvus metadata"
    
    # Verify NOT in document_chunked
    doc_chunks = await db["document_chunked"].count_documents({
        "document_id": video_id,
        "user_id": TEST_USER_ID
    })
    
    logger.info(f"✅ Found {doc_chunks} chunks in document_chunked (should be 0)")
    assert doc_chunks == 0, "Video should NOT store chunks in document_chunked"
    
    # Test batch fetch
    source_types = {cid: 'video' for cid in chunk_ids}
    
    chunk_texts = await enhanced_service.batch_fetch_chunk_texts(
        chunk_ids=chunk_ids,
        user_id=TEST_USER_ID,
        source_types=source_types
    )
    
    logger.info(f"✅ Fetched {len(chunk_texts)} texts via batch_fetch_chunk_texts")
    assert len(chunk_texts) > 0, "Should fetch text from video_transcripts"
    
    for chunk_id, text in chunk_texts.items():
        assert text == test_transcript, f"All chunks should map to full transcript"
    
    logger.info("✅ Video source type test PASSED")
    return True

async def test_note_source_type():
    """Test note source type"""
    logger.info("\n" + "="*80)
    logger.info("TEST 4: Note Source Type")
    logger.info("="*80)
    
    async_client = get_async_mongo_client()
    db = async_client[MONGODB_DATABASE]
    enhanced_service = EnhancedChunkedDocumentService(async_client, MONGODB_DATABASE)
    
    # Create test note
    note_id = "test_note_001"
    test_text = "This is a test note. " * 100
    
    # Store full text in Notes collection first
    await db["Notes"].insert_one({
        "_id": note_id,
        "user_id": TEST_USER_ID,
        "text": test_text,
        "title": "Test Note",
        "created_at": datetime.utcnow()
    })
    
    result = await enhanced_service.create_embeddings_and_store_Milvus_only(
        document_id=note_id,
        text=test_text,
        topic="Test Note",
        user_id=TEST_USER_ID,
        utc_date=datetime.utcnow().isoformat(),
        file_metadata={'filename': 'test.txt', 'file_type': 'notes'},
        folder_id='test_folder',
        include_topic_header=False,
        department=None,
        store_chunks_in_mongodb=False  # Notes do NOT store chunks
    )
    
    logger.info(f"✅ Created {result['vectors_created']} vectors for note")
    
    # Verify Milvus metadata
    uri = get_milvus_uri()
    api_key = get_milvus_api_key()
    milvus_client = MilvusClient(uri=uri, token=api_key)
    collection_name = get_collection_name()
    
    # Create a dummy dense vector for search
    dummy_vector = [0.1] * 768
    
    results = milvus_client.search(
        collection_name=collection_name,
        data=[dummy_vector],
        anns_field="dense_vector",  # Specify dense vector field for hybrid collections
        limit=5,
        output_fields=["chunk_id", "source_type", "document_id", "text"],
        filter=f'user_id == "{TEST_USER_ID}" && document_id == "{note_id}"'
    )[0]
    
    assert len(results) > 0, "No results found in Milvus"
    
    chunk_ids = []
    for hit in results:
        metadata = hit['entity']
        chunk_id = metadata.get('chunk_id')
        if chunk_id and chunk_id.startswith(note_id):
            chunk_ids.append(chunk_id)
            logger.info(f"📊 Milvus metadata: chunk_id={chunk_id}, source_type={metadata.get('source_type')}")
            
            # Assertions
            assert metadata.get('source_type') == 'note', f"Expected source_type='note', got '{metadata.get('source_type')}'"
            assert metadata.get('text') is None or metadata.get('text') == '', f"Text should NOT be stored in Milvus metadata"
    
    # Verify NOT in document_chunked
    doc_chunks = await db["document_chunked"].count_documents({
        "document_id": note_id,
        "user_id": TEST_USER_ID
    })
    
    logger.info(f"✅ Found {doc_chunks} chunks in document_chunked (should be 0)")
    assert doc_chunks == 0, "Notes should NOT store chunks in document_chunked"
    
    # Test batch fetch
    source_types = {cid: 'note' for cid in chunk_ids}
    
    chunk_texts = await enhanced_service.batch_fetch_chunk_texts(
        chunk_ids=chunk_ids,
        user_id=TEST_USER_ID,
        source_types=source_types
    )
    
    logger.info(f"✅ Fetched {len(chunk_texts)} texts via batch_fetch_chunk_texts")
    assert len(chunk_texts) > 0, "Should fetch text from Notes collection"
    
    for chunk_id, text in chunk_texts.items():
        assert text == test_text, f"All chunks should map to full note text"
    
    logger.info("✅ Note source type test PASSED")
    return True

async def test_mixed_source_types():
    """Test batch fetch with mixed source types"""
    logger.info("\n" + "="*80)
    logger.info("TEST 5: Mixed Source Types in Single Batch Fetch")
    logger.info("="*80)
    
    async_client = get_async_mongo_client()
    enhanced_service = EnhancedChunkedDocumentService(async_client, MONGODB_DATABASE)
    
    # Collect all chunk IDs from previous tests
    uri = get_milvus_uri()
    api_key = get_milvus_api_key()
    milvus_client = MilvusClient(uri=uri, token=api_key)
    collection_name = get_collection_name()
    
    # Get all vectors
    all_results = milvus_client.search(
        collection_name=collection_name,
        data=[[0.1] * 768],  # Dummy vector
        anns_field="dense_vector",  # Specify dense vector field for hybrid collections
        limit=100,
        output_fields=["chunk_id", "source_type"],
        filter=f'user_id == "{TEST_USER_ID}"'
    )[0]
    
    # Group by source type
    chunk_ids_by_type = {}
    source_types = {}
    
    for hit in all_results:
        metadata = hit['entity']
        chunk_id = metadata.get('chunk_id')
        source_type = metadata.get('source_type')
        
        if chunk_id and source_type:
            chunk_ids_by_type.setdefault(source_type, []).append(chunk_id)
            source_types[chunk_id] = source_type
    
    logger.info(f"📊 Found chunks by type: {[(k, len(v)) for k, v in chunk_ids_by_type.items()]}")
    
    # Test batch fetch with ALL chunk IDs
    all_chunk_ids = list(source_types.keys())
    
    chunk_texts = await enhanced_service.batch_fetch_chunk_texts(
        chunk_ids=all_chunk_ids,
        user_id=TEST_USER_ID,
        source_types=source_types
    )
    
    logger.info(f"✅ Fetched {len(chunk_texts)} texts from mixed source types")
    
    # Verify we got texts for all chunk IDs
    assert len(chunk_texts) == len(all_chunk_ids), f"Should fetch all {len(all_chunk_ids)} chunks"
    
    # Verify each chunk has text
    for chunk_id in all_chunk_ids:
        assert chunk_id in chunk_texts, f"Missing text for {chunk_id}"
        assert chunk_texts[chunk_id] and len(chunk_texts[chunk_id]) > 0, f"Empty text for {chunk_id}"
    
    logger.info("✅ Mixed source types test PASSED")
    return True

async def main():
    """Run all tests"""
    try:
        # Cleanup first
        await cleanup_test_data()
        
        # Run all tests
        test_results = []
        
        test_results.append(("Document", await test_document_source_type()))
        test_results.append(("Audio", await test_audio_source_type()))
        test_results.append(("Video", await test_video_source_type()))
        test_results.append(("Note", await test_note_source_type()))
        test_results.append(("Mixed", await test_mixed_source_types()))
        
        # Summary
        logger.info("\n" + "="*80)
        logger.info("TEST SUMMARY")
        logger.info("="*80)
        
        all_passed = True
        for test_name, passed in test_results:
            status = "✅ PASSED" if passed else "❌ FAILED"
            logger.info(f"{test_name}: {status}")
            if not passed:
                all_passed = False
        
        logger.info("="*80)
        
        if all_passed:
            logger.info("🎉 ALL TESTS PASSED! 4-source-type architecture is working correctly.")
        else:
            logger.error("❌ SOME TESTS FAILED. Please review the errors above.")
        
        # Cleanup after tests
        await cleanup_test_data()
        
        return all_passed
        
    except Exception as e:
        logger.error(f"❌ Test suite failed with error: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
