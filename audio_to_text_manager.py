# ============================  Transcripts V2 API  =============================
# Purpose: Combined transcript CRUD operations with MongoDB and Milvus integration
# Features: Audio upload, vector embeddings, full CRUD operations
# ----------------------------------------------------------------------------------------

from fastapi import APIRouter, HTTPException, Body, File, UploadFile, Form, Query, Request

from fastapi import status as http_status
from pydantic import BaseModel, Field
import uuid
import logging
import json

import os
import threading
import traceback
import asyncio
import time
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict, Any
import httpx
import redis

import tiktoken
import pytz
import pymongo
from dateutil import parser as dtp
# AWS S3 for file storage
import boto3
from bson import ObjectId

# Redis Progress Manager for distributed progress tracking
from redis_progress_manager import (
    get_progress_manager, 
    ProgressStatus, 
    ProgressType,
    update_document_progress as redis_update_audio_progress,
    get_document_progress as redis_get_audio_progress,
    clear_document_progress as redis_clear_audio_progress
)

from utils import get_user_id
from query import generate_topic_from_text, transcribe_audio
from llm_oss import llm_call

# Import credit checking for pay-as-you-go billing - MIGRATED TO MIDDLEWARE
from middleware.credit_check_middleware import (
    check_user_credits,
)
from middleware import InsufficientCreditsError
from citra_auth import get_user_email, get_secure_user_id

# Enterprise licensing model - subscription and usage tracking removed

# Import file manager for consistent filename handling
from file_manager import get_file_manager

# Import unified metadata schema for centralized namespace creation
from models.unified_metadata_schema import UnifiedMetadataSchema

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# ───────────────────────── Configuration ──────────────────────────

# Milvus/Zilliz setup - Migrated from Milvus
from config.milvus_config import (
    get_collection_name,
    get_milvus_uri,
    get_milvus_api_key,
    get_dense_vector_dim
)

# Collection name from Milvus config (environment-specific)
COLLECTION_NAME = get_collection_name()
EMBED_DIM = get_dense_vector_dim()

# MongoDB setup
MONGO_CONN = os.getenv("MONGODB_CONN_STRING")
from citra_mongo import MONGODB_DATABASE as MONGO_DB_NAME
_mongo_client = None

# Use centralized cache manager for Redis + local fallback
from citra_cache import get_cache_manager

def get_redis_client():
    """Get cache manager for concept caching"""
    try:
        return get_cache_manager()
    except Exception as e:
        logging.warning(f"Cache not available for concept caching: {e}")
        return None

# AWS S3 setup - import helper functions
from bucket import upload_file, delete_file, generate_download_url, get_environment_prefix

# SQL Server setup
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "1433")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
# Database security configuration
DB_SECURE = os.getenv("DB_SECURE", "true").lower() == "true"

MAX_AUDIO_SIZE = int(os.getenv("MAX_AUDIO_SIZE", 50))
MAX_AUDIO_DURATION_MINUTES = int(os.getenv("MAX_AUDIO_DURATION_MINUTES", 120))  # 2 hours default

# NLP setup
tokenizer = tiktoken.get_encoding("cl100k_base")
# nlp = spacy.load("en_core_web_sm")  # Removed - spacy not used

# ───────────────────────── Helper Functions ──────────────────────────

# Use centralized MongoDB manager
from citra_mongo import get_mongo_client as get_centralized_mongo_client, get_sync_database

def get_mongo_client():
    """Backward compatibility wrapper for centralized MongoDB manager"""
    return get_centralized_mongo_client()

def get_mongo_collection():
    """Get audio transcripts collection using centralized manager"""
    db = get_sync_database()
    return db["audio_transcripts"]

def token_len(text: str) -> int:
    """Return number of cl100k tokens for a given text."""
    return len(tokenizer.encode(text))

# def sentence_chunk(text: str, topic: str = "") -> Tuple[List[str], List[dict]]:
#     """Split text along sentence boundaries for chunking with enhanced metadata."""
#     CHUNK_LIMIT = int(os.getenv("CHUNK_SIZE_LIMIT", 800))
#     doc = nlp(text)
#     chunks, metas = [], []
#     buffer, meta, tokens = [], {}, 0

#     # Extract topic-level entities and keywords for better search
#     topic_entities = []
#     topic_keywords = []
#     if topic:
#         topic_doc = nlp(topic)
#         topic_entities = [ent.text for ent in topic_doc.ents]
#         topic_keywords = [token.text.lower() for token in topic_doc if token.pos_ in ["NOUN", "PROPN"] and len(token.text) > 2]

#     for s_idx, sent in enumerate(doc.sents, 1):
#         s_text = sent.text.strip()
#         s_tokens = token_len(s_text)
#         if tokens + s_tokens > CHUNK_LIMIT and buffer:
#             # Enhanced metadata for better searchability
#             chunk_meta = dict(meta)
#             if topic_entities:
#                 chunk_meta["topic_entities"] = topic_entities
#             if topic_keywords:
#                 chunk_meta["topic_keywords"] = topic_keywords
            
#             chunks.append(" ".join(buffer))
#             metas.append(chunk_meta)
#             buffer, meta, tokens = [], {}, 0

#         buffer.append(s_text)
#         tokens += s_tokens

#         # Collect NER info
#         for e_idx, ent in enumerate(sent.ents, 1):
#             meta[f"{s_idx}_ent_{e_idx}_text"] = ent.text
#             meta[f"{s_idx}_ent_{e_idx}_label"] = ent.label_
#         for np_idx, np in enumerate(sent.noun_chunks):
#             meta[f"{s_idx}_np_{np_idx}"] = np.text.strip()

#     if buffer:
#         # Final chunk metadata
#         chunk_meta = dict(meta)
#         if topic_entities:
#             chunk_meta["topic_entities"] = topic_entities
#         if topic_keywords:
#             chunk_meta["topic_keywords"] = topic_keywords
        
#         chunks.append(" ".join(buffer))
#         metas.append(chunk_meta)

#     return chunks, metas

def save_audio_to_s3_storage(audio_content: bytes, filename: str, audio_extension: str, user_id: str, transcript_id: str, is_enterprise: bool = False, entity_id: str = None, folder_id: str = None) -> str:
    """Save audio file to AWS S3 with environment-based folder structure."""
    try:
        # Sanitize user_id for consistent S3 folder naming (same as documents)
        sanitized_user_id = get_user_id(user_id)
        
        # Determine S3 folder path: {env}/{sanitized_user_id}/{personal|enterprise}/{folder_id|entity_id}/audio
        if is_enterprise:
            # Enterprise: dev/sanitized_user_id/enterprise/{entity_id or 'general'}/audio
            entity = entity_id if entity_id else "general"
            s3_folder = f"{sanitized_user_id}/enterprise/{entity}/audio"
        else:
            # Personal: dev/sanitized_user_id/personal/{folder_id or 'general'}/audio
            folder = folder_id if folder_id else "general"
            s3_folder = f"{sanitized_user_id}/personal/{folder}/audio"
        
        # Sanitize filename for S3
        safe_filename = filename.replace(' ', '_').replace('/', '_')
        if not safe_filename.endswith(f".{audio_extension}"):
            safe_filename = f"{safe_filename}.{audio_extension}"
        
        # Build S3 key (environment prefix will be added by upload_file)
        s3_key = f"{s3_folder}/{safe_filename}"
        
        # Determine content type
        content_type = f"audio/{audio_extension}" if audio_extension in ['mp3', 'wav', 'ogg', 'webm'] else "application/octet-stream"
        
        # Upload to S3
        s3_url = None
        try:
            s3_url = upload_file(audio_content, s3_key, content_type)
            logging.info(f"✅ Audio uploaded to S3: {s3_url}")
        except Exception as s3_error:
            logging.error(f"⚠️ S3 upload failed (continuing without cloud backup): {s3_error}")
            return f"local://{user_id}/audio"
        
        # S3 URL will be stored in files collection via files_service.register_file()
        return s3_url if s3_url else f"local://{user_id}/audio"
        
    except Exception as e:
        logging.error(f"⚠️ Failed to save audio to S3 (continuing): {e}")
        return f"local://{user_id}/audio"

async def delete_audio_from_s3_storage(transcript_id: str, user_id: str) -> bool:
    """Delete audio file from AWS S3 using files_service pattern."""
    try:
        from services.files_service import FilesService
        from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
        
        # Get files service
        async_mongo_client = get_async_mongo_client()
        files_service = FilesService(async_mongo_client, MONGODB_DATABASE)
        
        # Get S3 URL from files collection (single source of truth)
        file_resources = await files_service.get_file_resources(transcript_id, user_id)
        
        if not file_resources or not file_resources.get("s3_url"):
            logging.info(f"No S3 URL found in files registry for transcript {transcript_id}, skipping S3 deletion")
            return True
        
        s3_url = file_resources["s3_url"]
        
        # Extract S3 key from URL
        if ".amazonaws.com/" in s3_url:
            s3_key = s3_url.split(".amazonaws.com/")[-1]
        elif "s3://" in s3_url:
            s3_key = s3_url.split("s3://", 1)[-1].split("/", 1)[-1]
        else:
            s3_key = s3_url  # Fallback
        
        # Delete from S3
        try:
            delete_file(s3_key)
            logging.info(f"✅ Successfully deleted audio file from S3: {s3_key}")
        except Exception as e:
            # Log S3 errors but don't fail the process
            logging.warning(f"S3 delete failed (continuing): {e}")
        
        # Delete from files registry (important: prevents orphaned records)
        await files_service.delete_file(transcript_id, user_id)
        logging.info(f"✅ Deleted from files registry: {transcript_id}")
        
        return True
            
    except Exception as e:
        logging.warning(f"S3/files registry deletion failed (continuing): {e}")
        return True  # Return True to allow process to continue

