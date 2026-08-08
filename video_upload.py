import os
import uuid
import subprocess
import asyncio
import threading
import logging
import time
import traceback
import redis
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel

import motor.motor_asyncio
import os
import uuid
import subprocess
import asyncio
import threading
import logging
import time
import traceback
import redis
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

import motor.motor_asyncio
import requests
import pytz
from dateutil import parser as dtp
# AWS S3 for file storage
import boto3
from dotenv import load_dotenv

from fastapi import APIRouter, FastAPI, UploadFile, File, Form, HTTPException, status, Request
from redis_progress_manager import (
    get_progress_manager, 
    ProgressStatus, 
    ProgressType,
    update_document_progress as redis_update_video_progress,
    get_document_progress as redis_get_video_progress,
    clear_document_progress as redis_clear_video_progress
)

# Import utility functions
from utils import embed_text, get_user_id, sanitize_container_name

# Import authentication middleware
from citra_auth import get_secure_user_id, get_user_email

# Import credit checking for pay-as-you-go billing - MIGRATED TO MIDDLEWARE
from middleware.credit_check_middleware import (
    check_user_credits,
)
from middleware import InsufficientCreditsError

# Enhanced chunked document service for unified processing
from services.enhanced_chunked_document_service import EnhancedChunkedDocumentService
from citra_mongo import get_async_mongo_client, MONGODB_DATABASE

# AWS S3 setup - import helper functions
from bucket import upload_file, delete_file, generate_download_url, get_environment_prefix

# Import file manager for consistent filename handling
from file_manager import get_file_manager

# MoviePy optional import for server-side audio extraction from video
try:
    from moviepy.editor import VideoFileClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    VideoFileClip = None
    MOVIEPY_AVAILABLE = False
    logging.warning("moviepy not available. Server-side video audio extraction disabled. Client-extracted audio still supported.")

# Import topic generation utility (used when user does not supply a topic)
from query import generate_topic_from_text

# Load environment variables from .env file
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# --- Initialize FastAPI App ---
app = FastAPI(
    title="Video Processing and Storage Service",
    description="This API processes video uploads, extracts audio, transcribes it, and stores the results.",
)

# ⚡ PERFORMANCE: Initialize MongoDB indexes on startup
@app.on_event("startup")
async def startup_event():
    """Initialize MongoDB indexes for optimal query performance"""
    logging.info("🚀 Starting up video service - initializing database indexes...")
    await ensure_video_transcript_indexes()
    logging.info("✅ Video service startup complete")

# --- Configuration ---
MAX_FILE_SIZE = int(os.getenv('MAX_VIDEO_SIZE', '2048')) * 1024 * 1024  # 2GB default (increased from 100MB for 2-hour recordings)
MAX_AUDIO_SIZE = int(os.getenv('MAX_AUDIO_SIZE', '50')) * 1024 * 1024  # 50MB default for audio files
MAX_VIDEO_DURATION_MINUTES = int(os.getenv('MAX_VIDEO_DURATION_MINUTES', '180'))  # 3 hours default
# Milvus config removed - migrated to Milvus/Zilliz
EMBED_DIM = int(os.getenv("EMBED_DIM", 1024))
MONGO_CONN_STRING = os.getenv("MONGODB_CONN_STRING")
from citra_mongo import MONGODB_DATABASE as MONGO_DB_NAME
MONGO_COLLECTION_NAME = os.getenv("MONGODB_COLLECTION", "video_transcripts")

# Redis setup for concept caching
def get_redis_client():
    """Get Redis client for concept caching"""
    try:
        if os.getenv("REDIS_CACHE_ENABLED", "true").lower() == "true":
            conn_kwargs = dict(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                db=int(os.getenv("REDIS_DB", "0")),
                password=os.getenv("REDIS_PASSWORD"),
                username=os.getenv("REDIS_USERNAME"),
                decode_responses=True,
                socket_timeout=5,
            )
            if os.getenv("REDIS_SSL", "false").lower() == "true":
                conn_kwargs["ssl"] = True
                conn_kwargs["ssl_cert_reqs"] = None
            redis_client = redis.Redis(**conn_kwargs)
            redis_client.ping()  # Test connection
            return redis_client
    except Exception as e:
        logging.warning(f"Redis not available for concept caching: {e}")
    return None