def cleanup_transcript_with_llm(raw_transcript: str, user_id: str = None, user_email: str = None) -> str:
    """
    Clean up and enhance a raw Whisper transcript using the LLM.
    
    Fixes common speech-to-text issues: filler words, broken sentences,
    missing punctuation, mistranscribed words, and incoherent fragments
    that arise from noisy or multilingual audio recordings.
    
    Returns the cleaned transcript text, or the original if cleanup fails.
    """
    if not raw_transcript or not raw_transcript.strip():
        return raw_transcript

    system_prompt = (
        "You are a transcript cleanup assistant. You receive a raw speech-to-text "
        "transcript that may contain filler words, broken sentences, missing punctuation, "
        "mistranscribed words, repeated phrases, and incoherent fragments.\n\n"
        "Your task:\n"
        "1. Remove filler words (um, uh, you know, like, basically, etc.)\n"
        "2. Fix broken or incomplete sentences into coherent ones\n"
        "3. Correct obvious mistranscriptions and garbled words\n"
        "4. Add proper punctuation and paragraph breaks\n"
        "5. Preserve the original meaning, tone, and all factual content exactly\n"
        "6. Do NOT add new information, opinions, or summaries\n"
        "7. Do NOT remove any substantive content — only clean up noise\n"
        "8. If the transcript contains multilingual content, preserve all languages as-is\n\n"
        "Return ONLY the cleaned transcript text with no preamble or explanation."
    )

    try:
        cleaned = llm_call(
            system_prompt=system_prompt,
            user_prompt=raw_transcript,
            user_id=user_id,
            user_email=user_email,
            max_tokens=16000,
            temperature=0.2,
            tier="large",
        )
        if cleaned and cleaned.strip():
            logging.info(
                f"✅ LLM transcript cleanup complete | "
                f"raw={len(raw_transcript)} chars → cleaned={len(cleaned.strip())} chars"
            )
            return cleaned.strip()
        else:
            logging.warning("⚠️ LLM transcript cleanup returned empty — using raw transcript")
            return raw_transcript
    except Exception as e:
        logging.error(f"⚠️ LLM transcript cleanup failed (using raw transcript): {e}")
        return raw_transcript


async def create_embeddings_for_transcript(transcript_id: str, topic_or_filename: str, text: str, user_id: str, event_epoch: int, utc_date: str, folder_id: str = None, is_enterprise: bool = False, entity_id: Optional[str] = None, document_details: Optional[str] = None):
    """Create and store embeddings in Milvus for the transcript with uniform citation metadata."""
    # Use enhanced chunked document service for uniform chunking and embedding
    from services.enhanced_chunked_document_service import EnhancedChunkedDocumentService
    from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
    
    # Initialize enhanced service
    async_mongo_client = get_async_mongo_client()
    enhanced_service = EnhancedChunkedDocumentService(async_mongo_client, MONGODB_DATABASE)
    
    # Prepare file metadata for enhanced service
    file_metadata = {
        'topic_or_filename': topic_or_filename,
        'file_type': 'audio',
        'file_size': len(text.encode('utf-8')),
        'page_count': 1
    }
    
    # Use enhanced service for Milvus-only embedding creation and storage
    result = await enhanced_service.create_embeddings_and_store_Milvus_only(
        document_id=transcript_id,
        text=text,
        topic=topic_or_filename,
        user_id=user_id,
        utc_date=utc_date,
        file_metadata=file_metadata,
        folder_id=folder_id,
        include_topic_header=True,  # Include topic header for audio content
        is_enterprise=is_enterprise,
        entity_id=entity_id,
        document_details=document_details,
        department=None,
        store_chunks_in_mongodb=False  # Audio text stored in audio_transcripts, not document_chunked
    )
    
    return result.get('vectors_created', 0)

def _extract_topic_category(topic: str, text: str) -> str:
    """Extract topic category for better filtering."""
    if not topic:
        return "general"
    
    topic_lower = topic.lower()
    text_sample = text[:200].lower() if text else ""
    
    # Define topic categories for transcripts
    categories = {
        "meeting": ["meeting", "call", "conference", "discussion", "standup", "sync", "team"],
        "interview": ["interview", "conversation", "chat", "talk", "discussion"],
        "presentation": ["presentation", "demo", "pitch", "training", "workshop"],
        "personal": ["personal", "diary", "journal", "private", "family", "friend"],
        "work": ["work", "project", "task", "business", "client", "company"],
        "education": ["education", "course", "lecture", "learning", "study", "class"],
        "brainstorming": ["brainstorm", "ideas", "creative", "planning", "strategy"],
        "review": ["review", "feedback", "evaluation", "assessment", "retrospective"],
        "technical": ["technical", "code", "programming", "development", "software"],
        "sales": ["sales", "prospect", "client", "customer", "deal", "proposal"]
    }
    
    # Check topic and text for category keywords
    for category, keywords in categories.items():
        if any(keyword in topic_lower or keyword in text_sample for keyword in keywords):
            return category
    
    return "general"

def delete_embeddings_for_transcript(transcript_id: str, user_id: str):
    """Delete all embeddings for a transcript from Milvus."""
    try:
        from config.milvus_config import get_milvus_client, get_collection_name
        
        # Initialize Milvus client
        milvus_client = get_milvus_client()
        
        collection_name = get_collection_name()

        # Get all vector IDs for this transcript - check both audio and video collections
        coll = get_mongo_collection()
        doc = coll.find_one({"_id": transcript_id})

        # If not found in audio transcripts, check video transcripts
        if not doc:
            mongo_client = coll.database.client
            video_coll = mongo_client[MONGO_DB_NAME]["video_transcripts"]
            doc = video_coll.find_one({"_id": transcript_id})

        if doc and "total_chunks" in doc:
            vector_ids = [f"{transcript_id}_chunk_{i:04d}" for i in range(doc["total_chunks"])]
            
            # Delete vectors from Milvus using filter expression
            # Use document_id filter which is more reliable than chunk_id list
            filter_expr = f'document_id == "{transcript_id}" and user_id == "{user_id}"'
            
            try:
                delete_result = milvus_client.delete(
                    collection_name=collection_name,
                    filter=filter_expr
                )
                logging.info(f"[{transcript_id}] Deleted {len(vector_ids)} embeddings from Milvus using filter: {filter_expr}")
            except Exception as milvus_error:
                logging.error(f"[{transcript_id}] Failed to delete from Milvus: {milvus_error}")
                raise
        else:
            logging.warning(f"[{transcript_id}] No document found or no total_chunks field for Milvus deletion")
    except Exception as e:
        logging.warning(f"Failed to delete embeddings for transcript {transcript_id}: {e}")

# ───────────────────────── Pydantic Models ──────────────────────────

class TranscriptV2Summary(BaseModel):
    transcript_id: str
    topic_or_filename: str
    transcript: Optional[str] = ""  # ⚡ PERFORMANCE: Make optional for list view optimization
    duration: Optional[int] = None  # Make duration optional since video transcripts don't have it
    user_id: str
    utc_date: str
    audio_url: Optional[str] = None
    video_url: Optional[str] = None  # Add video_url field for video transcripts
    total_chunks: Optional[int] = None  # Make total_chunks optional since video transcripts don't use chunking
    transcript_type: Optional[str] = None  # Add type field to distinguish between audio and video
    entity_id: Optional[str] = None  # Add entity_id for entity ownership
    entity_name: Optional[str] = None  # Add entity_name for display

class VideoTranscriptSummary(BaseModel):
    transcript_id: str
    topic_or_filename: str
    transcript: str
    user_id: str
    utc_date: str
    video_url: Optional[str] = None
    duration: Optional[int] = None

class GetTranscriptsV2Response(BaseModel):
    transcripts: List[TranscriptV2Summary]
    total_count: int

class CreateTranscriptV2Request(BaseModel):
    topic_or_filename: str = Field("", description="Original filename or topic string")
    event_datetime: str = Field("", description="ISO format datetime")
    duration_sec: int = Field(0, description="Duration in seconds")

class CreateTranscriptV2Response(BaseModel):
    transcript_id: str
    stored_vectors: int
    audio_url: Optional[str] = None
    text: Optional[str] = None  # Full transcription text
    topic: Optional[str] = None  # Topic/title of the audio
    folder_id: Optional[str] = None  # Folder where audio is stored

class UpdateTranscriptV2Request(BaseModel):
    topic_or_filename: Optional[str] = Field(None, description="Updated topic or filename (optional)")
    transcript: Optional[str] = Field(None, description="New transcript text (optional)")

class UpdateTranscriptV2Response(BaseModel):
    transcript_id: str
    updated: bool
    updated_vectors: int
    message: str

class DeleteTranscriptV2Response(BaseModel):
    transcript_id: str
    deleted: bool
    message: str

class DeleteAllTranscriptsV2Response(BaseModel):
    user_id: str
    deleted_count: int
    deleted_vectors: int
    message: str

# ============= REUSABLE PARALLEL TASK FUNCTIONS FOR AUDIO =============
async def create_audio_milvus_task(transcript_id: str, final_topic: str, extracted_text: str, 
                                    user_id: str, event_epoch: int, utc_iso: str, folder_id: str,
                                    is_enterprise: bool = False, entity_id: Optional[str] = None, document_details: Optional[str] = None) -> Dict[str, Any]:
    """Reusable Milvus embedding and insertion task for audio transcripts"""
    try:
        logging.info(f"[{transcript_id}] 🚀 Starting parallel audio Milvus insertion...")
        stored_vectors = await create_embeddings_for_transcript(
            transcript_id=transcript_id,
            topic_or_filename=final_topic,
            text=extracted_text,
            user_id=user_id,
            event_epoch=event_epoch,
            utc_date=utc_iso,
            folder_id=folder_id,
            is_enterprise=is_enterprise,
            entity_id=entity_id,
            document_details=document_details
        )
        logging.info(f"[{transcript_id}] ✅ Audio Milvus insertion completed: {stored_vectors} vectors")
        return {"vectors_created": stored_vectors}
    except Exception as e:
        error_str = str(e)
        logging.error(f"[{transcript_id}] ❌ Audio Milvus insertion failed: {error_str}")
        
        # Re-raise credit errors so they propagate up properly
        if "insufficient_credits" in error_str.lower() or "negative balance" in error_str.lower():
            logging.info("💰 [AUDIO_MANAGER] Re-raising credit error")
        
        raise e

async def create_audio_mongodb_task(transcript_id: str, filename: str, extracted_text: str, 
                                   user_id: str, event_epoch: int, utc_iso: str, folder_id: str, 
                                   duration_sec: int, audio_url: str, stored_vectors: int, filename_param: str,
                                   is_enterprise: bool = False, entity_id: Optional[str] = None, document_details: Optional[str] = None) -> Dict[str, Any]:
    """Reusable MongoDB storage task for audio transcripts"""
    try:
        logging.info(f"[{transcript_id}] 🚀 Starting parallel audio MongoDB storage...")
        
        # Process enterprise parameters
        is_enterprise_bool = is_enterprise
        entity_id_str = entity_id if entity_id else None
        document_details_str = document_details if document_details else None
        
        # Parse datetime
        dt_obj = dtp.parse(utc_iso).astimezone(pytz.UTC)
        
        # Store in MongoDB
        mongo_doc = {
            "_id": transcript_id,
            "transcript_id": transcript_id,  # Add this field for the unique index
            "user_id": user_id,
            "topic_or_filename": filename,  # Store filename in topic_or_filename field
            "transcript": extracted_text,
            "duration": int(duration_sec or 0),
            "audio_url": audio_url,
            "utc_date": dt_obj,
            "event_epoch": event_epoch,
            "total_chunks": stored_vectors,
            "created_at": datetime.now(tz=pytz.UTC),
            "updated_at": datetime.now(tz=pytz.UTC),
            "folder_id": folder_id
        }
        
        # Add enterprise fields if present
        if is_enterprise_bool:
            mongo_doc["is_enterprise"] = is_enterprise_bool
            logging.info(f"[{transcript_id}] Adding is_enterprise: {is_enterprise_bool}")
        if entity_id_str:
            mongo_doc["entity_id"] = entity_id_str
            logging.info(f"[{transcript_id}] Adding entity_id: {entity_id_str}")
        if document_details_str:
            mongo_doc["document_details"] = document_details_str
            logging.info(f"[{transcript_id}] Adding document_details: {document_details_str}")
        
        logging.info(f"[{transcript_id}] Final mongo_doc: {mongo_doc}")

        coll = get_mongo_collection()
        
        # ✅ IMPROVED ERROR HANDLING: Insert with explicit validation
        try:
            insert_result = coll.insert_one(mongo_doc)
            
            # Validate insertion succeeded
            if not insert_result.inserted_id:
                raise Exception("MongoDB insert returned no inserted_id")
            
            # Verify document exists
            verify_doc = coll.find_one({"_id": transcript_id})
            if not verify_doc:
                raise Exception(f"Document {transcript_id} not found after insert")
            
            logging.info(f"[{transcript_id}] ✅ MongoDB document inserted and verified: {insert_result.inserted_id}")
            
        except Exception as insert_error:
            logging.error(f"[{transcript_id}] ❌ MongoDB insert failed: {insert_error}", exc_info=True)
            logging.error(f"[{transcript_id}] 📋 Failed document data: user_id={user_id}, folder_id={folder_id}, is_enterprise={is_enterprise_bool}")
            raise Exception(f"Audio MongoDB storage failed: {insert_error}") from insert_error
        
        logging.info(f"[{transcript_id}] ✅ Audio MongoDB storage completed successfully")
        return {"status": "stored", "document_id": transcript_id}
    except Exception as e:
        logging.error(f"[{transcript_id}] ❌ Audio MongoDB storage failed: {e}", exc_info=True)
        raise

async def create_audio_concept_map_task(transcript_id: str, final_topic: str, extracted_text: str, 
                                       user_id: str, folder_id: str) -> Dict[str, Any]:
    """Reusable concept map processing task for audio transcripts"""
    try:
        logging.info(f"[{transcript_id}] 🚀 Starting parallel audio concept map processing...")
        concept_map_enabled = os.getenv('CONCEPT_MAP_ENABLED', 'true').lower() == 'true'
        
        if concept_map_enabled and extracted_text.strip():
            # Check if concept extraction already happened for this transcript
            redis_client = get_redis_client()
            # Check cache first
            concept_cache_key = f"concept_processed_{transcript_id}"
            if redis_client and redis_client.get(concept_cache_key):
                logging.info(f"[{transcript_id}] ✅ Entity extraction already completed - skipping")
                return {"status": "cached"}
            else:
                # DGraph entity extraction removed - skipping knowledge graph creation
                logging.info(f"[{transcript_id}] ⚠️ DGraph entity extraction removed - no knowledge graph created")
                result = {"status": "skipped", "reason": "dgraph_removed"}
                
                # Mark as processed to prevent double execution
                if redis_client:
                    redis_client.setex(concept_cache_key, 3600, "completed")  # Cache for 1 hour
                
                return result
        else:
            logging.info(f"[{transcript_id}] ⚠️ Audio entity extraction skipped (disabled or no text)")
            return {"status": "skipped"}
    except Exception as e:
        logging.error(f"[{transcript_id}] ❌ Audio entity extraction failed: {e}")
        # Don't fail the entire upload if entity extraction fails
        return {"status": "failed", "error": str(e)}


# ============= END REUSABLE PARALLEL TASK FUNCTIONS =============

# ───────────────────────── API Endpoints ──────────────────────────

router = APIRouter()

# ═══════════════════════ Audio Upload Progress Tracking ═══════════════════════

def update_audio_progress(audio_id: str, stage: str, progress: int, metadata: dict = None):
    """Update progress for audio upload UI tracking - Enhanced with Redis distributed cache"""
    
    # Map stage to progress status
    progress_status = ProgressStatus.PROCESSING
    if stage == "error":
        progress_status = ProgressStatus.ERROR
    elif stage == "complete" and progress >= 100:
        progress_status = ProgressStatus.COMPLETED
    elif progress == 0 and stage in ["starting", "initializing"]:
        progress_status = ProgressStatus.PENDING
    
    # Update Redis cache (distributed across instances) using the existing document progress system
    # Audio uploads use the same progress infrastructure as documents
    redis_update_audio_progress(audio_id, stage, progress, progress_status, metadata=metadata)
    
    # Log progress for debugging - but only for major milestones to reduce spam
    should_log = (
        progress % 10 == 0 or  # Every 10%
        progress in [5, 15, 25, 35, 45, 55, 65, 75, 85, 95] or  # Key milestones
        progress >= 100  # Completion
    )
    
    if should_log:
        logging.info(f"[{audio_id}] 🎵 Audio Progress: {stage} - {progress}% (Redis: distributed)")

def get_audio_progress(audio_id: str) -> dict:
    """Get current progress for an audio upload - Enhanced with Redis distributed cache"""
    
    # Try Redis first (distributed cache)
    redis_progress = redis_get_audio_progress(audio_id)
    if redis_progress:
        # Convert Redis format to legacy format for backward compatibility
        return {
            "stage": redis_progress.get("stage"),
            "progress": redis_progress.get("progress"),
            "status": redis_progress.get("status"),
            "message": redis_progress.get("message"),
            "timestamp": time.time(),  # Current time for backward compatibility
            "updated_at": redis_progress.get("updated_at"),
            "metadata": redis_progress.get("metadata", {})
        }
    
    # Return not found if no progress data
    return None

def clear_audio_progress(audio_id: str):
    """Clear progress tracking for an audio upload - Enhanced with Redis distributed cache"""
    
    # Clear Redis cache
    redis_clear_audio_progress(audio_id)
    
    logging.info(f"[{audio_id}] 🗑️ Audio progress cleared (Redis: distributed)")

# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/v2/transcripts",
    response_model=CreateTranscriptV2Response,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_transcript_v2(
    request: Request,
    topic_or_filename: str = Form(""),
    event_datetime: str = Form(""),
    duration_sec: int = Form(0),
    audio: Optional[UploadFile] = File(None),
    folder_id: str = Form(None),
    upload_id: Optional[str] = Form(None),  # Add upload_id parameter for progress tracking
    source: Optional[str] = Form("upload_audio"),  # Add source parameter to distinguish upload types
    is_enterprise: Optional[str] = Form(""),  # Add enterprise parameter
    entity_id: Optional[str] = Form(""),  # Add entity ID parameter
    document_details: Optional[str] = Form(""),  # Add document details parameter
):
    """
    POST /api/v2/transcripts (multipart/form-data)
    
    Create a new transcript with audio upload support.
    Stores data in both MongoDB and Milvus with shared UUID.
    Includes distributed progress tracking via Redis.
    
    Parameters:
    - source: Upload source type:
      * "recording" or "meeting_recording" -> Always goes to 'meetings' folder
      * "upload_audio" or other -> Respects folder_id or defaults to 'documents'
    - folder_id: Target folder (ignored for recordings, respected for file uploads)
    
    Note: UI sends audio file uploads without source parameter, so defaulting to 'upload_audio'
    to ensure they respect folder selection rather than always going to meetings folder.
    """
    # Extract authenticated user_id from JWT token
    user_id = get_secure_user_id(request)
    provided_topic_or_filename = topic_or_filename
    
    print("API hit successfully!")
    
    # Initialize progress tracking
    progress_id = upload_id or str(uuid.uuid4())
    update_audio_progress(progress_id, "analyzing", 5)
    logging.info(f"[{progress_id}] 🎵 Starting audio upload with progress tracking")
    
    try:
        if not audio:
            update_audio_progress(progress_id, "error", 0)
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Audio file is required for transcription."
            )

        import hashlib
        import tempfile
        
        # Debug: Check what FastAPI received
        logging.info(f"[{progress_id}] 📂 Audio file info: filename={audio.filename}, content_type={audio.content_type}")
        
        # Reset file pointer to beginning before reading
        await audio.seek(0)
        audio_content = await audio.read()
        
        # Debug: Check the actual content read
        logging.info(f"[{progress_id}] 📊 Audio content read successfully")
        if len(audio_content) == 0:
            logging.error(f"[{progress_id}] ❌ Audio content is empty after reading from FormData")
            # Try to reset and read again
            await audio.seek(0)
            audio_content = await audio.read()
            logging.info(f"[{progress_id}] 🔄 Retry read successful")
        else:
            logging.info(f"[{progress_id}] ✅ Audio content successfully read")
        
        # Enhanced audio file validation
        def validate_audio_file(file_content: bytes, content_type: str = None) -> tuple[bool, str]:
            """Validate audio file integrity and format"""
            if not file_content or len(file_content) == 0:
                return False, "Audio file is empty"
            
            # Check file size (minimum 1KB, maximum from MAX_AUDIO_SIZE env)
            file_size = len(file_content)
            if file_size < 1024:  # Less than 1KB
                return False, f"Audio file too small ({file_size} bytes)"
            if file_size > MAX_AUDIO_SIZE * 1024 * 1024:  # Use env variable (default 50MB)
                return False, f"Audio file too large ({file_size / 1024 / 1024:.2f} MB, max {MAX_AUDIO_SIZE} MB)"
            
            # Validate audio file signatures
            audio_signatures = {
                b'RIFF': 'audio/wav',
                b'ID3': 'audio/mpeg',
                b'\xff\xfb': 'audio/mpeg',
                b'\xff\xf3': 'audio/mpeg',
                b'\xff\xf2': 'audio/mpeg',
                b'OggS': 'audio/ogg',
                b'fLaC': 'audio/flac',
                b'\x00\x00\x00\x20ftypM4A': 'audio/mp4',
                b'\x00\x00\x00\x18ftypmp42': 'audio/mp4',
                b'\x1a\x45\xdf\xa3': 'audio/webm',  # WebM/Matroska signature
            }
            
            # Check magic numbers
            detected_type = None
            for signature, mime_type in audio_signatures.items():
                if file_content.startswith(signature):
                    detected_type = mime_type
                    break
            
            # Special check for M4A/MP4 audio
            if not detected_type and len(file_content) > 8:
                if file_content[4:8] == b'ftyp':
                    detected_type = 'audio/mp4'
            
            if not detected_type:
                return True, "Warning: Could not detect audio format from signature, proceeding with caution"
            
            return True, f"Valid audio file detected: {detected_type}"
        
        # Validate audio file
        is_valid, validation_message = validate_audio_file(audio_content, audio.content_type)
        if not is_valid:
            logging.error(f"[{progress_id}] Audio validation failed: {validation_message}")
            update_audio_progress(progress_id, "error", 0)
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=validation_message
            )
        
        logging.info(f"[{progress_id}] Audio validation: {validation_message}")
        
        # Calculate file hash for deduplication and unique ID generation
        file_hash = hashlib.md5(audio_content).hexdigest()
        
        # Generate unique transcript ID to avoid duplicates
        from datetime import datetime
        timestamp = datetime.utcnow().isoformat().replace(":", "-").replace(".", "-")
        transcript_id = f"transcript_{user_id.replace('@', '_').replace('.', '_')}_{file_hash[:8]}_{timestamp}"
        
    # Additional validation: Check for basic audio file signatures
    # This helps catch obviously corrupted files before sending for transcription
        audio_start = audio_content[:12]  # First 12 bytes for format detection
        
        # Common audio file signatures (magic numbers)
        audio_signatures = [
            b'RIFF',      # WAV files
            b'fLaC',      # FLAC files  
            b'OggS',      # OGG files
            b'ID3',       # MP3 with ID3 tag
            b'\xff\xfb',  # MP3 without ID3 (MPEG-1 Layer 3)
            b'\xff\xf3',  # MP3 without ID3 (MPEG-1 Layer 3) 
            b'\xff\xf2',  # MP3 without ID3 (MPEG-1 Layer 3)
            b'\x1a\x45\xdf\xa3',  # WebM/Matroska (EBML) signature
            b'ftypM4A',   # M4A files
            b'ftypm4a',   # M4A files (lowercase)
        ]
        
        # Check if file starts with any known audio signature
        has_valid_signature = any(audio_start.startswith(sig) for sig in audio_signatures)
        
        # For RIFF files (WAV), also check the format
        if audio_start.startswith(b'RIFF') and len(audio_content) >= 12:
            # Check if it's actually a WAV file (should have 'WAVE' at offset 8)
            if audio_content[8:12] != b'WAVE':
                logging.warning(f"[{progress_id}] RIFF file detected but not WAV format")
                has_valid_signature = False
        
        # Log file analysis for debugging
        logging.info(f"[{progress_id}] Audio file analysis: filename={audio.filename}, "
                    f"content_type={audio.content_type}, size={len(audio_content)}, "
                    f"signature_valid={has_valid_signature}, first_bytes={audio_start.hex()}")
        
        # If no valid signature detected, log warning but don't fail
        if not has_valid_signature:
            logging.warning(f"[{progress_id}] Audio file may be corrupted or unsupported format. "
                           f"First bytes: {audio_start.hex()}")
            # Continue processing - transcription service will provide a more specific error if needed

        print("user_id: ", user_id, " topic_or_filename: ", provided_topic_or_filename, " event_datetime: ", event_datetime, " duration_sec: ", duration_sec, " folder_id: ", folder_id, " source: ", source, " is_enterprise: ", is_enterprise, " entity_id: ", entity_id, " document_details: ", document_details)

        # ========== AUDIO DURATION LIMIT CHECK ==========
        if duration_sec > 0 and duration_sec > MAX_AUDIO_DURATION_MINUTES * 60:
            duration_minutes = duration_sec / 60
            logging.warning(f"[{progress_id}] ⚠️ Audio exceeds duration limit: {duration_minutes:.1f} minutes (max: {MAX_AUDIO_DURATION_MINUTES} minutes)")
            update_audio_progress(progress_id, "error", 0)
            raise HTTPException(
                status_code=http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Audio exceeds maximum duration of {MAX_AUDIO_DURATION_MINUTES} minutes ({MAX_AUDIO_DURATION_MINUTES // 60} hours). Your audio is {duration_minutes:.1f} minutes."
            )
        # ========== END DURATION LIMIT CHECK ==========

        # Process enterprise parameters
        is_enterprise_bool = is_enterprise and is_enterprise.lower() == 'true'
        entity_id_str = entity_id if entity_id else None
        document_details_str = document_details if document_details else None
        
        # Initialize file manager for consistent filename handling
        from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
        async_mongo_client = get_async_mongo_client()
        file_manager = get_file_manager(async_mongo_client, MONGODB_DATABASE)
        
        # Use original filename from upload
        original_filename = audio.filename or f"audio_{int(time.time())}.wav"
        
        # Extract file extension early for credit calculation and validation
        from pathlib import Path
        audio_extension = Path(original_filename).suffix if original_filename else ".wav"
        
        # Import folder routing logic
        from folder_routing import determine_upload_folder
        
        # Determine the appropriate folder - all audio uploads respect selected folder or default to 'general'
        folder_id = determine_upload_folder(
            content_type='audio',
            upload_source=source or 'upload_audio',
            selected_folder=folder_id
        )
        print(f"folder_id determined as '{folder_id}' for audio upload (source: {source})")
        
        # Check for duplicate filename and cleanup if exists (AFTER folder determination)
        logging.info(f"🔍 Checking for duplicate audio filename: {original_filename} in folder: {folder_id}")
        duplicate_prep = await file_manager.prepare_file_upload(user_id, original_filename, folder_id)
        if duplicate_prep.get("exists"):
            logging.info(f"📁 Duplicate audio filename found in folder {folder_id}, cleaned up existing file: {original_filename}")

        # ═══════════════════════════════════════════════════════════════════════════════════════
        # 💰 CREDIT PRE-CHECK: Verify user has positive balance before audio transcription
        # ═══════════════════════════════════════════════════════════════════════════════════════
        
        logging.info("💰 Starting credit pre-check for audio transcription...")
        
        # Calculate audio file size for logging
        audio_size_bytes = len(audio_content)
        audio_size_mb = audio_size_bytes / (1024 * 1024)
        upload_type = 'video' if audio_extension.lower() in ['.mp4', '.mov', '.avi', '.mkv', '.webm'] else 'audio'
        
        logging.info(f"💰 {upload_type.capitalize()} size: {audio_size_mb:.2f} MB | Upload type: {upload_type}")
        
        # Simple positive balance check - no pre-estimation of cost
        credit_check_result = check_user_credits(user_id, 0)
        
        if not credit_check_result['success'] or not credit_check_result.get('sufficient', False):
            # Negative balance - block transcription
            balance = credit_check_result.get('balance', 0)
            logging.error(f"❌ Negative token balance for user {user_id}: {balance:.0f} tokens")

            update_audio_progress(progress_id, "error", 0)

            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_credits",
                    "message": f"Upload failed: Your token balance is too low ({balance:.0f} tokens).",
                    "balance": balance,
                    "audio_size_mb": audio_size_mb,
                    "transcript_id": progress_id
                }
            )

        logging.info(f"✅ Credit pre-check passed for user {user_id} | Balance: {credit_check_result.get('balance', 0):.0f} tokens")

        # Stage 1: Extracting (transcription)
        update_audio_progress(progress_id, "extracting", 25)
        logging.info(f"[{progress_id}] 🔄 Audio Stage 1/5: Extracting - Transcribing audio")

        # Audio transcription request
        try:
            print("Sending audio for transcription.")
            
            # Get user email for credit tracking
            user_email = get_user_email(request)
            
            text = await asyncio.to_thread(
                transcribe_audio,
                audio_content,
                audio.content_type,
                original_filename,
                user_id,
                user_email
            )
            logging.info(f"[{progress_id}] Audio transcription successful")
        except HTTPException:
            raise
        except Exception as transcription_error:
            update_audio_progress(progress_id, "error", 0)
            logging.exception(f"[{progress_id}] ❌ Audio transcription failed")
            raise HTTPException(
                status_code=http_status.HTTP_502_BAD_GATEWAY,
                detail=f"Audio transcription failed: {transcription_error}"
            )

        if not text or not text.strip():
            update_audio_progress(progress_id, "error", 0)
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to extract text from audio or received empty text."
            )

        # Stage 1.5: Cleanup — enhance raw transcript via LLM
        logging.info(f"[{progress_id}] 🔄 Audio Stage 1.5: Cleaning up raw transcript with LLM")
        try:
            text = await asyncio.to_thread(
                cleanup_transcript_with_llm,
                text,
                user_id,
                user_email
            )
            logging.info(f"[{progress_id}] ✅ Transcript cleanup complete")
        except Exception as cleanup_error:
            # Non-fatal: proceed with raw transcript if cleanup fails
            logging.warning(f"[{progress_id}] ⚠️ Transcript cleanup failed, using raw transcript: {cleanup_error}")

        # Stage 2: Processing (topic generation and text processing)
        update_audio_progress(progress_id, "processing", 50)
        logging.info(f"[{progress_id}] 🔄 Audio Stage 2/5: Processing - Determining topic and cleaning text")

        # Use user-provided topic or generate from transcribed text
        if provided_topic_or_filename and provided_topic_or_filename.strip():
            # Use user-provided topic or filename
            final_topic = provided_topic_or_filename.strip()
            logging.info(f"Using user-provided topic_or_filename for audio: {final_topic}")
        else:
            # Generate topic from transcribed text using AI only if no topic provided
            try:
                # user_email already extracted earlier for credit tracking
                generated_topic = generate_topic_from_text(text, user_id=user_id, user_email=user_email)  # Pass user_id for token tracking
                final_topic = generated_topic if generated_topic else "Audio Recording"
                logging.info(f"Auto-generated topic for audio (no user topic provided): {final_topic}")
            except Exception as e:
                logging.error(f"Failed to generate topic from text: {e}")
                raise RuntimeError(f"Topic generation failed: {e}")

        # Generate shared UUID
        transcript_id = str(int(datetime.now().timestamp() * 1e6)) + "-" + str(uuid.uuid4())

        # Parse datetime
        if event_datetime:
            dt_obj = dtp.parse(event_datetime).astimezone(pytz.UTC)
        else:
            dt_obj = datetime.now(tz=pytz.UTC)

        event_epoch = int(dt_obj.timestamp())
        utc_iso = dt_obj.isoformat()

        # Handle audio upload to S3
        audio_url = None
        if audio and user_id:
            audio_extension = Path(original_filename).suffix.lstrip('.') if original_filename else "wav"
            # Use original filename with extension for S3 storage
            filename_with_ext = original_filename if '.' in original_filename else f"{original_filename}.{audio_extension}"
            audio_url = save_audio_to_s3_storage(
                audio_content=audio_content,
                filename=filename_with_ext,
                audio_extension=audio_extension,
                user_id=user_id,
                transcript_id=transcript_id,
                is_enterprise=is_enterprise_bool,
                entity_id=entity_id_str,
                folder_id=folder_id
            )
            
        # ============= PARALLEL PROCESSING FOR AUDIO TRANSCRIPTS =============
        # Stage 3: Embedding (vector embeddings and Milvus storage)
        update_audio_progress(progress_id, "embedding", 70)
        logging.info(f"[{progress_id}] 🔄 Audio Stage 3/5: Embedding - Creating vectors and storing in Milvus")
        
        # Run Milvus insertion, MongoDB storage, and concept mapping in parallel
        parallel_start = time.time()
        
        # Execute all three tasks in parallel using reusable functions
        logging.info(f"[{transcript_id}] 🚀 Starting parallel execution of Milvus, MongoDB, and Concept Map tasks...")
        
        try:
            milvus_result, mongodb_result, concept_result = await asyncio.gather(
                create_audio_milvus_task(transcript_id, original_filename, text, user_id, event_epoch, utc_iso, folder_id, is_enterprise_bool, entity_id_str, document_details_str),
                create_audio_mongodb_task(transcript_id, original_filename, text, user_id, event_epoch, utc_iso, folder_id, duration_sec, audio_url, 0, original_filename, is_enterprise_bool, entity_id_str, document_details_str),  # stored_vectors will be updated after milvus
                create_audio_concept_map_task(transcript_id, final_topic, text, user_id, folder_id),
                return_exceptions=True
            )
            
            # Stage 4: Finalizing (completing all storage operations)
            update_audio_progress(progress_id, "finalizing", 90)
            logging.info(f"[{progress_id}] 🔄 Audio Stage 4/5: Finalizing - Completing storage operations")
            
            parallel_time = time.time() - parallel_start
            logging.info(f"[{transcript_id}] ⚡ Parallel processing completed in {parallel_time:.3f}s")
            
            # Handle results and any exceptions
            if isinstance(milvus_result, Exception):
                logging.error(f"[{transcript_id}] ❌ Milvus task failed: {milvus_result}")
                update_audio_progress(progress_id, "error", 0)
                raise milvus_result
            else:
                stored_vectors = milvus_result['vectors_created']
                logging.info(f"[{transcript_id}] ✅ Milvus: {stored_vectors} vectors created")
            
            if isinstance(mongodb_result, Exception):
                logging.error(f"[{transcript_id}] ❌ MongoDB task failed: {mongodb_result}")
                
                # 🔄 ROLLBACK: Delete Milvus chunks to maintain consistency
                logging.warning(f"[{transcript_id}] 🔄 Rolling back Milvus chunks due to MongoDB failure...")
                try:
                    from services.enhanced_chunked_document_service import EnhancedChunkedDocumentService
                    from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
                    
                    async_mongo_client = get_async_mongo_client()
                    enhanced_service = EnhancedChunkedDocumentService(async_mongo_client, MONGODB_DATABASE)
                    
                    # Use existing delete_from_milvus method
                    rollback_success = await enhanced_service.delete_from_milvus(transcript_id, user_id, is_enterprise_bool, entity_id_str, None)
                    if rollback_success:
                        logging.info(f"[{transcript_id}] ✅ Rollback complete: Deleted Milvus chunks for {transcript_id}")
                    else:
                        logging.warning(f"[{transcript_id}] ⚠️ Rollback completed with warnings (check logs above)")
                except Exception as rollback_error:
                    logging.error(f"[{transcript_id}] ❌ Rollback failed: {rollback_error}", exc_info=True)
                    logging.error(f"[{transcript_id}] ⚠️ CRITICAL: Orphaned Milvus chunks may exist for document_id={transcript_id}")
                
                update_audio_progress(progress_id, "error", 0)
                raise mongodb_result
            else:
                logging.info(f"[{transcript_id}] ✅ MongoDB: Audio transcript stored successfully")
            
            if isinstance(concept_result, Exception):
                logging.error(f"[{transcript_id}] ❌ Concept map task failed: {concept_result}")
                # Don't fail the entire upload if concept extraction fails
                logging.warning(f"[{transcript_id}] ⚠️ Continuing with upload despite concept map failure")
            else:
                if concept_result.get('status') == 'success':
                    new_concepts = concept_result.get('new_concepts', [])
                    updated_concepts = concept_result.get('updated_concepts', [])
                    total_concepts = concept_result.get('total_concepts', 0)
                    logging.info(f"[{transcript_id}] ✅ Concepts updated successfully")
                else:
                    logging.info(f"[{transcript_id}] ⚠️ Concept map: {concept_result.get('status', 'unknown')}")
        
        except Exception as e:
            logging.error(f"[{transcript_id}] ❌ Parallel processing failed: {e}")
            raise e

        # Update MongoDB document with correct total_chunks from Milvus result
        try:
            coll = get_mongo_collection()
            coll.update_one(
                {"_id": transcript_id},
                {"$set": {"total_chunks": stored_vectors}}
            )
        except Exception as e:
            logging.warning(f"[{transcript_id}] Failed to update total_chunks in MongoDB: {e}")
        # ============= END PARALLEL PROCESSING =============
        
        # Stage 5: Complete
        update_audio_progress(progress_id, "complete", 100)
        logging.info(f"[{progress_id}] ✅ Audio Stage 5/5: Complete - Audio upload and processing finished successfully")

        # ============= FILES COLLECTION INTEGRATION =============
        # Register audio file metadata in central files collection
        try:
            from services.files_service import FilesService
            from datetime import datetime
            
            # Initialize FilesService
            async_mongo_client = get_async_mongo_client()
            files_service = FilesService(async_mongo_client, MONGODB_DATABASE)
            
            # Get Milvus primary_keys and actual _id from milvus_chunks collection
            milvus_chunks_coll = async_mongo_client[MONGODB_DATABASE]["milvus_chunks"]
            milvus_doc = await milvus_chunks_coll.find_one({"document_id": transcript_id})
            
            milvus_primary_keys = []
            milvus_chunks_id = None
            
            if milvus_doc:
                # Store the actual _id from milvus_chunks collection
                milvus_chunks_id = str(milvus_doc["_id"])
                
                # Convert vector_ids (strings) to INT64 primary_keys (same hash logic as document upload)
                if "vector_ids" in milvus_doc:
                    import hashlib
                    for vector_id in milvus_doc["vector_ids"]:
                        # Generate consistent INT64 hash from vector_id
                        id_hash = int(hashlib.sha256(str(vector_id).encode()).hexdigest()[:15], 16)
                        milvus_primary_keys.append(id_hash)
                    logging.info(f"[{transcript_id}] 📊 Converted {len(milvus_primary_keys)} vector_ids to Milvus primary_keys")
            
            # Get file extension from original filename
            file_extension = Path(original_filename).suffix.lstrip('.').lower() if original_filename else "wav"
            
            # Get file size
            file_size_bytes = len(audio_content)
            
            # Get db_size_bytes from MongoDB document
            # Audio transcripts are stored in "audio_transcripts" collection
            transcript_coll = async_mongo_client[MONGODB_DATABASE]["audio_transcripts"]
            transcript_doc = await transcript_coll.find_one({"_id": transcript_id})
            db_size_bytes = transcript_doc.get("db_size_bytes", 0) if transcript_doc else 0
            
            # Build file metadata with _id set to transcripts_id
            file_metadata = {
                "_id": transcript_id,  # Use transcript_id as primary key
                "user_id": user_id,
                "filename": original_filename,
                "file_extension": file_extension,
                "file_size_bytes": file_size_bytes,
                "db_size_bytes": db_size_bytes,  # Database storage size tracking
                "content_type": audio.content_type or f"audio/{file_extension}",
                "file_type_category": "audio",  # audio|document|video|image|note
                "topic_or_filename": final_topic,
                "upload_datetime": datetime.utcnow(),
                "last_modified_datetime": datetime.utcnow(),
                "folder_id": folder_id,
                "is_enterprise": is_enterprise_bool,
                "entity_id": entity_id_str,
                "duration_seconds": duration_sec or 0,
                "s3_url": audio_url,
                "storage_location": "s3",
                "milvus_primary_keys": milvus_primary_keys,
                "mongodb_collections": {
                    "document_chunked_ids": None,
                    "milvus_chunks_id": milvus_chunks_id,  # Actual _id from milvus_chunks
                    "transcripts_id": transcript_id,  # This IS the _id
                    "video_transcripts_id": None
                }
            }
            
            # Register file in files collection
            file_id = await files_service.register_file(file_metadata)
            logging.info(f"[{transcript_id}] ✅ Audio file registered in files collection: {file_id}")
            
        except Exception as files_error:
            # Don't fail audio upload if files registration fails - just log the error
            logging.error(f"[{transcript_id}] ⚠️ Failed to register audio file in files collection: {files_error}")
            logging.exception(files_error)
        # ============= END FILES COLLECTION INTEGRATION =============

        return CreateTranscriptV2Response(
            text=text,
            transcript_id=transcript_id,
            stored_vectors=stored_vectors,
            audio_url=audio_url,
            topic=final_topic,
            folder_id=folder_id
        )

    except HTTPException as http_exc:
        # Mark progress as error and clear after delay
        update_audio_progress(progress_id, "error", 0)
        logging.error(f"[{progress_id}] ❌ Audio upload failed with HTTP error: {http_exc.detail}")
        raise
    except Exception as exc:
        # Mark progress as error and clear after delay
        update_audio_progress(progress_id, "error", 0)
        logging.exception(f"[{progress_id}] ❌ Audio upload failed with unexpected error")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
        )