# --- File Type Conversion ---
def convert_webm_to_mp4(webm_path: str) -> str:
    output_path = webm_path.replace('.webm', f'_{uuid.uuid4().hex}.mp4')
    command = [
        'ffmpeg',
        '-y',
        '-i', webm_path,
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-c:a', 'aac',
        '-movflags', '+faststart',
        output_path
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return output_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg conversion failed: {e.stderr}")

def fix_webm_metadata(webm_path: str) -> str:
    fixed_path = webm_path.replace(".webm", f"_fixed_{uuid.uuid4().hex}.webm")
    command = [
        "ffmpeg", "-y", "-i", webm_path, "-c", "copy", "-fflags", "+genpts", fixed_path
    ]
    try:
        subprocess.run(command, capture_output=True, check=True)
        return fixed_path
    except subprocess.CalledProcessError as e:
        logging.warning(f"Failed to fix webm metadata: {e.stderr}")
        return webm_path

def cleanup_old_temp_files(temp_dir: str = "temp_videos", max_age_hours: int = 24):
    """Clean up temporary files older than max_age_hours to prevent disk space issues"""
    try:
        if not os.path.exists(temp_dir):
            return
        
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        cleaned_count = 0
        
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            if os.path.isfile(file_path):
                file_age = current_time - os.path.getmtime(file_path)
                if file_age > max_age_seconds:
                    try:
                        os.remove(file_path)
                        cleaned_count += 1
                        logging.info(f"🗑️ Cleaned up old temp file: {filename} (age: {file_age/3600:.1f}h)")
                    except Exception as e:
                        logging.warning(f"Failed to clean up old temp file {filename}: {e}")
        
        if cleaned_count > 0:
            logging.info(f"🗑️ Cleanup completed: removed {cleaned_count} old temporary files")
        else:
            logging.debug(f"🗑️ Cleanup completed: no old temporary files found")
            
    except Exception as e:
        logging.error(f"Error during temp file cleanup: {e}")

# --- Lazy & Thread-Safe Client Initialization ---
# DEPRECATED: Using centralized MongoDB manager instead
# _mongo_client = None
# _mongo_lock = threading.Lock()

def get_mongo_collection():
    """Get video_transcripts collection using centralized MongoDB manager"""
    from citra_mongo import get_async_database
    db = get_async_database()
    return db[MONGO_COLLECTION_NAME]

# ⚡ PERFORMANCE: Ensure MongoDB indexes for optimal query performance
async def ensure_video_transcript_indexes():
    """Create indexes on video_transcripts collection for optimal query performance"""
    try:
        collection = get_mongo_collection()
        
        # Create indexes asynchronously
        # _id is automatically indexed by MongoDB, but we add user_id and utc_date for listing queries
        await collection.create_index([("user_id", 1), ("utc_date", -1)])  # For get_transcripts_by_device
        await collection.create_index([("user_id", 1), ("topic_or_filename", 1)])  # For search queries
        await collection.create_index([("created_at", -1)])  # For time-based queries
        
        logging.info("✅ Video transcript indexes ensured successfully")
    except Exception as e:
        logging.warning(f"⚠️ Failed to create video transcript indexes (non-critical): {e}")

# Removed: get_blob_service_client() - migrated to S3
# Use functions from bucket.py instead: upload_file, delete_file, generate_download_url

# Milvus initialization removed - migrated to Milvus/Zilliz
# All vector operations now handled by EnhancedChunkedDocumentService with Milvus

# --- Helper Functions ---
async def upload_to_s3(file_path: str, original_filename: str, user_id: str, is_enterprise: bool = False, entity_id: Optional[str] = None, folder_id: Optional[str] = None) -> str:
    """Upload video to AWS S3 with environment-based folder structure."""
    try:
        # Sanitize user_id for consistent S3 folder naming (same as documents and audio)
        sanitized_user_id = get_user_id(user_id)
        
        # Determine S3 folder path: {env}/{sanitized_user_id}/{personal|enterprise}/{folder_id|entity_id}/videos
        if is_enterprise:
            # Enterprise: dev/sanitized_user_id/enterprise/{entity_id or 'general'}/videos
            entity = entity_id if entity_id else "general"
            s3_folder = f"{sanitized_user_id}/enterprise/{entity}/videos"
        else:
            # Personal: dev/sanitized_user_id/personal/{folder_id or 'general'}/videos
            folder = folder_id if folder_id else "general"
            s3_folder = f"{sanitized_user_id}/personal/{folder}/videos"
        
        # Sanitize filename for S3
        safe_filename = original_filename.replace(' ', '_').replace('/', '_')
        
        # Build S3 key (environment prefix will be added by upload_file)
        s3_key = f"{s3_folder}/{safe_filename}"
        
        # Determine content type
        file_ext = Path(original_filename).suffix.lower()
        content_type_map = {
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.mkv': 'video/x-matroska'
        }
        content_type = content_type_map.get(file_ext, 'application/octet-stream')
        
        # Upload to S3
        try:
            with open(file_path, "rb") as data:
                file_content = data.read()
            
            s3_url = upload_file(file_content, s3_key, content_type)
            logging.info(f"✅ Video uploaded to S3: {s3_url}")
            return s3_url
        except Exception as s3_error:
            logging.error(f"⚠️ S3 upload failed (continuing with local reference): {s3_error}")
            return f"local://{user_id}/{safe_filename}"
            
    except Exception as e:
        logging.error(f"⚠️ Failed to upload video to S3: {e}")
        return f"local://{user_id}/{original_filename}"

def extract_audio_from_video(video_path: str, audio_path: str, duration: float = None):
    try:
        if not MOVIEPY_AVAILABLE:
            raise ValueError("MoviePy is not available. Please install moviepy>=1.0.3 to enable video processing.")
        
        logging.info(f"Extracting audio from video: {video_path} -> {audio_path} (duration hint: {duration})")
        video_clip = VideoFileClip(video_path)
        audio_clip = video_clip.audio
        if audio_clip is None:
            raise ValueError("The uploaded video does not contain an audio track.")

        audio_clip.write_audiofile(audio_path, codec='mp3', bitrate='128k', logger=None, verbose=False)

        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            raise ValueError("Audio extraction failed - output file is missing or empty")

        logging.info(f"Audio extraction successful: {audio_path} ({os.path.getsize(audio_path)} bytes)")

    except Exception as e:
        logging.error(f"Audio extraction failed for {video_path}: {e}")
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception:
                # Announce loudly, but do NOT raise here — the real failure
                # (audio extraction) is re-raised below and must not be masked
                # by a temp-file-cleanup error.
                logging.error(
                    f"Failed to clean up temp audio file {audio_path} after "
                    f"extraction error; leaking temp file on disk",
                    exc_info=True,
                )
        raise ValueError(f"Failed to extract audio from video: {str(e)}")

def transcribe_audio(audio_path: str, user_id: str = None, user_email: str = None) -> str:
    """
    Transcribe audio file using configured audio-to-text API.
    """
    try:
        file_extension = Path(audio_path).suffix.lower()
        if file_extension == '.mp3':
            mime_type = 'audio/mpeg'
        elif file_extension == '.wav':
            mime_type = 'audio/wav'
        elif file_extension == '.m4a':
            mime_type = 'audio/mp4'
        elif file_extension == '.webm':
            mime_type = 'audio/webm'
        else:
            mime_type = 'audio/mpeg'
        
        logging.info(f"Transcribing audio file: {audio_path} (mime_type: {mime_type})")
        
        # Import audio transcription function
        from query import transcribe_audio
        
        # Read audio file
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        
        # Transcribe audio with user tracking
        transcription = transcribe_audio(
            audio_bytes,
            mime_type,
            os.path.basename(audio_path),
            user_id=user_id,
            user_email=user_email
        )
        
        if not transcription or not transcription.strip():
            logging.warning(f"Empty transcription received for {audio_path}")
            raise ValueError("API returned empty transcription")
        
        logging.info(f"✅ Audio transcription successful: {len(transcription)} characters")
        return transcription
        
    except Exception as e:
        error_str = str(e)
        logging.error(f"Audio transcription failed for {audio_path}: {error_str}")
        
        # Re-raise credit errors so they propagate up properly
        if "insufficient_credits" in error_str.lower() or "negative balance" in error_str.lower():
            logging.info("💰 [VIDEO_UPLOAD] Re-raising credit error")
            raise
        
        raise ValueError(f"Transcription failed: {error_str}")


# --- Pydantic Models ---
class Transcript(BaseModel):
    _id: str
    user_id: str
    video_url: str
    original_filename: str
    full_transcription: str | None = None
    topic: str
    status: str
    created_at: datetime
    utc_date: datetime
    error_message: str | None = None
    total_chunks: int | None = None

# ============= REUSABLE PARALLEL TASK FUNCTIONS FOR VIDEO =============
async def create_video_embedding_task(transcript_id: str, final_topic: str, extracted_text: str, 
                                    user_id: str, event_epoch: int, utc_iso: str, folder_id: str, 
                                    video_url: str, is_enterprise: bool = False, entity_id: str = None) -> Dict[str, Any]:
    """Reusable Milvus embedding and insertion task for video transcripts"""
    try:
        logging.info(f"[{transcript_id}] 🚀 Starting parallel video Milvus insertion...")
        
        # Parse datetime object from ISO string
        dt_obj = dtp.parse(utc_iso).astimezone(pytz.UTC)
        
        # Milvus metadata removed - now handled by Milvus through EnhancedChunkedDocumentService
        # All vector metadata is managed in Milvus collection
        
        # Use enhanced chunked document service for unified processing
        async_mongo_client = get_async_mongo_client()
        enhanced_service = EnhancedChunkedDocumentService(async_mongo_client, MONGODB_DATABASE)
        
        # Prepare file metadata for enhanced service
        filename = f"{final_topic}.mp4" if final_topic else f"video_{transcript_id}.mp4"
        file_metadata = {
            'filename': filename,
            'file_type': 'video',
            'file_size': len(extracted_text.encode('utf-8')),
            'page_count': 1
        }
        
        # Create metadata for enhanced service
        metadata = {
            'video_url': video_url,
            'user_id': user_id,
            'topic': final_topic,
            'utc_date': dt_obj.isoformat(),
            'event_epoch': event_epoch,
            'folder_id': folder_id,
            'document_type': 'video',
            'content_type': 'meeting',
            'source_file': filename,
            'created_at': dt_obj.isoformat()
        }
        
        # Use enhanced service for chunking and embedding
        result = await enhanced_service.create_embeddings_and_store_Milvus_only(
            document_id=transcript_id,
            topic=final_topic,
            text=extracted_text,
            user_id=user_id,
            utc_date=utc_iso,
            folder_id=folder_id,
            file_metadata=file_metadata,
            include_topic_header=True,  # Include topic header for video content
            department=None,
            store_chunks_in_mongodb=False  # Video text stored in video_transcripts, not document_chunked
        )
        
        stored_vectors = result['vectors_created']
        
        logging.info(f"[{transcript_id}] ✅ Video Milvus insertion completed: {stored_vectors} vectors")
        return {"vectors_created": stored_vectors}
    except Exception as e:
        error_str = str(e)
        logging.error(f"[{transcript_id}] ❌ Video Milvus insertion failed: {error_str}")
        
        # Re-raise credit errors so they propagate up properly
        if "insufficient_credits" in error_str.lower() or "negative balance" in error_str.lower():
            logging.info("💰 [VIDEO_UPLOAD] Re-raising credit error")
        
        raise e

async def create_video_mongodb_task(transcript_id: str, final_topic: str, extracted_text: str, 
                                   user_id: str, event_epoch: int, utc_iso: str, folder_id: str, 
                                   video_url: str, original_filename: str, stored_vectors: int,
                                   is_enterprise: bool = False, entity_id: str = None) -> Dict[str, Any]:
    """Reusable MongoDB storage task for video transcripts with improved error handling"""
    try:
        logging.info(f"[{transcript_id}] 🚀 Starting parallel video MongoDB storage...")
        
        # Parse datetime object from ISO string
        dt_obj = dtp.parse(utc_iso).astimezone(pytz.UTC)
        
        # Store in MongoDB
        collection = get_mongo_collection()
        doc = {
            "_id": transcript_id,
            "user_id": user_id,
            "video_url": video_url,
            "original_filename": original_filename,
            "topic": final_topic,
            "status": "completed",
            "created_at": datetime.now(tz=pytz.UTC),
            "utc_date": dt_obj,
            "full_transcription": extracted_text,
            "error_message": None,
            "total_chunks": stored_vectors,
            "folder_id": folder_id,
            "is_enterprise": is_enterprise,
            "entity_id": entity_id
        }
        
        # ✅ IMPROVED ERROR HANDLING: Insert with validation
        try:
            insert_result = await collection.insert_one(doc)
            
            # Validate insertion succeeded
            if not insert_result.inserted_id:
                raise Exception("MongoDB insert returned no inserted_id")
            
            # Verify document exists
            verify_doc = await collection.find_one({"_id": transcript_id})
            if not verify_doc:
                raise Exception(f"Document {transcript_id} not found after insert")
            
            logging.info(f"[{transcript_id}] ✅ MongoDB document inserted and verified: {insert_result.inserted_id}")
            
        except Exception as insert_error:
            logging.error(f"[{transcript_id}] ❌ MongoDB insert failed: {insert_error}", exc_info=True)
            logging.error(f"[{transcript_id}] 📋 Failed document data: user_id={user_id}, folder_id={folder_id}, is_enterprise={is_enterprise}")
            raise Exception(f"Video MongoDB storage failed: {insert_error}") from insert_error
        
        logging.info(f"[{transcript_id}] ✅ Video MongoDB storage completed successfully")
        return {"status": "stored", "document_id": transcript_id}
    except Exception as e:
        logging.error(f"[{transcript_id}] ❌ Video MongoDB storage failed: {e}", exc_info=True)
        raise

# async def create_video_entity_extraction_task(transcript_id: str, final_topic: str, extracted_text: str, 
#                                        user_id: str, folder_id: str) -> Dict[str, Any]:
#     """Reusable entity extraction processing task for video transcripts"""
#     try:
#         logging.info(f"[{transcript_id}] 🚀 Starting parallel video entity extraction processing...")
        
#         # Use Dgraph for entity extraction - no fallback, fail early if disabled
#         use_dgraph = os.getenv('DGRAPH_ENTITY_EXTRACTION_ENABLED', 'true').lower() == 'true'
        
#         if not use_dgraph:
#             error_msg = "Dgraph entity extraction is disabled. Enable DGRAPH_ENTITY_EXTRACTION_ENABLED=true"
#             logging.error(f"[{transcript_id}] ❌ {error_msg}")
#             return {"status": "failed", "error": error_msg}
        
#         if extracted_text.strip():
#             # Check if entity extraction already happened for this video transcript
#             redis_client = get_redis_client()
#             process_cache_key = f"entity_processed_{transcript_id}"
#             if redis_client and redis_client.get(process_cache_key):
#                 logging.info(f"[{transcript_id}] ✅ Entity extraction already completed - skipping")
#                 return {"status": "cached"}
#             else:
#                 # DGraph entity extraction removed - skipping knowledge graph creation
#                 logging.info(f"[{transcript_id}] ⚠️ DGraph entity extraction removed - no knowledge graph created")
#                 result = {"status": "skipped", "reason": "dgraph_removed"}
                
#                 # Mark as processed to prevent double execution
#                 if redis_client:
#                     redis_client.setex(process_cache_key, 3600, "completed")  # Cache for 1 hour
                
#                 return result
#         else:
#             logging.info(f"[{transcript_id}] ⚠️ Video entity extraction skipped (no text)")
#             return {"status": "skipped"}
#     except Exception as e:
#         logging.error(f"[{transcript_id}] ❌ Video entity extraction failed: {e}")
#         # Don't fail the entire upload if entity extraction fails
#         return {"status": "failed", "error": str(e)}


# ============= END REUSABLE PARALLEL TASK FUNCTIONS =============

# --- API Endpoints ---
router = APIRouter()

# ═══════════════════════ Video Upload Progress Tracking ═══════════════════════

def update_video_progress(video_id: str, stage: str, progress: int, metadata: dict = None):
    """Update progress for video upload UI tracking - Enhanced with Redis distributed cache"""
    
    # Map stage to progress status
    progress_status = ProgressStatus.PROCESSING
    if stage == "error":
        progress_status = ProgressStatus.ERROR
    elif stage == "complete" and progress >= 100:
        progress_status = ProgressStatus.COMPLETED
    elif progress == 0 and stage in ["starting", "initializing"]:
        progress_status = ProgressStatus.PENDING
    
    # Update Redis cache (distributed across instances) using the existing document progress system
    # Video uploads use the same progress infrastructure as documents
    redis_update_video_progress(video_id, stage, progress, progress_status, metadata=metadata)
    
    # Log progress for debugging - but only for major milestones to reduce spam
    should_log = (
        progress % 10 == 0 or  # Every 10%
        progress in [5, 15, 25, 35, 45, 55, 65, 75, 85, 95] or  # Key milestones
        progress >= 100  # Completion
    )
    
    if should_log:
        # Only append Redis suffix when the distributed progress manager is enabled
        try:
            pm = get_progress_manager()
            redis_suffix = " (Redis: distributed)" if getattr(pm, "enabled", False) else ""
        except Exception:
            redis_suffix = ""
        logging.info(f"[{video_id}] 🎬 Video Progress: {stage} - {progress}%{redis_suffix}")

def get_video_progress(video_id: str) -> dict:
    """Get current progress for a video upload - Enhanced with Redis distributed cache"""
    
    # Try Redis first (distributed cache)
    redis_progress = redis_get_video_progress(video_id)
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

def clear_video_progress(video_id: str):
    """Clear progress tracking for a video upload - Enhanced with Redis distributed cache"""
    
    # Clear Redis cache
    redis_clear_video_progress(video_id)
    
    # Only append Redis suffix when the distributed progress manager is enabled
    try:
        pm = get_progress_manager()
        redis_suffix = " (Redis: distributed)" if getattr(pm, "enabled", False) else ""
    except Exception:
        redis_suffix = ""
    logging.info(f"[{video_id}] 🗑️ Video progress cleared{redis_suffix}")

# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/upload-video/")
async def upload_video(
    request: Request,
    file: UploadFile = File(...),
    audio_file: Optional[UploadFile] = File(None),  # Separate audio file for cost optimization
    audio_extracted: str = Form("false"),  # Flag to indicate audio was extracted client-side
    topic: str = Form(""),
    event_datetime: str = Form(None),
    duration_seconds: float = Form(None),
    folder_id: str = Form(None),
    is_enterprise: Optional[str] = Form(""),  # Add enterprise parameter
    entity_id: Optional[str] = Form(""),  # Add entity ID parameter
    upload_id: str = Form(None)  # Add upload_id parameter for progress tracking
):
    # Get user_id and email from JWT token
    user_id = get_secure_user_id(request)
    user_email = get_user_email(request)
    if not user_email:
        logging.warning("⚠️ User email not available from request")
        user_email = "unknown@example.com"  # Fallback
    
    logging.info(f"Received request with user_id: {user_id}, topic: {topic}, event_datetime: {event_datetime}, folder_id: {folder_id}, is_enterprise: {is_enterprise}, entity_id: {entity_id}")
    
    # Process enterprise parameters
    is_enterprise_bool = is_enterprise and is_enterprise.lower() == 'true'
    entity_id_str = entity_id if entity_id else None
    
    # Initialize progress tracking IMMEDIATELY to prevent UI polling race condition
    progress_id = upload_id or str(uuid.uuid4())
    
    # Set initial status immediately before any processing to ensure UI can find progress data
    update_video_progress(progress_id, "initializing", 0)
    logging.info(f"[{progress_id}] 🎬 Starting video upload with progress tracking")
    
    # Update to analyzing once file processing begins
    update_video_progress(progress_id, "analyzing", 5)
    
    # Import folder routing logic
    from folder_routing import determine_upload_folder
    
    # Clean up old temporary files to prevent disk space issues
    cleanup_old_temp_files()
    
    # Determine the appropriate folder - video uploads respect selected folder or default to 'general'
    folder_id = determine_upload_folder(
        content_type='video',
        upload_source='upload_video',
        selected_folder=folder_id
    )
    logging.info(f"folder_id determined as '{folder_id}' for video upload")
        
    if not file.content_type or not file.content_type.startswith("video/"):
        update_video_progress(progress_id, "error", 0)
        raise HTTPException(status_code=400, detail="Invalid file type")
    if not user_id:
        update_video_progress(progress_id, "error", 0)
        raise HTTPException(status_code=400, detail="user_id is required")

    event_datetime_str = event_datetime or datetime.now().isoformat()
    video_path = ""
    transcript_id = str(int(datetime.now().timestamp() * 1e6)) + "-" + str(uuid.uuid4())
    error_message = None

    try:
        video_content = await file.read()
        if len(video_content) > MAX_FILE_SIZE:
            update_video_progress(progress_id, "error", 0)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Video file size exceeds the limit of {MAX_FILE_SIZE / 1024 / 1024}MB."
            )
        
        # Validate audio file size if provided (for cost optimization)
        audio_content = None
        if audio_file:
            audio_content = await audio_file.read()
            if len(audio_content) > MAX_AUDIO_SIZE:
                update_video_progress(progress_id, "error", 0)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Audio file size exceeds the limit of {MAX_AUDIO_SIZE / 1024 / 1024}MB."
                )
            logging.info(f"[{progress_id}] 🎵 Received audio file: {len(audio_content) / 1024 / 1024:.2f} MB")
        
        # ========== VIDEO DURATION LIMIT CHECK ==========
        if duration_seconds and duration_seconds > MAX_VIDEO_DURATION_MINUTES * 60:
            duration_minutes = duration_seconds / 60
            logging.warning(f"[{progress_id}] ⚠️ Video exceeds duration limit: {duration_minutes:.1f} minutes (max: {MAX_VIDEO_DURATION_MINUTES} minutes)")
            update_video_progress(progress_id, "error", 0)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Video exceeds maximum duration of {MAX_VIDEO_DURATION_MINUTES} minutes ({MAX_VIDEO_DURATION_MINUTES // 60} hours). Your video is {duration_minutes:.1f} minutes."
            )
        # ========== END DURATION LIMIT CHECK ==========
        
        # ═══════════════════════════════════════════════════════════════════════════════════════
        # 💰 CREDIT PRE-CHECK: Verify user has sufficient credits before video processing
        # ═══════════════════════════════════════════════════════════════════════════════════════
        
        logging.info("💰 Starting credit pre-check for video upload and transcription...")
        
        # Calculate video file size in MB
        video_size_bytes = len(video_content)
        video_size_mb = video_size_bytes / (1024 * 1024)
        
        # Simple positive balance check - no pre-estimation of cost
        try:
            credit_check_result = check_user_credits(user_id, 0)
            
            if not credit_check_result['success'] or not credit_check_result.get('sufficient', False):
                # Insufficient credits - return 402 Payment Required
                balance = credit_check_result.get('balance', 0)
                logging.error(f"❌ Negative balance for user {user_id}: {balance:.2f} credits")
                
                update_video_progress(progress_id, "error", 0)
                
                raise HTTPException(
                    status_code=402,
                    detail={
                        "error": "insufficient_credits",
                        "message": f"Upload failed: Your credit balance is too low ({balance:.2f} credits). Please purchase credits to upload video files.",
                        "balance": balance,
                        "required": 0,
                        "video_size_mb": video_size_mb,
                        "transcript_id": progress_id
                    }
                )
            
            logging.info(f"✅ Credit pre-check passed for user {user_id}")
            
        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"❌ Error during credit pre-check: {e}")
            # Continue processing - verified fail-open behavior if system error
        
        # ═══════════════════════════════════════════════════════════════════════════════════════

        container_name = await asyncio.to_thread(get_user_id, user_id)
        # container_name is already sanitized by get_user_id(), use it directly
        logging.info(f"[{progress_id}] 🔧 Using pre-sanitized container name: '{container_name}'")
        
        # Initialize file manager for consistent filename handling
        async_mongo_client = get_async_mongo_client()
        file_manager = get_file_manager(async_mongo_client, MONGODB_DATABASE)
        
        # Use original filename from upload
        original_filename = file.filename or f"video_{int(time.time())}.mp4"
        
        # Check for duplicate filename and cleanup if exists
        logging.info(f"🔍 Checking for duplicate video filename: {original_filename}")
        duplicate_prep = await file_manager.prepare_file_upload(user_id, original_filename, folder_id)
        if duplicate_prep.get("exists"):
            logging.info(f"📁 Duplicate video filename found, cleaned up existing file: {original_filename}")
        
        temp_dir = "temp_videos"
        os.makedirs(temp_dir, exist_ok=True)
        original_video_path = os.path.join(temp_dir, f"{transcript_id}-{original_filename}")

        with open(original_video_path, "wb") as f:
            f.write(video_content)

        video_path = original_video_path
        if file.filename.lower().endswith(".webm"):
            logging.info(f"Fixing .webm metadata for {video_path}")
            fixed_path = await asyncio.to_thread(fix_webm_metadata, video_path)
            if fixed_path != video_path:
                os.remove(video_path)
                video_path = fixed_path

        # Use the original filename (user-provided title) for S3 storage
        video_url = await upload_to_s3(video_path, original_filename, user_id, is_enterprise=is_enterprise_bool, entity_id=entity_id_str, folder_id=folder_id)

        # Stage 1: Extracting (audio extraction and transcription)
        update_video_progress(progress_id, "extracting", 25)
        logging.info(f"[{progress_id}] 🔄 Video Stage 1/5: Extracting - Extracting audio and transcribing")

        # 💰 COST OPTIMIZATION: Use client-extracted audio if provided
        audio_path = None
        audio_extracted_client_side = audio_extracted and audio_extracted.lower() == 'true'
        
        try:
            if audio_file and audio_extracted_client_side:
                # Use the audio file provided by client (cost optimized)
                logging.info(f"[{progress_id}] 🎵 Using client-extracted audio (cost optimized - no video processing)")
                
                # Audio content already read during validation
                if not audio_content:
                    audio_content = await audio_file.read()
                
                audio_filename = f"{Path(video_path).stem}_client_audio.mp3"
                audio_path = os.path.join(Path(video_path).parent, audio_filename)
                
                with open(audio_path, "wb") as f:
                    f.write(audio_content)
                
                logging.info(f"[{progress_id}] ✅ Client-extracted audio saved: {audio_path} ({len(audio_content)} bytes)")
                logging.info(f"[{progress_id}] 💰 Cost savings: Skipped MoviePy extraction and video processing")
            else:
                # Fallback: Extract audio from video (legacy method)
                logging.info(f"[{progress_id}] ⚠️ No client audio provided, extracting from video (legacy method)")
                audio_filename = f"{Path(video_path).stem}.mp3"
                audio_path = os.path.join(Path(video_path).parent, audio_filename)
                
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, extract_audio_from_video, video_path, audio_path, duration_seconds)
                logging.info(f"[{progress_id}] ✅ Audio extracted from video: {audio_path}")
            
            # Step 2: Transcribe audio for topic generation
            logging.info(f"[{progress_id}] Step 2: Transcribing audio for topic generation...")
            loop = asyncio.get_running_loop()
            transcribed_text = await loop.run_in_executor(None, transcribe_audio, audio_path, user_id, user_email)
            if not transcribed_text or not transcribed_text.strip():
                update_video_progress(progress_id, "error", 0)
                raise HTTPException(status_code=500, detail="Transcription resulted in empty text")
            
        except Exception as audio_error:
            logging.error(f"[{progress_id}] ❌ Audio processing failed: {audio_error}")
            # Clean up temp files on error
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    logging.info(f"[{progress_id}] 🗑️ Cleaned up audio file after error: {audio_path}")
                except Exception as cleanup_err:
                    logging.warning(f"[{progress_id}] Failed to cleanup audio file: {cleanup_err}")
            raise audio_error

        # Stage 2: Processing (topic generation and text processing)
        update_video_progress(progress_id, "processing", 50)
        logging.info(f"[{progress_id}] 🔄 Video Stage 2/5: Processing - Determining topic and cleaning text")

        # Step 3: Use user-provided topic or generate from transcribed text as fallback
        if topic and topic.strip():
            # Use user-provided topic
            final_topic = topic.strip()
            logging.info(f"Using user-provided topic for video: {final_topic}")
        else:
            # Fallback: Generate topic from transcribed text using AI only if no topic provided
            try:
                generated_topic = generate_topic_from_text(transcribed_text, user_id=user_id, user_email=user_email)  # Pass user_id for token tracking
                final_topic = generated_topic if generated_topic else "Video Recording"
                logging.info(f"Auto-generated topic for video (no user topic provided): {final_topic}")
            except Exception as e:
                logging.error(f"Failed to generate topic from text: {e}")
                final_topic = "Video Recording"  # Final fallback topic

        # ============= PARALLEL PROCESSING FOR VIDEO TRANSCRIPTS =============
        # Stage 3: Embedding (vector embeddings and Milvus storage)
        update_video_progress(progress_id, "embedding", 70)
        logging.info(f"[{progress_id}] 🔄 Video Stage 3/5: Embedding - Creating vectors and storing in Milvus")

        # Parse datetime for all tasks
        dt_obj = dtp.parse(event_datetime_str).astimezone(pytz.UTC)
        
        # Run Milvus insertion, MongoDB storage, and concept mapping in parallel
        parallel_start = time.time()
        
        # Execute all tasks in parallel using reusable functions
        base_tasks = [
            create_video_embedding_task(transcript_id, topic, transcribed_text, user_id, int(dt_obj.timestamp()), dt_obj.isoformat(), folder_id, video_url, is_enterprise_bool, entity_id_str),
            create_video_mongodb_task(transcript_id, topic, transcribed_text, user_id, int(dt_obj.timestamp()), dt_obj.isoformat(), folder_id, video_url, file.filename, 0, is_enterprise_bool, entity_id_str),
        ]

        logging.info(f"[{transcript_id}] 🚀 Starting parallel execution of Milvus and MongoDB tasks...")

        try:
            results = await asyncio.gather(*base_tasks, return_exceptions=True)
            
            # Stage 4: Finalizing (completing all storage operations)
            update_video_progress(progress_id, "finalizing", 90)
            logging.info(f"[{progress_id}] 🔄 Video Stage 4/5: Finalizing - Completing storage operations")
            
            parallel_time = time.time() - parallel_start
            logging.info(f"[{transcript_id}] ⚡ Parallel processing completed in {parallel_time:.3f}s")
            
            # Handle results and any exceptions
            milvus_result = results[0]
            mongodb_result = results[1]
            # Note: concept_result removed since create_video_entity_extraction_task is disabled

            if isinstance(milvus_result, Exception):
                logging.error(f"[{transcript_id}] ❌ Milvus task failed: {milvus_result}")
                update_video_progress(progress_id, "error", 0)
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
                    
                    async_mongo_client = get_async_mongo_client()
                    enhanced_service = EnhancedChunkedDocumentService(async_mongo_client, MONGODB_DATABASE)
                    
                    # Use existing delete_from_milvus method
                    rollback_success = await enhanced_service.delete_from_milvus(transcript_id, user_id, is_enterprise_bool, entity_id_str)
                    if rollback_success:
                        logging.info(f"[{transcript_id}] ✅ Rollback complete: Deleted Milvus chunks for {transcript_id}")
                    else:
                        logging.warning(f"[{transcript_id}] ⚠️ Rollback completed with warnings (check logs above)")
                except Exception as rollback_error:
                    logging.error(f"[{transcript_id}] ❌ Rollback failed: {rollback_error}", exc_info=True)
                    logging.error(f"[{transcript_id}] ⚠️ CRITICAL: Orphaned Milvus chunks may exist for document_id={transcript_id}")
                
                update_video_progress(progress_id, "error", 0)
                raise mongodb_result
            else:
                logging.info(f"[{transcript_id}] ✅ MongoDB: Video transcript stored successfully")
        
        except Exception as e:
            logging.error(f"[{transcript_id}] ❌ Parallel processing failed: {e}")
            update_video_progress(progress_id, "error", 0)
            raise e

        # Update MongoDB document with correct total_chunks from Milvus result
        try:
            collection = get_mongo_collection()
            await collection.update_one(
                {"_id": transcript_id},
                {"$set": {"total_chunks": stored_vectors}}
            )
        except Exception as e:
            logging.warning(f"[{transcript_id}] Failed to update total_chunks in MongoDB: {e}")
        
        process_result = {
            "full_transcription": transcribed_text,
            "total_chunks": stored_vectors,
            "utc_date": dt_obj
        }
        # ============= END PARALLEL PROCESSING =============
        
        
        # Clean up temp files after successful processing
        temp_files_to_clean = []
        if audio_path and os.path.exists(audio_path):
            temp_files_to_clean.append(("audio", audio_path))
        if video_path and os.path.exists(video_path):
            temp_files_to_clean.append(("video", video_path))
        
        for file_type, file_path in temp_files_to_clean:
            try:
                os.remove(file_path)
                logging.info(f"[{transcript_id}] 🗑️ Cleaned up temporary {file_type} file: {file_path}")
            except Exception as cleanup_error:
                logging.warning(f"[{transcript_id}] Failed to clean up {file_type} file {file_path}: {cleanup_error}")
        
        logging.info(f"Successfully completed processing and stored transcript_id: {transcript_id}")

        # Stage 5: Complete
        update_video_progress(progress_id, "complete", 100)
        logging.info(f"[{progress_id}] ✅ Video Stage 5/5: Complete - Video upload and processing finished successfully")

        # ============= FILES COLLECTION INTEGRATION =============
        # Register video file metadata in central files collection
        try:
            from services.files_service import FilesService
            
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
            file_extension = Path(file.filename).suffix.lstrip('.').lower() if file.filename else "mp4"
            
            # Get file size
            file_size_bytes = len(video_content)
            
            # Get db_size_bytes from MongoDB document
            video_coll = async_mongo_client[MONGODB_DATABASE]["video_transcripts"]
            video_doc = await video_coll.find_one({"_id": transcript_id})
            db_size_bytes = video_doc.get("db_size_bytes", 0) if video_doc else 0
            
            # Build file metadata with _id set to video_transcripts_id
            file_metadata = {
                "_id": transcript_id,  # Use transcript_id as primary key
                "user_id": user_id,
                "filename": original_filename,
                "file_extension": file_extension,
                "file_size_bytes": file_size_bytes,
                "db_size_bytes": db_size_bytes,  # Database storage size tracking
                "content_type": file.content_type or f"video/{file_extension}",
                "file_type_category": "video",  # audio|document|video|image|note
                "topic_or_filename": final_topic,
                "upload_datetime": datetime.utcnow(),
                "last_modified_datetime": datetime.utcnow(),
                "folder_id": folder_id,
                "is_enterprise": is_enterprise_bool,
                "entity_id": entity_id_str,
                "duration_seconds": int(duration_seconds) if duration_seconds else 0,
                "s3_url": video_url,
                "storage_location": "s3",
                "milvus_primary_keys": milvus_primary_keys,
                "mongodb_collections": {
                    "document_chunked_ids": None,
                    "milvus_chunks_id": milvus_chunks_id,  # Actual _id from milvus_chunks
                    "transcripts_id": None,
                    "video_transcripts_id": transcript_id  # This IS the _id
                }
            }
            
            # Register file in files collection
            file_id = await files_service.register_file(file_metadata)
            logging.info(f"[{transcript_id}] ✅ Video file registered in files collection: {file_id}")
            
        except Exception as files_error:
            # Don't fail video upload if files registration fails - just log the error
            logging.error(f"[{transcript_id}] ⚠️ Failed to register video file in files collection: {files_error}")
            logging.exception(files_error)
        # ============= END FILES COLLECTION INTEGRATION =============

        return {
            "message": "Video processed and embeddings stored successfully.",
            "video_url": video_url,
            "transcript_id": transcript_id,
            "total_chunks_stored": process_result["total_chunks"],
            "user_id": user_id,
            "container_name": container_name,
            "full_transcription": transcribed_text,
            "topic": final_topic,
            "folder_id": folder_id
        }
    except HTTPException as http_exc:
        # Mark progress as error and clear after delay
        update_video_progress(progress_id, "error", 0)
        logging.error(f"[{progress_id}] ❌ Video upload failed with HTTP error: {http_exc.detail}")
        
        # Clean up temporary files in case of error
        cleanup_files = []
        if video_path and os.path.exists(video_path):
            cleanup_files.append(("video", video_path))
        if 'audio_path' in locals() and audio_path and os.path.exists(audio_path):
            cleanup_files.append(("audio", audio_path))
        
        for file_type, file_path in cleanup_files:
            try:
                os.remove(file_path)
                logging.info(f"[{progress_id}] 🗑️ Cleaned up temporary {file_type} file: {file_path}")
            except Exception as cleanup_error:
                logging.warning(f"[{progress_id}] Failed to clean up {file_type} file {file_path}: {cleanup_error}")
        
        raise
    except Exception as e:
        # Mark progress as error and clear after delay
        update_video_progress(progress_id, "error", 0)
        logging.error(f"[{progress_id}] ❌ Video upload failed with unexpected error")
        logging.error(f"An error occurred during the video upload process: {e}")
        
        # Clean up temporary files in case of error
        cleanup_files = []
        if video_path and os.path.exists(video_path):
            cleanup_files.append(("video", video_path))
        if 'audio_path' in locals() and audio_path and os.path.exists(audio_path):
            cleanup_files.append(("audio", audio_path))
        
        for file_type, file_path in cleanup_files:
            try:
                os.remove(file_path)
                logging.info(f"[{progress_id}] 🗑️ Cleaned up temporary {file_type} file: {file_path}")
            except Exception as cleanup_error:
                logging.warning(f"[{progress_id}] Failed to clean up {file_type} file {file_path}: {cleanup_error}")
        
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