async def _get_entity_names_map(user_id: str) -> Dict[str, str]:
    """Get a mapping of entity_id to entity_name for the user"""
    try:
        # Use the same MongoDB manager as EnterpriseEntityService
        from citra_mongo import MongoDBManager
        mongo_manager = MongoDBManager()
        mongo_client = mongo_manager.get_async_client()
        entities_coll = mongo_client[mongo_manager.database_name]["enterprise_entities"]
        
        # Get all entities for this user
        entities = await entities_coll.find(
            {},  # Remove user_id filter temporarily for debugging
            {"entity_id": 1, "entity_name": 1, "user_id": 1}
        ).to_list(length=None)
        
        logging.info(f"📋 Found {len(entities)} entities for user {user_id}")
        for entity in entities:
            logging.info(f"📋 Entity: {entity}")
        
        # Create mapping
        entity_map = {entity["entity_id"]: entity["entity_name"] for entity in entities}
        logging.info(f"📋 Entity names map for user {user_id}: {entity_map}")
        return entity_map
    except Exception as e:
        logging.error(f"Failed to get entity names map: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return {}

@router.get(
    "/v2/transcripts",
    response_model=GetTranscriptsV2Response,
    status_code=http_status.HTTP_200_OK,
)
async def get_transcripts_v2_by_device(
    request: Request,
    limit: int = Query(50, description="Paging limit, default=50."),
    skip: int = Query(0, description="Paging skip, default=0."),
    query: Optional[str] = Query(None, description="Search query for transcripts (searches topic_or_filename only)."),
    folder_id: Optional[str] = Query(None, description="Filter transcripts by folder_id.")
):
    """GET /api/v2/transcripts - Get all transcripts for the authenticated user."""
    try:
        user_id = get_secure_user_id(request)
        coll = get_mongo_collection()

        # Get entity names mapping for this user
        entity_names_map = await _get_entity_names_map(user_id)

        # Resolve the correct user_id for querying (handles shared vault access)
        query_user_id = user_id
        if folder_id:
            # Check shared vault access via centralized auth (avoids sync DB calls)
            try:
                from services.authorization_service import get_authorization_service
                auth_service = get_authorization_service()
                access_result = await auth_service.check_access(
                    user_id=user_id,
                    resource_id=folder_id,
                    resource_type="vault",
                    required_permission="read"
                )
                if access_result.get("allowed") and not access_result.get("is_owner"):
                    vault_owner = access_result.get("owner_id")
                    if vault_owner:
                        query_user_id = vault_owner
                        logging.info(f"📂 Shared vault access: querying transcripts with owner_id={query_user_id}")
                        entity_names_map = await _get_entity_names_map(query_user_id)
            except Exception as auth_err:
                logging.warning(f"⚠️ Error checking shared vault access for transcripts: {auth_err}")

        # Build base query filter
        base_filter = {"user_id": query_user_id}
        
        # Add folder_id filter if provided
        if folder_id:
            base_filter["folder_id"] = folder_id

        # Add topic_or_filename search filter if query provided
        search_filter = {}
        if query and query.strip():
            search_term = query.strip()
            # Case-insensitive regex search in topic_or_filename only
            search_filter = {"topic_or_filename": {"$regex": search_term, "$options": "i"}}

        # Combine filters
        audio_filter = {**base_filter, **search_filter}
        video_filter = {**base_filter, **search_filter}

        # Get total count for filtered results from both collections
        mongo_client = coll.database.client
        video_coll = mongo_client[MONGO_DB_NAME]["video_transcripts"]
        total_count = coll.count_documents(audio_filter) + video_coll.count_documents(video_filter)

        # Get paginated results from both collections with sorting
        # Sort by utc_date descending, then apply skip/limit
        sort_criteria = [("utc_date", -1)]  # -1 for descending

        # Get audio transcripts
        audio_docs = list(coll.find(audio_filter).sort(sort_criteria).skip(skip).limit(limit))

        # Get video transcripts
        video_docs = list(video_coll.find(video_filter).sort(sort_criteria).skip(skip).limit(limit))

        # Combine and sort the results (since we need to interleave audio and video results)
        all_docs = audio_docs + video_docs
        all_docs_sorted = sorted(all_docs, key=lambda x: x.get("utc_date", ""), reverse=True)

        # Apply final pagination after combining (in case we have more results than limit)
        paginated_docs = all_docs_sorted[:limit]

        transcripts = []
        for doc in paginated_docs:
            # Determine if this is audio or video transcript
            is_video = "video_url" in doc and doc.get("video_url")

            # Format date in human readable IST format
            utc_date_formatted = ""
            if doc.get("utc_date"):
                # Convert UTC to IST (UTC+5:30)
                ist_time = doc["utc_date"] + timedelta(hours=5, minutes=30)
                utc_date_formatted = ist_time.strftime("%d %b %Y, %I:%M %p IST")

            transcript_summary = TranscriptV2Summary(
                transcript_id=str(doc["_id"]),
                topic_or_filename=doc.get("topic_or_filename", ""),
                transcript="",  # Empty - content loaded on demand via individual transcript API
                duration=doc.get("duration", 0),
                user_id=doc.get("user_id", ""),
                utc_date=utc_date_formatted,  # Use formatted IST date
                audio_url=doc.get("audio_url") if not is_video else None,
                video_url=doc.get("video_url") if is_video else None,
                total_chunks=doc.get("total_chunks", 0),
                transcript_type="video" if is_video else "audio",
                entity_id=doc.get("entity_id"),  # Add entity_id from document
                entity_name=entity_names_map.get(doc.get("entity_id")) if doc.get("entity_id") else None  # Lookup entity_name from map
            )

            transcripts.append(transcript_summary)

            # Debug logging
            entity_id = doc.get("entity_id")
            entity_name = entity_names_map.get(entity_id) if entity_id else None
            transcript_type = "video" if is_video else "audio"
            logging.info(f"{'🎥' if is_video else '🎤'} {transcript_type} transcript {str(doc['_id'])}: entity_id={entity_id}, entity_name={entity_name}")

        return GetTranscriptsV2Response(
            transcripts=transcripts,
            total_count=total_count
        )
    except Exception as exc:
        logging.exception("Failed to fetch transcripts v2")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
        )

@router.get(
    "/v2/transcript/{transcript_id}",
    response_model=TranscriptV2Summary,
    status_code=http_status.HTTP_200_OK,
)
async def get_transcript_v2_by_id(transcript_id: str, request: Request):
    """GET /api/v2/transcript/{transcript_id} - Get a specific transcript by ID."""
    try:
        # SECURITY: Authenticate user from JWT token
        from citra_auth import get_secure_user_id
        user_id = get_secure_user_id(request)

        logging.info(f"🔍 [GET_TRANSCRIPT_V2_BY_ID] Searching for transcript ID: {transcript_id}")
        coll = get_mongo_collection()
        doc = coll.find_one({"_id": transcript_id, "user_id": user_id})
        
        if not doc:
            logging.warning(f"🔍 [GET_TRANSCRIPT_V2_BY_ID] Transcript not found in transcripts collection: {transcript_id}")
            # Try to check if it's in video_transcripts collection
            mongo_client = coll.database.client
            video_coll = mongo_client[MONGO_DB_NAME]["video_transcripts"]
            video_doc = video_coll.find_one({"_id": transcript_id, "user_id": user_id})
            
            if video_doc:
                logging.info(f"🔍 [GET_TRANSCRIPT_V2_BY_ID] Found in video_transcripts collection: {transcript_id}")
                return TranscriptV2Summary(
                    transcript_id=str(video_doc["_id"]),
                    topic_or_filename=video_doc.get("topic_or_filename", ""),
                    transcript=video_doc.get("full_transcription", ""),
                    duration=video_doc.get("duration"),  # Optional for video transcripts
                    user_id=video_doc.get("user_id", ""),
                    utc_date=video_doc["utc_date"].isoformat() if video_doc.get("utc_date") else "",
                    video_url=video_doc.get("video_url"),  # Use video_url for video transcripts
                    audio_url=None,  # No audio_url for video transcripts
                    total_chunks=None,  # No chunking for video transcripts
                    transcript_type="video"
                )
            else:
                logging.warning(f"🔍 [GET_TRANSCRIPT_V2_BY_ID] Transcript not found in either collection: {transcript_id}")
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Transcript with ID '{transcript_id}' not found."
                )
        
        logging.info(f"🔍 [GET_TRANSCRIPT_V2_BY_ID] Found transcript: {transcript_id}, topic_or_filename: {doc.get('topic_or_filename', 'No topic_or_filename')}")
        return TranscriptV2Summary(
            transcript_id=str(doc["_id"]),
            topic_or_filename=doc.get("topic_or_filename", ""),
            transcript=doc.get("transcript", ""),
            duration=doc.get("duration", 0),
            user_id=doc.get("user_id", ""),
            utc_date=doc["utc_date"].isoformat() if doc.get("utc_date") else "",
            audio_url=doc.get("audio_url"),
            video_url=None,  # No video_url for audio transcripts
            total_chunks=doc.get("total_chunks", 0),
            transcript_type="audio"
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        logging.exception(f"Failed to fetch transcript v2 by ID: {transcript_id}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
        )

@router.put(
    "/v2/transcript/{transcript_id}",
    response_model=UpdateTranscriptV2Response,
    status_code=http_status.HTTP_200_OK,
)
async def update_transcript_v2(transcript_id: str, request: Request, body: UpdateTranscriptV2Request = Body(...)):
    """PUT /api/v2/transcript/{transcript_id} - Update a transcript."""
    try:
        # SECURITY: Authenticate user from JWT token
        from citra_auth import get_secure_user_id
        user_id_auth = get_secure_user_id(request)

        logging.info(f"Updating transcript {transcript_id} with body: {body}")
        if not body.topic_or_filename and not body.transcript:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="At least one of 'topic_or_filename' or 'transcript' must be provided."
            )

        coll = get_mongo_collection()
        
        # SECURITY: Check transcript exists AND belongs to authenticated user
        existing_doc = coll.find_one({"_id": transcript_id, "user_id": user_id_auth})
        if not existing_doc:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Transcript with ID '{transcript_id}' not found."
            )

        # Build update document
        update_doc = {"updated_at": datetime.now(tz=pytz.UTC)}
        if body.topic_or_filename is not None:
            update_doc["topic_or_filename"] = body.topic_or_filename
        if body.transcript is not None:
            update_doc["transcript"] = body.transcript

        # Update MongoDB
        result = coll.update_one(
            {"_id": transcript_id},
            {"$set": update_doc}
        )

        updated_vectors = 0
        # If transcript text was updated, recreate embeddings
        if body.transcript is not None:
            # Delete old embeddings
            delete_embeddings_for_transcript(transcript_id, existing_doc.get("user_id", ""))
            
            # Create new embeddings
            updated_vectors = await create_embeddings_for_transcript(
                transcript_id=transcript_id,
                topic_or_filename=body.topic_or_filename if body.topic_or_filename is not None else existing_doc.get("topic_or_filename", ""),
                text=body.transcript,
                user_id=existing_doc.get("user_id", ""),
                event_epoch=existing_doc.get("event_epoch", int(datetime.now().timestamp())),
                utc_date=existing_doc.get("utc_date", datetime.now(tz=pytz.UTC)).isoformat() if isinstance(existing_doc.get("utc_date"), datetime) else str(existing_doc.get("utc_date", "")),
                folder_id=existing_doc.get("folder_id"),
                is_enterprise=existing_doc.get("is_enterprise", False),
                entity_id=existing_doc.get("entity_id"),
                document_details=existing_doc.get("document_details")
            )
            
            # Update total_chunks in MongoDB
            coll.update_one(
                {"_id": transcript_id},
                {"$set": {"total_chunks": updated_vectors}}
            )

        return UpdateTranscriptV2Response(
            transcript_id=transcript_id,
            updated=result.modified_count > 0,
            updated_vectors=updated_vectors,
            message="Transcript updated successfully" if result.modified_count > 0 else "No changes made"
        )

    except HTTPException:
        raise
    except Exception as exc:
        logging.exception("Failed to update transcript v2")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
        )