@router.get("/transcripts/device")
async def get_transcripts_by_device(request: Request):
    """Get all video transcripts for the authenticated user with proper full_transcription field"""
    user_id = get_secure_user_id(request)
    collection = get_mongo_collection()
    cursor = collection.find({"user_id": user_id})
    transcripts = await cursor.to_list(length=100)
    if not transcripts:
        raise HTTPException(status_code=404, detail="No video transcripts found for this device.")
    
    # Process each transcript to ensure proper field mapping with explicit ID fields
    # ⚡ PERFORMANCE: Remove transcript content from list view - only load on click
    processed_transcripts = []
    for doc in transcripts:
        transcript_dict = {
            "_id": str(doc["_id"]),  # Convert ObjectId to string for JSON serialization
            "id": str(doc["_id"]),   # Add 'id' field for UI compatibility
            "transcript_id": str(doc["_id"]),  # Add 'transcript_id' field for UI compatibility
            "user_id": doc.get("user_id", ""),
            "video_url": doc.get("video_url", ""),
            "original_filename": doc.get("original_filename", ""),
            # PERFORMANCE: Remove full_transcription from list - content loaded on demand
            "topic": doc.get("topic", ""),
            "status": doc.get("status", ""),
            "created_at": doc.get("created_at"),
            "utc_date": doc.get("utc_date"),
            "error_message": doc.get("error_message"),
            "total_chunks": doc.get("total_chunks", 0)
        }
        processed_transcripts.append(transcript_dict)
    
    return processed_transcripts