@router.delete(
    "/v2/transcript/{transcript_id}",
    response_model=DeleteTranscriptV2Response,
    status_code=http_status.HTTP_200_OK,
)
async def delete_transcript_v2(transcript_id: str, request: Request):
    """DELETE /api/v2/transcript/{transcript_id} - Delete a transcript."""
    try:
        # SECURITY: Authenticate user from JWT token
        from citra_auth import get_secure_user_id
        user_id_auth = get_secure_user_id(request)

        coll = get_mongo_collection()
        
        # SECURITY: Get document info before deletion - verify ownership
        doc = coll.find_one({"_id": transcript_id, "user_id": user_id_auth})
        is_video_transcript = False
        
        if not doc:
            # Try to check if it's in video_transcripts collection
            mongo_client = coll.database.client
            video_coll = mongo_client[MONGO_DB_NAME]["video_transcripts"]
            doc = video_coll.find_one({"_id": transcript_id, "user_id": user_id_auth})
            is_video_transcript = True
            
        if not doc:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Transcript with ID '{transcript_id}' not found."
            )

        # Delete audio/video file if it exists
        file_deleted = True
        if doc.get("audio_url") and doc.get("user_id"):
            try:
                file_deleted = await delete_audio_from_s3_storage(transcript_id, doc["user_id"])
            except Exception as e:
                logging.warning(f"Failed to delete audio for transcript {transcript_id}: {e}")
                file_deleted = False
        elif doc.get("video_url") and doc.get("user_id"):
            try:
                file_deleted = await delete_audio_from_s3_storage(transcript_id, doc["user_id"])
                logging.info(f"[{transcript_id}] Deleted video file from S3: {doc['video_url']}")
            except Exception as e:
                logging.warning(f"Failed to delete video for transcript {transcript_id}: {e}")
                file_deleted = False

        # Delete embeddings from Milvus
        delete_embeddings_for_transcript(transcript_id, doc.get("user_id", ""))

        # Delete from milvus_chunks MongoDB collection
        try:
            mongo_client = coll.database.client
            milvus_chunks_coll = mongo_client[MONGO_DB_NAME]["milvus_chunks"]
            chunks_result = milvus_chunks_coll.delete_many({"document_id": transcript_id})
            logging.info(f"[{transcript_id}] Deleted {chunks_result.deleted_count} entries from milvus_chunks collection")
        except Exception as e:
            logging.warning(f"[{transcript_id}] Failed to delete from milvus_chunks collection: {e}")

        # ===================== CONCEPT MAP PRESERVATION =====================
        # Remove document references while preserving all concepts and nodes
        try:
            concept_map_enabled = os.getenv('CONCEPT_MAP_ENABLED', 'true').lower() == 'true'
            logging.info(f"[{transcript_id}] Concept preservation check - CONCEPT_MAP_ENABLED={concept_map_enabled}")
            
            if concept_map_enabled and doc.get("user_id"):
                logging.info(f"[{transcript_id}] Concept preservation disabled - module removed")
                
                # Concept map functionality has been removed
                # This section is now disabled
                
                # Remove document references while preserving concepts
                preservation_result = {"status": "disabled", "message": "Concept map module removed"}
                
                if preservation_result.get("status") == "success":
                    logging.info(f"[{transcript_id}] ✅ Concept preservation successful - concepts preserved, references removed")
                else:
                    logging.info(f"[{transcript_id}] ℹ️ Concept preservation info: {preservation_result}")
                    
            else:
                logging.info(f"[{transcript_id}] Concept preservation skipped (disabled or no user_id)")
                
        except Exception as e:
            # Don't fail the deletion if concept preservation fails
            logging.error(f"[{transcript_id}] ❌ Concept preservation failed: {e}")
            logging.error(f"[{transcript_id}] Transcript deletion will continue without concept preservation")
        # ===================== END CONCEPT MAP PRESERVATION =====================

        # Delete from the appropriate MongoDB collection
        if is_video_transcript:
            mongo_client = coll.database.client
            video_coll = mongo_client[MONGO_DB_NAME]["video_transcripts"]
            result = video_coll.delete_one({"_id": transcript_id})
            logging.info(f"[{transcript_id}] Deleted video transcript from video_transcripts collection")
        else:
            result = coll.delete_one({"_id": transcript_id})
            logging.info(f"[{transcript_id}] Deleted audio transcript from transcripts collection")

        message = "Transcript deleted successfully"
        if not file_deleted:
            message += " (file deletion failed)"

        return DeleteTranscriptV2Response(
            transcript_id=transcript_id,
            deleted=result.deleted_count > 0,
            message=message
        )

    except HTTPException:
        raise
    except Exception as exc:
        logging.exception("Failed to delete transcript v2")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
        )

@router.delete(
    "/v2/transcripts/all",
    response_model=DeleteAllTranscriptsV2Response,
    status_code=http_status.HTTP_200_OK,
)
async def delete_all_transcripts_v2_by_device(request: Request):
    """DELETE /api/v2/transcripts/all - Delete all transcripts for the authenticated user."""
    try:
        user_id = get_secure_user_id(request)
        coll = get_mongo_collection()
        
        # Get storage info from files collection (optimized: single query for all transcripts)
        mongo_client = coll.database.client
        files_collection = mongo_client[MONGO_DB_NAME]["files"]
        
        # Get audio transcript storage from files collection
        audio_files = list(files_collection.find(
            {"user_id": user_id, "file_type_category": "audio"},
            {"file_size_bytes": 1, "db_size_bytes": 1}
        ))
        
        logging.info(f"[{user_id}] Found {len(audio_files)} audio transcripts from files collection")

        # Delete audio files if they exist (using new files_service pattern)
        audio_deletion_errors = 0
        if transcript_ids and user_id:
            try:
                for transcript_id in transcript_ids:
                    if not await delete_audio_from_s3_storage(transcript_id, user_id):
                        audio_deletion_errors += 1
            except Exception as e:
                logging.warning(f"Failed to delete audio files for device {user_id}: {e}")
                audio_deletion_errors = len(transcript_ids)

        # Delete from MongoDB audio transcripts
        result = coll.delete_many({"user_id": user_id})

        # Also delete from video transcripts collection
        video_coll = mongo_client[MONGO_DB_NAME]["video_transcripts"]
        video_result = video_coll.delete_many({"user_id": user_id})
        logging.info(f"[{user_id}] Deleted {video_result.deleted_count} video transcript(s)")
        
        # Delete from files collection
        try:
            files_delete_result = files_collection.delete_many({"user_id": user_id, "file_type_category": {"$in": ["audio", "video"]}})
            logging.info(f"[{user_id}] Deleted {files_delete_result.deleted_count} file records from files collection")
        except Exception as e:
            logging.warning(f"[{user_id}] Failed to delete file records (continuing): {e}")

        # Get transcript IDs and total vectors from actual collections (for deletion)
        cursor = coll.find({"user_id": user_id}, {"_id": 1, "total_chunks": 1, "audio_url": 1})
        transcript_ids = []
        total_vectors = 0
        
        for doc in cursor:
            transcript_id = str(doc["_id"])
            transcript_ids.append(transcript_id)
            total_vectors += doc.get("total_chunks", 0)

        # Delete embeddings from Milvus
        if transcript_ids:
            from config.milvus_config import get_milvus_client, get_collection_name
            
            # Initialize Milvus client
            milvus_client = get_milvus_client()
            
            collection_name = get_collection_name()
            
            # Delete all transcripts for this user using filter
            filter_expr = f'user_id == "{user_id}"'
            try:
                delete_result = milvus_client.delete(
                    collection_name=collection_name,
                    filter=filter_expr
                )
                logging.info(f"Deleted vectors from Milvus for user {user_id}")
            except Exception as e:
                logging.error(f"Failed to delete Milvus vectors for user {user_id}: {e}")

        # Delete from milvus_chunks MongoDB collection
        try:
            milvus_chunks_coll = mongo_client[MONGO_DB_NAME]["milvus_chunks"]
            chunks_result = milvus_chunks_coll.delete_many({"user_id": user_id})
            logging.info(f"Deleted {chunks_result.deleted_count} milvus_chunks entries for device {user_id}")
        except Exception as e:
            logging.warning(f"Failed to delete from milvus_chunks collection: {e}")
        
        message = f"Deleted {result.deleted_count} transcript(s)"
        logging.info(f"Deleted {result.deleted_count} transcript(s) and {total_vectors} vector(s) for device {user_id}")
        if audio_deletion_errors > 0:
            message += f" ({audio_deletion_errors} audio file deletion(s) failed)"

        return DeleteAllTranscriptsV2Response(
            user_id=user_id,
            deleted_count=result.deleted_count,
            deleted_vectors=total_vectors,
            message=message
        )

    except Exception as exc:
        logging.exception("Failed to delete all transcripts v2")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
        )

# ═══════════════════════ Audio Upload Progress Endpoint ═══════════════════════

@router.get("/audio/progress/{audio_id}")
async def get_audio_progress_endpoint(audio_id: str):
    """
    Get real-time progress for audio processing (with Redis distributed cache)
    Used by UI to display upload progress and analysis results across multiple service instances
    """
    try:
        progress_data = get_audio_progress(audio_id)
        
        if not progress_data:
            return {
                "audio_id": audio_id,
                "status": "not_found",
                "message": "No processing in progress for this audio",
                "progress": 0,
                "stage": "not_started"
            }
        
        # Enhanced response with proper status mapping from Redis data
        stage = progress_data.get("stage", "unknown")
        progress = progress_data.get("progress", 0)
        redis_status = progress_data.get("status", "processing")
        
        # Map Redis status to UI-friendly status
        if redis_status == "error" or stage == "error":
            status = "error"
            message = progress_data.get("message", "Audio upload failed - please try again")
        elif redis_status == "completed" or (stage == "complete" and progress >= 100):
            status = "completed"
            message = progress_data.get("message", "Audio uploaded and processed successfully")
        elif redis_status == "pending" or stage in ["starting", "initializing"]:
            status = "processing"
            message = progress_data.get("message", f"Initializing audio processing: {stage}")
        elif redis_status == "processing" or stage in ["analyzing", "extracting", "processing", "embedding", "finalizing"]:
            status = "processing"
            message = progress_data.get("message", f"Processing audio: {stage}")
        else:
            status = "processing"
            message = progress_data.get("message", f"Processing audio: {stage}")
        
        response = {
            "audio_id": audio_id,
            "stage": stage,
            "progress": progress,
            "status": status,
            "message": message,
            "timestamp": progress_data.get("timestamp", time.time()),
            "updated_at": progress_data.get("updated_at"),
            "time_since_update": progress_data.get("time_since_update"),
            "metadata": progress_data.get("metadata", {}),
            "source": "redis" if "updated_at" in progress_data else "local"
        }
        
        return response
        
    except Exception as e:
        logging.error(f"Audio progress tracking error: {e}")
        return {
            "audio_id": audio_id,
            "status": "error",
            "message": f"Error retrieving progress: {str(e)}",
            "progress": 0,
            "stage": "error"
        }