@router.get("/transcripts/{transcript_id}")
async def get_transcript_by_id(transcript_id: str, request: Request):
    """Get video transcript by ID with proper full_transcription field"""
    import time
    # SECURITY: Authenticate user from JWT token
    from citra_auth import get_secure_user_id
    user_id_auth = get_secure_user_id(request)

    start_time = time.time()
    
    logging.info(f"🎥 [GET_VIDEO_TRANSCRIPT] Searching for video transcript ID: {transcript_id}")
    collection = get_mongo_collection()
    
    # ⚡ PERFORMANCE OPTIMIZATION: Use projection to fetch only needed fields initially
    # SECURITY: Filter by user_id to prevent cross-user data access
    query_start = time.time()
    document = await collection.find_one(
        {"_id": transcript_id, "user_id": user_id_auth},
        projection={
            "_id": 1,
            "user_id": 1,
            "video_url": 1,
            "original_filename": 1,
            "topic": 1,
            "status": 1,
            "created_at": 1,
            "utc_date": 1,
            "error_message": 1,
            "total_chunks": 1,
            "full_transcription": 1  # Still include it but MongoDB can optimize retrieval
        }
    )
    query_time = time.time() - query_start
    
    if document:
        total_time = time.time() - start_time
        logging.info(f"🎥 [GET_VIDEO_TRANSCRIPT] ✅ Found video transcript: {transcript_id}, topic: {document.get('topic', 'No topic')} | Query: {query_time:.2f}s | Total: {total_time:.2f}s")
        
        # Ensure the response includes the full_transcription field for video transcripts with all ID formats
        return {
            "_id": str(document["_id"]),  # Convert ObjectId to string for JSON serialization
            "id": str(document["_id"]),   # Add 'id' field for UI compatibility
            "transcript_id": str(document["_id"]),  # Add 'transcript_id' field for UI compatibility
            "user_id": document.get("user_id", ""),
            "video_url": document.get("video_url", ""),
            "original_filename": document.get("original_filename", ""),
            "full_transcription": document.get("full_transcription", ""),  # This is the key field for video content
            "topic": document.get("topic", ""),
            "status": document.get("status", ""),
            "created_at": document.get("created_at"),
            "utc_date": document.get("utc_date"),
            "error_message": document.get("error_message"),
            "total_chunks": document.get("total_chunks", 0)
        }
    
    logging.warning(f"🎥 [GET_VIDEO_TRANSCRIPT] Video transcript not found: {transcript_id}")
    raise HTTPException(status_code=404, detail="Video transcription not found.")

# ═══════════════════════ Video Upload Progress Endpoint ═══════════════════════

@router.get("/video/progress/{video_id}")
async def get_video_progress_endpoint(video_id: str):
    """
    Get real-time progress for video processing (with Redis distributed cache)
    Used by UI to display upload progress and analysis results across multiple service instances
    """
    try:
        progress_data = get_video_progress(video_id)
        
        if not progress_data:
            # Progress data not available - could be Redis temporarily down or progress not set yet
            # Instead of immediately returning "redis_down", try to determine if video processing might be ongoing
            try:
                from citra_mongo import get_mongo_client
                client = get_mongo_client()
                from citra_mongo import MONGODB_DATABASE as db_name
                db = client[db_name]
                
                # Check if the video was successfully processed and stored
                video_record = db.video_transcriptions.find_one({"_id": video_id})
                if video_record and video_record.get("status") == "completed":
                    # Video processing completed successfully but Redis tracking lost
                    return {
                        "video_id": video_id,
                        "status": "completed",
                        "message": "Video processed and stored successfully",
                        "progress": 100,
                        "stage": "complete",
                        "source": "database_fallback"
                    }
                elif video_record and video_record.get("status") == "error":
                    # Video processing failed
                    return {
                        "video_id": video_id,
                        "status": "error",
                        "message": video_record.get("error_message", "Video processing failed"),
                        "progress": 0,
                        "stage": "error",
                        "source": "database_fallback"
                    }
                elif video_record:
                    # Video record exists but status is not completed - might still be processing
                    return {
                        "video_id": video_id,
                        "status": "processing",
                        "message": "Video processing in progress",
                        "progress": 50,  # Assume mid-processing
                        "stage": "processing",
                        "source": "database_fallback"
                    }
            except Exception as db_error:
                logging.debug(f"Could not check database for video status: {db_error}")
            
            # Progress tracking unavailable - but video might still be processing
            # Return a status that indicates monitoring is down but processing might continue
            return {
                "video_id": video_id,
                "status": "processing",  # Changed from "redis_down" to "processing"
                "message": "Progress tracking temporarily unavailable - video processing may still be active",
                "progress": 25,  # Assume some progress has been made
                "stage": "processing",
                "source": "monitoring_unavailable"
            }
        
        # Enhanced response with proper status mapping from Redis data
        stage = progress_data.get("stage", "unknown")
        progress = progress_data.get("progress", 0)
        redis_status = progress_data.get("status", "processing")
        
        # Map Redis status to UI-friendly status
        if redis_status == "error" or stage == "error":
            status = "error"
            message = progress_data.get("message", "Video upload failed - please try again")
        elif redis_status == "completed" or (stage == "complete" and progress >= 100):
            status = "completed"
            message = progress_data.get("message", "Video uploaded and processed successfully")
        elif redis_status == "pending" or stage in ["starting", "initializing"]:
            status = "processing"
            message = progress_data.get("message", f"Initializing video processing: {stage}")
        elif redis_status == "processing" or stage in ["analyzing", "extracting", "processing", "embedding", "finalizing"]:
            status = "processing"
            message = progress_data.get("message", f"Processing video: {stage}")
        else:
            status = "processing"
            message = progress_data.get("message", f"Processing video: {stage}")
        
        response = {
            "video_id": video_id,
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
        logging.error(f"Video progress tracking error: {e}")
        return {
            "video_id": video_id,
            "status": "error",
            "message": f"Error retrieving progress: {str(e)}",
            "progress": 0,
            "stage": "error"
        }

@router.get("/")
def read_root():
    return {"message": "Welcome to the Video Processing API"}

app.include_router(router)
