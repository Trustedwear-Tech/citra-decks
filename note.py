from typing import List, Dict, Any, Optional
import uuid
from fastapi import APIRouter, Request, Query, Body, HTTPException, status
from fastapi.responses import JSONResponse
import logging
import json
from citra_auth import get_secure_user_id

import os
import time
import threading
import traceback
import redis
from datetime import datetime
import hashlib
import re
from bson import ObjectId

# Import Milvus client for vector storage
try:
    from config.milvus_config import get_milvus_client, get_collection_name
    MILVUS_AVAILABLE = True
except ImportError as e:
    logging.error(f"Milvus import error: {e}")
    MILVUS_AVAILABLE = False

# Import unified metadata schema for centralized namespace creation
from models.unified_metadata_schema import UnifiedMetadataSchema

# Import MongoDB utilities.
# DB-name selection is REQUIRED config, resolved before the connection try so a
# missing MONGODB_DATABASE crashes loudly at import instead of silently
# defaulting to a hardcoded DB name (cross-environment bleed risk).
from require_env import require_env
MONGODB_DATABASE = require_env("MONGODB_DATABASE")
try:
    from citra_mongo import get_mongo_client
    # Setup MongoDB
    client = get_mongo_client()
    db = client[MONGODB_DATABASE]
    notes_col = db['Notes']
    MONGODB_AVAILABLE = True
except Exception as e:
    logging.error(f"Error while connecting to MongoDB: {str(e)}")
    MONGODB_AVAILABLE = False

# Import utilities (no longer need embed_text - handled by EnhancedChunkedDocumentService)
try:
    from utils import get_user_id
    from services.enhanced_chunked_document_service import EnhancedChunkedDocumentService
    from services.files_service import FilesService
    UTILS_AVAILABLE = True
except ImportError as e:
    logging.error(f"Error importing utilities: {e}")
    UTILS_AVAILABLE = False

# Concept Map Integration - Disabled (module removed)
CONCEPT_MAP_AVAILABLE = False
logging.info("ℹ️ Concept map functionality disabled - module removed")

# Note Safety Manager removed - using direct MongoDB operations

# =============================================================================
# NOTES MONGODB FUNCTIONS
# =============================================================================

def create_note_documents(mongo_docs: List[Dict]) -> int:
    """Create multiple note documents in MongoDB"""
    try:
        if not mongo_docs:
            return 0
        
        insert_result = notes_col.insert_many(mongo_docs)
        inserted_count = len(insert_result.inserted_ids)
        logging.info(f"MongoDB insert completed: {inserted_count} documents")
        return inserted_count
    except Exception as e:
        logging.error(f"Error creating note documents: {str(e)}")
        raise

def get_notes_list(user_id: str, limit: int = 50, skip: int = 0, folder_id: str = None) -> List[Dict]:
    """Get list of notes for a device with pagination, optionally filtered by folder_id"""
    try:
        query = {'user_id': user_id}
        
        # Add folder_id filter if provided
        if folder_id:
            query['folder_id'] = folder_id
            
        logging.info(f"MongoDB query: {query}")
        
        cursor = notes_col.find(query).sort('created_at', -1).skip(skip).limit(limit)
        notes = []
        
        for doc in cursor:
            doc['_id'] = str(doc['_id'])
            doc['created_at'] = doc['created_at'].isoformat() if isinstance(doc['created_at'], datetime) else doc['created_at']
            doc['updated_at'] = doc['updated_at'].isoformat() if isinstance(doc['updated_at'], datetime) else doc['updated_at']
            
            # Truncate text field to first 50 characters and add ellipsis for list view
            if 'text' in doc and doc['text']:
                doc['text'] = doc['text'][:50] + "➡️" if len(doc['text']) > 50 else doc['text']
            
            notes.append(doc)
        
        logging.info(f"Retrieved {len(notes)} notes from MongoDB")
        return notes
    except Exception as e:
        logging.error(f"Error getting notes list: {str(e)}")
        raise

def get_notes_count(user_id: str, folder_id: str = None) -> int:
    """Get total count of notes for a device, optionally filtered by folder_id"""
    try:
        query = {'user_id': user_id}
        
        # Add folder_id filter if provided
        if folder_id:
            query['folder_id'] = folder_id
            
        total_count = notes_col.count_documents(query)
        logging.info(f"Total documents matching query: {total_count}")
        return total_count
    except Exception as e:
        logging.error(f"Error getting notes count: {str(e)}")
        raise

def get_note_metadata_by_note_id(note_id: str) -> Optional[Dict]:
    """Get note metadata by note_id"""
    try:
        query = {'note_id': note_id}
        doc = notes_col.find_one(query)
        
        if doc:
            doc['_id'] = str(doc['_id'])
            doc['created_at'] = doc['created_at'].isoformat() if isinstance(doc['created_at'], datetime) else doc['created_at']
            doc['updated_at'] = doc['updated_at'].isoformat() if isinstance(doc['updated_at'], datetime) else doc['updated_at']
        
        return doc
    except Exception as e:
        logging.error(f"Error getting note metadata by note_id: {str(e)}")
        raise

def get_note_metadata_by_mongodb_id(mongodb_id: str) -> Optional[Dict]:
    """Get note metadata by MongoDB _id"""
    try:
        query = {'_id': str(mongodb_id)}
        doc = notes_col.find_one(query)
        
        if doc:
            doc['_id'] = str(doc['_id'])
            doc['created_at'] = doc['created_at'].isoformat() if isinstance(doc['created_at'], datetime) else doc['created_at']
            doc['updated_at'] = doc['updated_at'].isoformat() if isinstance(doc['updated_at'], datetime) else doc['updated_at']
        
        return doc
    except Exception as e:
        logging.error(f"Error getting note metadata by mongodb_id: {str(e)}")
        raise

def get_notes_stats(user_id: Optional[str] = None) -> int:
    """Get notes statistics from MongoDB"""
    try:
        if user_id:
            mongodb_count = notes_col.count_documents({'user_id': user_id})
        else:
            mongodb_count = notes_col.count_documents({})
        return mongodb_count
    except Exception as e:
        logging.error(f"Error getting notes stats: {str(e)}")
        raise

def get_notes_to_update(note_id: Optional[str] = None, mongodb_id: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict]:
    """Get notes to update by note_id or mongodb_id - filtered by user_id for security"""
    try:
        if mongodb_id:
            query = {'_id': str(mongodb_id)}
        elif note_id:
            query = {'note_id': note_id}
        else:
            return []
        
        # SECURITY: Always filter by user_id to prevent cross-user access
        if user_id:
            query['user_id'] = user_id
        
        docs = list(notes_col.find(query))
        return docs
    except Exception as e:
        logging.error(f"Error getting notes to update: {str(e)}")
        raise

def update_note_document(doc_id: str, new_text: Optional[str] = None, new_metadata: Optional[Dict] = None) -> bool:
    """Update a single note document"""
    try:
        update_data = {'updated_at': datetime.utcnow().isoformat()}
        
        if new_text:
            update_data['text'] = new_text
        
        if new_metadata:
            # Get existing metadata and update it
            existing_doc = notes_col.find_one({'_id': doc_id})
            if existing_doc:
                updated_metadata = existing_doc.get('metadata', {})
                updated_metadata.update(new_metadata)
                updated_metadata['updated_at'] = datetime.utcnow().isoformat()
                update_data['metadata'] = updated_metadata
        
        result = notes_col.update_one({'_id': doc_id}, {'$set': update_data})
        return result.modified_count > 0
    except Exception as e:
        logging.error(f"Error updating note document: {str(e)}")
        raise

def get_notes_to_delete(note_ids: Optional[List[str]] = None, mongodb_ids: Optional[List[str]] = None, user_id: Optional[str] = None) -> List[Dict]:
    """Get notes to delete by note_ids or mongodb_ids - filtered by user_id for security"""
    try:
        if mongodb_ids:
            object_ids = [str(id_str) for id_str in mongodb_ids]
            mongo_query = {'_id': {'$in': object_ids}}
        elif note_ids:
            mongo_query = {'note_id': {'$in': note_ids}}
        else:
            return []

        # SECURITY: Always filter by user_id to prevent cross-user access
        if user_id:
            mongo_query['user_id'] = user_id
        
        docs_to_delete = list(notes_col.find(mongo_query))
        return docs_to_delete
    except Exception as e:
        logging.error(f"Error getting notes to delete: {str(e)}")
        raise

def delete_notes_by_query(note_ids: Optional[List[str]] = None, mongodb_ids: Optional[List[str]] = None, user_id: Optional[str] = None) -> int:
    """Delete notes by note_ids or mongodb_ids - filtered by user_id for security"""
    try:
        if mongodb_ids:
            object_ids = [str(id_str) for id_str in mongodb_ids]
            mongo_query = {'_id': {'$in': object_ids}}
        elif note_ids:
            mongo_query = {'note_id': {'$in': note_ids}}
        else:
            return 0
        
        # SECURITY: Always filter by user_id to prevent cross-user access
        if user_id:
            mongo_query['user_id'] = user_id
        
        mongo_result = notes_col.delete_many(mongo_query)
        return mongo_result.deleted_count
    except Exception as e:
        logging.error(f"Error deleting notes by query: {str(e)}")
        raise

def delete_all_notes_for_device(user_id: str) -> int:
    """Delete all notes for a specific device"""
    try:
        # Check if any documents exist for this device
        existing_count = notes_col.count_documents({'user_id': user_id})
        logging.info(f"Found {existing_count} documents in MongoDB for device {user_id}")
        
        if existing_count > 0:
            mongo_result = notes_col.delete_many({'user_id': user_id})
            deleted_count = mongo_result.deleted_count
            logging.info(f"Deleted {deleted_count} documents from MongoDB")
            return deleted_count
        else:
            logging.info(f"No documents found in MongoDB for device {user_id}")
            return 0
    except Exception as e:
        logging.error(f"Error deleting all notes for device: {str(e)}")
        raise

# =============================================================================
# END NOTES MONGODB FUNCTIONS
# =============================================================================\n\n# Assume these handler functions exist and are imported:
#   handle_create_note
#   handle_search_notes
#   handle_list_notes
#   handle_get_note_metadata
#   handle_get_note_stats
#   handle_health_check
#   handle_update_note
#   handle_delete_notes
#   handle_delete_all_notes

# Also assume these booleans are defined elsewhere and imported:
#   DEPENDENCIES_AVAILABLE
#   MONGODB_AVAILABLE

router = APIRouter()

@router.get("/note")
@router.post("/note")
@router.put("/note")
@router.delete("/note")
@router.options("/note")
async def note(
    request: Request,
    operation: Optional[str] = Query(
        None,
        description=(
            "One of: create, search, list, get_metadata, stats, health, "
            "update, delete, delete_all"
        ),
    ),
    body: Optional[dict] = Body(None),
):
    """
    Endpoint for Milvus/Zilliz Cloud note database CRUD operations with MongoDB metadata storage.

    Query Parameters:
    - operation: required, one of:
        * POST: "create" or "search"
        * GET: "list", "get_metadata", "stats", or "health"
        * PUT: "update"
        * DELETE: "delete" or "delete_all"

    JSON Body is passed through to the lower‐level handlers as needed.
    """
    # Common CORS headers (if not handled by middleware)
    headers = {
        "Content-Type": "application/json",
        # "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }

    # 1. Handle preflight (OPTIONS)
    if request.method == "OPTIONS":
        return JSONResponse(status_code=status.HTTP_200_OK, content="", headers=headers)

    # 2. Check dependencies
    if not MILVUS_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Milvus/Zilliz Cloud connection not available. Please check configuration.",
        )
    if not MONGODB_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MongoDB connection not available. Please check MongoDB configuration.",
        )

    try:
        method = request.method.upper()
        logging.info(f"Processing {method} request with operation: {operation}")

        # 3. Validate operation parameter
        if not operation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Operation parameter is required. "
                    "Use: create, search, list, get_metadata, stats, health, "
                    "update, delete, or delete_all"
                ),
            )

        # 4. Route to appropriate handler
        if method == "POST":
            if operation == "create":
                return await handle_create_note(request, headers)
            elif operation == "search":
                return await handle_search_notes(request, headers)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid operation for POST. Use 'create' or 'search'.",
                )

        elif method == "GET":
            if operation == "list":
                return await handle_list_notes(request, headers)
            elif operation == "get_metadata":
                return await handle_get_note_metadata(request, headers)
            elif operation == "stats":
                return await handle_get_note_stats(request, headers)
            elif operation == "health":
                return await handle_health_check(request, headers)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid operation for GET. Use 'list', 'get_metadata', 'stats', or 'health'.",
                )

        elif method == "PUT":
            if operation == "update":
                return await handle_update_note(request, headers)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid operation for PUT. Use 'update'.",
                )

        elif method == "DELETE":
            if operation == "delete":
                return await handle_delete_notes(request, headers)
            elif operation == "delete_all":
                return await handle_delete_all_notes(request, headers)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid operation for DELETE. Use 'delete' or 'delete_all'.",
                )

        else:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail=f"Method {method} not allowed.",
            )

    except HTTPException:
        # FastAPI will handle re‐raising HTTPExceptions
        raise
    except Exception as e:
        logging.error(f"Error in note: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )

async def handle_health_check(request: Request, headers: dict) -> JSONResponse:
    """Handle health check endpoint"""
    try:
        # Check environment variables
        required_env_vars = [
            'ZILLIZ_CLOUD_URI',
            'ZILLIZ_CLOUD_API_KEY',
            'MILVUS_COLLECTION',
            'llm_API_KEY',
            'MONGODB_CONN_STRING'
        ]
        
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        
        if missing_vars:
            return JSONResponse(
                content={
                    "status": "unhealthy",
                    "missing_environment_variables": missing_vars,
                    "message": "Required environment variables are missing"
                },
                status_code=500,
                headers=headers
            )

        # Return healthy status
        health_status = {
            "status": "healthy",
            "function": "note_crud",
            "vector_store": "milvus_zilliz_cloud",
            "hybrid_search": "enabled",
            "timestamp": datetime.utcnow().isoformat()
        }

        return JSONResponse(
            content=health_status,
            status_code=200,
            headers=headers
        )

    except Exception as e:
        return JSONResponse(
            content={
                "status": "unhealthy",
                "error": str(e)
            },
            status_code=500,
            headers=headers
        )

def initialize_milvus():
    """Get Milvus client from centralized singleton"""
    return get_milvus_client()

def get_cached_milvus_client():
    """Get cached Milvus client from centralized singleton"""
    return get_milvus_client()

def get_redis_client():
    """Get Redis client with default configuration"""
    try:
        import redis
        conn_kwargs = dict(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=int(os.getenv('REDIS_DB', 0)),
            password=os.getenv('REDIS_PASSWORD'),
            username=os.getenv('REDIS_USERNAME'),
            decode_responses=True,
        )
        if os.getenv('REDIS_SSL', 'false').lower() == 'true':
            conn_kwargs['ssl'] = True
            conn_kwargs['ssl_cert_reqs'] = None
        return redis.Redis(**conn_kwargs)
    except Exception as e:
        logging.warning(f"Redis client initialization failed: {e}")
        return None

async def handle_create_note(request: Request, headers: dict) -> JSONResponse:
    """
    Handle note creation operations with a shared note_id and parallel Milvus/MongoDB storage.
    All embeddings are created via EnhancedChunkedDocumentService which generates hybrid vectors
    (dense embeddings + sparse BM25 vectors) and stores them in Milvus/Zilliz Cloud.
    """
    try:
        logging.info("Processing create note request")

        # Parse request body
        req_body = await request.json()
        if not req_body:
            return JSONResponse(
                content={"error": "Request body is required"},
                status_code=400,
                headers=headers
            )

        # Validate required fields
        user_id = get_secure_user_id(request)
        text = req_body.get('text')

        if not user_id:
            return JSONResponse(
                content={"error": "user_id is required"},
                status_code=400,
                headers=headers
            )
        if not text:
            return JSONResponse(
                content={"error": "text is required"},
                status_code=400,
                headers=headers
            )

        # Optional fields
        title = req_body.get('title', 'Note')
        metadata = req_body.get('metadata', {})
        chunk_size = req_body.get('chunk_size', int(os.getenv('CHUNK_SIZE_LIMIT', '1000')))
        overlap = req_body.get('overlap', 200)
        folder_id = req_body.get('folder_id')  # Get folder_id from request
        
        # Enterprise and entity fields for files collection
        is_enterprise = req_body.get('is_enterprise', False)
        entity_id = req_body.get('entity_id', None)
        
        # Apply folder routing logic (respects selected folder or defaults to 'general')
        from folder_routing import determine_upload_folder
        folder_id = determine_upload_folder(
            content_type='note',
            upload_source='note_creation',
            selected_folder=folder_id
        )
        logging.info(f"Note will be saved to folder: {folder_id}")

        logging.info(f"Creating note for user_id: {user_id}, text length: {len(text)}")

        # Initialize Milvus service
        milvus_client = initialize_milvus()

        # 1) Create a single note_id that will be shared by both Milvus metadata and MongoDB documents
        base_note_id = str(int(datetime.now().timestamp() * 1e6)) + "-" + str(uuid.uuid4())
        logging.info(f"Generated base note_id: {base_note_id}")

        # 2) Use enhanced chunked document service for uniform chunking and embedding
        from services.enhanced_chunked_document_service import EnhancedChunkedDocumentService
        from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
        
        # Initialize enhanced service
        async_mongo_client = get_async_mongo_client()
        enhanced_service = EnhancedChunkedDocumentService(async_mongo_client, MONGODB_DATABASE)
        
        # Prepare file metadata for enhanced service
        current_timestamp = datetime.utcnow()
        file_metadata = {
            'filename': f"{title}.txt",
            'file_type': 'notes',
            'file_size': len(text.encode('utf-8')),
            'page_count': 1
        }
        
        # Use enhanced service for Milvus hybrid (dense + sparse) embedding creation and storage
        result = await enhanced_service.create_embeddings_and_store_Milvus_only(
            document_id=base_note_id,
            text=text,
            topic=title,
            user_id=user_id,
            utc_date=current_timestamp.isoformat(),
            file_metadata=file_metadata,
            folder_id=folder_id,  # Use determined folder_id (selected folder or 'general')
            include_topic_header=False,  # Notes don't need topic headers embedded in chunks
            department=None,
            store_chunks_in_mongodb=False  # Notes store full text in Notes collection, not chunks in document_chunked
        )
        
        vectors_created = result.get('vectors_created', 0)
        chunks = result.get('chunks', [])
        metas = result.get('metas', [])
        vector_ids = result.get('vector_ids', [])
        
        logging.info(f"✅ Enhanced service created {vectors_created} Milvus hybrid vectors for note")
        
        # LOG: Confirm document_id is set in Milvus metadata
        # The enhanced service stores metadata in Milvus directly, not in the returned metas list
        # We can verify by checking if vectors were created and document_id was passed correctly
        if vectors_created > 0:
            logging.info(f"📋 [MILVUS_METADATA] Milvus vectors created with document_id: {base_note_id}")
            logging.info(f"📋 [MILVUS_METADATA] Vector IDs: {vector_ids[:3]}..." if len(vector_ids) > 3 else f"📋 [MILVUS_METADATA] Vector IDs: {vector_ids}")
            logging.info(f"✅ [MILVUS_METADATA] Enhanced service stored {vectors_created} vectors for note_id: {base_note_id}")
        else:
            logging.warning(f"⚠️ [MILVUS_METADATA] No vectors created for note_id: {base_note_id}")

        # 3) Prepare single MongoDB document for direct storage (like audio/video services)
        mongo_docs = []
        now = datetime.utcnow()
        
        # Create single document with complete note content
        mongo_doc = {
            '_id': base_note_id,
            'note_id': base_note_id,
            'user_id': user_id,
            'folder_id': folder_id,  # Use determined folder_id (selected folder or 'general')
            'text': text,  # Store complete original text
            'title': title,
            'metadata': {
                'user_id': user_id,
                'note_id': base_note_id,
                'title': title,
                'folder_id': folder_id,  # Use determined folder_id
                'created_at': current_timestamp.isoformat(),
                'type': 'note',
                'document_type': 'notes',
                'content_type': 'notes',
                **metadata
            },
            'created_at': now,
            'updated_at': now
        }
        mongo_docs.append(mongo_doc)

        # 4) Define thread‐safe containers to capture results or errors
        milvus_result = {'upserted_count': vectors_created, 'error': None}
        mongo_result = {}

        # 5) Define the MongoDB-insert thread target using mongodb function
        def _do_mongo_insert():
            try:
                if mongo_docs:
                    inserted_count = create_note_documents(mongo_docs)
                    mongo_result['inserted_count'] = inserted_count
                    mongo_result['error'] = None
                else:
                    mongo_result['inserted_count'] = 0
                    mongo_result['error'] = None
                    logging.warning("MongoDB insert: no documents to insert")
            except Exception as e:
                mongo_result['inserted_count'] = 0
                mongo_result['error'] = str(e)
                logging.error(f"MongoDB insert thread error: {str(e)}", exc_info=True)

        # 6) Launch MongoDB thread (Milvus already handled by enhanced service)
        mongo_thread = threading.Thread(target=_do_mongo_insert, daemon=True)
        mongo_thread.start()

        # 7) Wait for MongoDB to finish
        mongo_thread.join()

        # ============= FILES COLLECTION INTEGRATION =============
        # Register note in centralized files collection for reader service
        try:
            if mongo_result.get('inserted_count', 0) > 0:
                files_service = FilesService(async_mongo_client, MONGODB_DATABASE)
                
                # Extract milvus_primary_keys from result
                milvus_primary_keys = result.get('vector_ids', [])
                
                # Build file metadata for notes
                file_metadata = {
                    "_id": base_note_id,  # Use note_id as primary key
                    "user_id": user_id,
                    "filename": title,
                    "original_filename": title,
                    "file_extension": "note",
                    "file_type_category": "note",  # For filtering and routing
                    "topic_or_filename": title,
                    "created_at": current_timestamp.isoformat(),
                    "updated_at": current_timestamp.isoformat(),
                    "folder_id": folder_id,
                    "is_enterprise": is_enterprise,
                    "entity_id": entity_id,
                    "file_size_bytes": len(text.encode('utf-8')),
                    "db_size_bytes": len(text.encode('utf-8')),
                    "storage_location": "mongodb",
                    "mongodb_collections": {
                        "notes_id": base_note_id,
                        "milvus_chunks_id": None,
                        "document_chunked_ids": None,
                        "transcripts_id": None,
                        "video_transcripts_id": None
                    },
                    "milvus_primary_keys": milvus_primary_keys
                }
                
                # Register in files collection
                file_id = await files_service.register_file(file_metadata)
                logging.info(f"[{base_note_id}] ✅ Note registered in files collection: {file_id}")
                
                # LOG: Confirm document_id (_id) is set in files collection
                logging.info(f"📋 [FILES_COLLECTION] document_id (_id) confirmed in files collection: {file_metadata['_id']}")
                logging.info(f"📋 [FILES_COLLECTION] file_type_category: {file_metadata['file_type_category']}")
                logging.info(f"📋 [FILES_COLLECTION] mongodb_collections.notes_id: {file_metadata['mongodb_collections']['notes_id']}")
                logging.info(f"✅ [FILES_COLLECTION] Note {base_note_id} ready for reader service citations")
                
        except Exception as files_error:
            # Don't fail note creation if files registration fails - just log the error
            logging.error(f"[{base_note_id}] ⚠️ Failed to register note in files collection: {files_error}")
            logging.exception(files_error)
        # ============= END FILES COLLECTION INTEGRATION =============

        # 10) Build a combined response
        response_payload = {
            "id": str(mongo_docs[0]['_id']) if mongo_docs else None,
            "note_id": base_note_id,
            "chunk_count": len(chunks),
            "milvus": {
                "upserted_count": milvus_result.get('upserted_count', 0),
                "error": milvus_result.get('error')
            },
            "mongodb": {
                "inserted_count": mongo_result.get('inserted_count', 0),
                "error": mongo_result.get('error'),
                "ids": [str(doc['_id']) for doc in mongo_docs] if mongo_docs else []
            }
        }
        logging.info(f"Response payload: {response_payload}")

        # If Milvus failed critically, return a 500—even though Mongo may have succeeded.
        if milvus_result.get('error'):
            return JSONResponse(
                content={
                    "error": f"Milvus upsert failed: {milvus_result['error']}",
                    "note_id": base_note_id,
                    "mongodb_inserted_count": mongo_result.get('inserted_count', 0)
                },
                status_code=500,
                headers=headers
            )

        # Otherwise, return overall success (even if Mongo had a partial failure)
        
        # ===================== CONCEPT MAP INTEGRATION =====================
        # Extract concepts from the note and update user's concept map
        try:
            if (CONCEPT_MAP_AVAILABLE and 
                os.getenv('CONCEPT_MAP_ENABLED', 'true').lower() == 'true' and 
                not milvus_result.get('error')):  # Only if Milvus succeeded
                
                # Check Redis cache to avoid duplicate concept processing
                redis_client = get_redis_client()
                concept_cache_key = f"concept_processed_{base_note_id}"
                concept_already_processed = False
                
                if redis_client:
                    try:
                        concept_already_processed = redis_client.exists(concept_cache_key)
                        if concept_already_processed:
                            logging.info(f"[{base_note_id}] Concept extraction already processed - skipping")
                    except Exception as redis_e:
                        logging.warning(f"[{base_note_id}] Redis cache check failed: {redis_e}")
                
                if not concept_already_processed:
                    logging.info(f"[{base_note_id}] Concept extraction disabled - module removed")
                    
                    # Concept map functionality has been removed
                    # This section is now disabled
                    
                    # Mark concept processing as complete in Redis cache (skip actual processing)
                    if redis_client:
                        try:
                            redis_client.setex(concept_cache_key, 3600, "processed")  # 1 hour TTL
                            logging.debug(f"[{base_note_id}] Marked concept processing as complete in cache")
                        except Exception as redis_e:
                            logging.warning(f"[{base_note_id}] Failed to update Redis cache: {redis_e}")
                    
                    # Log concept extraction statistics
                    if isinstance(result, dict):
                        concepts_added = result.get('concepts_added', 0)
                        concepts_updated = result.get('concepts_updated', 0)
                        total_concepts = result.get('total_concepts', 0)
                        logging.info(f"[{base_note_id}] Concept extraction completed - Added: {concepts_added}, Updated: {concepts_updated}, Total: {total_concepts}")
                    else:
                        logging.info(f"[{base_note_id}] Concept map updated successfully!")
            else:
                if not CONCEPT_MAP_AVAILABLE:
                    logging.debug(f"[{base_note_id}] Concept map not available")
                elif milvus_result.get('error'):
                    logging.debug(f"[{base_note_id}] Skipping concept extraction due to Milvus error")
                else:
                    logging.debug(f"[{base_note_id}] Concept map integration disabled")
                
        except Exception as e:
            # Don't fail the entire note creation if concept extraction fails
            logging.error(f"[{base_note_id}] Concept extraction failed (non-critical): {str(e)}")
            traceback.print_exc()
            # Continue with note creation
        # ===================================================================
        
        return JSONResponse(
            content={
                "message": f"Successfully created note with {len(chunks)} chunks under note_id {base_note_id}",
                **response_payload
            },
            status_code=200,
            headers=headers
        )

    except Exception as e:
        logging.error(f"Error in create_note: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"error": f"Failed to create note: {str(e)}"},
            status_code=500,
            headers=headers
        )

async def handle_search_notes(request: Request, headers: dict) -> JSONResponse:
    """
    Handle note search operations using Milvus hybrid search.
    Delegates to UnifiedQueryEngine for proper hybrid (dense + sparse) vector search.
    """
    try:
        logging.info("Processing search notes request")
        
        req_body = await request.json()
        if not req_body:
            return JSONResponse(
                content={"error": "Request body is required"},
                status_code=400,
                headers=headers
            )
        
        user_id = get_secure_user_id(request)
        query_text = req_body.get('query')
        
        if not user_id:
            return JSONResponse(
                content={"error": "user_id is required"},
                status_code=400,
                headers=headers
            )
        
        if not query_text:
            return JSONResponse(
                content={"error": "query is required"},
                status_code=400,
                headers=headers
            )
        
        # Optional parameters
        top_k = req_body.get('top_k', 10)
        include_metadata = req_body.get('include_metadata', True)
        filter_metadata = req_body.get('filter', {})
        
        # Initialize Milvus if not already initialized
        milvus_client = initialize_milvus()
        if not milvus_client:
            return JSONResponse(
                content={"error": "Failed to initialize Milvus client"},
                status_code=500,
                headers=headers
            )
        
        # Use UnifiedQueryEngine for search
        from llamaindex_query_engine import UnifiedQueryEngine
        query_engine = UnifiedQueryEngine(user_id=user_id)
        
        # Perform dense vector search
        search_results = await query_engine.retrieve_personal_context(
            query=query_text,
            user_id=user_id,
            top_k=top_k
        )
        
        # Convert results to match expected format
        matches = []
        for result in search_results:
            match_dict = {
                "id": result.get("id", ""),
                "score": float(result.get("score", 0.0))
            }
            
            if include_metadata and "metadata" in result:
                match_dict["metadata"] = result["metadata"]
            
            matches.append(match_dict)
        
        return JSONResponse(
            content={
                "matches": matches,
                "namespace": user_id,
                "query_text": query_text,
                "search_type": "hybrid"  # Indicate hybrid search was used
            },
            status_code=200,
            headers=headers
        )

    except Exception as e:
        logging.error(f"Error in search_notes: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"error": f"Failed to search notes: {str(e)}"},
            status_code=500,
            headers=headers
        )

async def handle_list_notes(request: Request, headers: dict) -> JSONResponse:
    """Handle listing notes from MongoDB metadata"""
    try:
        logging.info("Processing list notes request")
        
        user_id = get_secure_user_id(request)
        
        logging.info(f"Listing notes for user_id: {user_id}")
        
        # Pagination parameters
        limit = int(request.query_params.get('limit', 50))
        skip = int(request.query_params.get('skip', 0))
        folder_id = request.query_params.get('folder_id')  # Get folder_id from query params (optional)
        
        # Validation
        if limit > 100:
            limit = 100
        if skip < 0:
            skip = 0
        
        # Resolve the correct user_id for querying (handles shared vault access)
        query_user_id = user_id
        if folder_id:
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
                        logging.info(f"📂 Shared vault access: querying notes with owner_id={query_user_id}")
            except Exception as auth_err:
                logging.warning(f"⚠️ Error checking shared vault access for notes: {auth_err}")
        
        # Get notes from MongoDB using mongodb functions, filtering by folder_id
        notes = get_notes_list(query_user_id, limit, skip, folder_id)
        total_count = get_notes_count(query_user_id, folder_id)
        
        logging.info(f"Retrieved {len(notes)} notes from MongoDB")
        
        return JSONResponse(
            content={
                "notes": notes,
                "count": len(notes),
                "total_count": total_count,
                "limit": limit,
                "skip": skip
            },
            status_code=200,
            headers=headers
        )

    except Exception as e:
        logging.error(f"Error in list_notes: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"error": f"Failed to list notes: {str(e)}"},
            status_code=500,
            headers=headers
        )

async def handle_get_note_metadata(request: Request, headers: dict) -> JSONResponse:
    """Handle getting specific note metadata"""
    try:
        logging.info("Processing get note metadata request")
        
        note_id = request.query_params.get('note_id')
        mongodb_id = request.query_params.get('mongodb_id')
        
        if not note_id and not mongodb_id:
            return JSONResponse(
                content={"error": "Either note_id or mongodb_id is required"},
                status_code=400,
                headers=headers
            )
        
        # Get note metadata using mongodb functions
        if mongodb_id:
            doc = get_note_metadata_by_mongodb_id(mongodb_id)
            if doc is None:
                return JSONResponse(
                    content={"error": "Invalid MongoDB ID format"},
                    status_code=400,
                    headers=headers
                )
        else:
            doc = get_note_metadata_by_note_id(note_id)
        
        if not doc:
            return JSONResponse(
                content={"error": "Note metadata not found"},
                status_code=404,
                headers=headers
            )

        return JSONResponse(
            content={"note_metadata": doc},
            status_code=200,
            headers=headers
        )
    
    except Exception as e:
        logging.error(f"Error in get_note_metadata: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"error": f"Failed to get note metadata: {str(e)}"},
            status_code=500,
            headers=headers
        )

async def handle_get_note_stats(request: Request, headers: dict) -> JSONResponse:
    """
    Handle getting note statistics from Milvus and MongoDB.
    Returns vector counts from Milvus collection and document counts from MongoDB.
    """
    try:
        logging.info("Processing get note stats request")
        
        user_id = get_secure_user_id(request)
        
        # Initialize Milvus client
        milvus_client = initialize_milvus()
        if not milvus_client:
            return JSONResponse(
                content={"error": "Failed to initialize Milvus client"},
                status_code=500,
                headers=headers
            )
        
        # Get collection stats from Milvus
        collection_name = os.getenv('MILVUS_COLLECTION_NAME', 'citra')
        milvus_stats = {}
        
        try:
            # Query Milvus to get entity count
            if user_id:
                # Count vectors for specific user
                from pymilvus import utility
                # Note: Milvus doesn't natively support per-user counts without filtering
                # We'll return total collection stats and MongoDB count for the user
                milvus_stats = {
                    "collection": collection_name,
                    "note": "User-specific vector counts require full collection scan"
                }
            else:
                # Get total collection stats
                from pymilvus import utility, connections
                # Connect if not already connected
                if collection_name:
                    milvus_stats = {
                        "collection": collection_name,
                        "note": "Query collection for detailed stats"
                    }
        except Exception as e:
            logging.warning(f"Could not retrieve Milvus stats: {e}")
            milvus_stats = {"error": str(e)}
        
        # Get MongoDB stats using mongodb function
        mongodb_count = get_notes_stats(user_id)
        
        return JSONResponse(
            content={
                "milvus_stats": milvus_stats,
                "mongodb_count": mongodb_count,
                "user_id": user_id,
                "note": "Milvus stats are collection-level; MongoDB count is user-specific"
            },
            status_code=200,
            headers=headers
        )
    
    except Exception as e:
        logging.error(f"Error in get_note_stats: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"error": f"Failed to get note stats: {str(e)}"},
            status_code=500,
            headers=headers
        )

async def handle_update_note(request: Request, headers: dict) -> JSONResponse:
    """
    Handle updating existing notes in Milvus and MongoDB.
    Updates are done by deleting old vectors and creating new ones with updated content.
    """
    try:
        # SECURITY: Authenticate user from JWT token
        user_id_auth = get_secure_user_id(request)

        logging.info("Processing update note request")
        
        req_body = await request.json()
        if not req_body:
            return JSONResponse(
                content={"error": "Request body is required"},
                status_code=400,
                headers=headers
            )

        note_id = req_body.get('note_id')
        mongodb_id = req_body.get('mongodb_id')
        new_text = req_body.get('text')
        new_metadata = req_body.get('metadata', {})

        if not note_id and not mongodb_id:
            return JSONResponse(
                content={"error": "Either note_id or mongodb_id is required"},
                status_code=400,
                headers=headers
            )

        # Initialize Milvus
        milvus_client = initialize_milvus()
        if not milvus_client:
            return JSONResponse(
                content={"error": "Failed to initialize Milvus client"},
                status_code=500,
                headers=headers
            )
        
        # SECURITY: Get notes to update filtered by authenticated user_id
        docs = get_notes_to_update(note_id, mongodb_id, user_id=user_id_auth)

        if not docs:
            return JSONResponse(
                content={"error": "No notes found to update"},
                status_code=404,
                headers=headers
            )

        updated_count = 0
        from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
        async_mongo_client = get_async_mongo_client()
        enhanced_service = EnhancedChunkedDocumentService(async_mongo_client, MONGODB_DATABASE)

        for doc in docs:
            document_id = str(doc['_id'])
            user_id = doc['user_id']
            
            # If text is provided, we need to delete old vectors and create new ones
            if new_text:
                # Delete old vectors from Milvus
                try:
                    await enhanced_service.delete_from_milvus(document_id, user_id)
                except Exception as e:
                    logging.warning(f"Could not delete old vectors for {document_id}: {e}")
                
                # Create new vectors with updated text
                topic = doc.get('topic', 'Updated Note')
                utc_date = datetime.utcnow().isoformat()
                
                # Merge existing metadata with new metadata
                file_metadata = doc.get('metadata', {})
                file_metadata.update(new_metadata)
                file_metadata['updated_at'] = utc_date
                
                # Create new embeddings and store in Milvus
                await enhanced_service.create_embeddings_and_store_Milvus_only(
                    document_id=document_id,
                    text=new_text,
                    topic=topic,
                    user_id=user_id,
                    utc_date=utc_date,
                    file_metadata=file_metadata,
                    folder_id=doc.get('folder_id'),
                    include_topic_header=False
                )
                
                # Update MongoDB
                update_note_document(doc['_id'], new_text, new_metadata)
            else:
                # Only update metadata in MongoDB (vectors stay the same)
                update_note_document(doc['_id'], None, new_metadata)
            
            updated_count += 1
        
        return JSONResponse(
            content={
                "message": f"Successfully updated {updated_count} notes",
                "updated_count": updated_count
            },
            status_code=200,
            headers=headers
        )
    
    except Exception as e:
        logging.error(f"Error in update_note: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"error": f"Failed to update note: {str(e)}"},
            status_code=500,
            headers=headers
        )

async def handle_delete_notes(request: Request, headers: dict) -> JSONResponse:
    """
    Handle deleting specific notes from Milvus and MongoDB.
    Uses EnhancedChunkedDocumentService to delete vectors from Milvus.
    """
    try:
        logging.info("Processing delete notes request")
        
        req_body = await request.json()
        if not req_body:
            return JSONResponse(
                content={"error": "Request body is required"},
                status_code=400,
                headers=headers
            )
        
        note_ids = req_body.get('note_ids', [])
        mongodb_ids = req_body.get('mongodb_ids', [])
        user_id = get_secure_user_id(request)
        
        if not note_ids and not mongodb_ids:
            return JSONResponse(
                content={"error": "Either note_ids or mongodb_ids is required"},
                status_code=400,
                headers=headers
            )

        # Initialize Milvus
        milvus_client = initialize_milvus()
        if not milvus_client:
            return JSONResponse(
                content={"error": "Failed to initialize Milvus client"},
                status_code=500,
                headers=headers
            )
        
        # SECURITY: Get documents to delete using mongodb function filtered by authenticated user_id
        docs_to_delete = get_notes_to_delete(note_ids, mongodb_ids, user_id=user_id)
        logging.info(f"docs_to_delete: {docs_to_delete} for note_ids: {note_ids}, mongodb_ids: {mongodb_ids}")

        if not docs_to_delete:
            return JSONResponse(
                content={"error": "No notes found to delete"},
                status_code=404,
                headers=headers
            )

        # Delete vectors from Milvus using service
        from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
        async_mongo_client = get_async_mongo_client()
        enhanced_service = EnhancedChunkedDocumentService(async_mongo_client, MONGODB_DATABASE)
        milvus_deleted = 0
        
        for doc in docs_to_delete:
            document_id = str(doc.get('_id')) or doc.get('note_id')
            doc_user_id = doc['user_id']
            
            try:
                await enhanced_service.delete_from_milvus(document_id, doc_user_id)
                # Count chunks that were deleted
                total_chunks = doc.get('total_chunks', 1)
                milvus_deleted += total_chunks
            except Exception as e:
                logging.warning(f"Could not delete vectors for document {document_id}: {e}")
        
        # SECURITY: Delete from MongoDB using mongodb function filtered by authenticated user_id
        mongodb_deleted = delete_notes_by_query(note_ids, mongodb_ids, user_id=user_id)

        return JSONResponse(
            content={
                "message": f"Successfully deleted {milvus_deleted} note chunks from Milvus and {mongodb_deleted} from MongoDB",
                "milvus_deleted": milvus_deleted,
                "mongodb_deleted": mongodb_deleted
            },
            status_code=200,
            headers=headers
        )

    except Exception as e:
        logging.error(f"Error in delete_notes: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"error": f"Failed to delete notes: {str(e)}"},
            status_code=500,
            headers=headers
        )

async def handle_delete_all_notes(request: Request, headers: dict) -> JSONResponse:
    """
    Handle deleting all notes for a user from Milvus and MongoDB.
    Uses EnhancedChunkedDocumentService to delete vectors from Milvus.
    """
    try:
        logging.info("Processing delete all notes request")
        
        user_id = get_secure_user_id(request)

        logging.info(f"Deleting all notes for user_id: {user_id}")

        # Initialize Milvus
        milvus_client = initialize_milvus()
        if not milvus_client:
            return JSONResponse(
                content={"error": "Failed to initialize Milvus client"},
                status_code=500,
                headers=headers
            )

        # Track deletion results
        milvus_deleted = 0
        mongo_deleted_count = 0
        milvus_error = None
        
        # Get all notes for this user from MongoDB
        notes = get_notes_list(user_id, limit=10000, skip=0)
        
        # Delete from Milvus using service
        from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
        async_mongo_client = get_async_mongo_client()
        enhanced_service = EnhancedChunkedDocumentService(async_mongo_client, MONGODB_DATABASE)
        
        if notes:
            for note in notes:
                document_id = str(note.get('_id')) or note.get('note_id')
                
                try:
                    await enhanced_service.delete_from_milvus(document_id, user_id)
                    total_chunks = note.get('total_chunks', 1)
                    milvus_deleted += total_chunks
                except Exception as e:
                    logging.warning(f"Could not delete vectors for document {document_id}: {e}")
                    if not milvus_error:
                        milvus_error = str(e)
        
        # Delete from MongoDB using mongodb function
        try:
            mongo_deleted_count = delete_all_notes_for_device(user_id)
        except Exception as mongo_error:
            logging.error(f"Error deleting from MongoDB: {str(mongo_error)}")
        
        # Prepare response
        response_message = f"Successfully deleted {milvus_deleted} note chunks from Milvus and {mongo_deleted_count} from MongoDB"
        if milvus_error:
            response_message += f". Some Milvus deletions had errors: {milvus_error[:100]}"
        
        logging.info(response_message)
        
        return JSONResponse(
            content={
                "message": response_message,
                "user_id": user_id,
                "mongodb_deleted": mongo_deleted_count,
                "milvus_deleted": milvus_deleted,
                "had_errors": milvus_error is not None
            },
            status_code=200,
            headers=headers
        )
    
    except Exception as e:
        logging.error(f"Error in delete_all_notes: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"error": f"Failed to delete all notes: {str(e)}"},
            status_code=500,
            headers=headers
        )

# Utility functions

# LEGACY FUNCTIONS REMOVED:
# - initialize_openai_embedding(): No longer needed - embeddings handled by EnhancedChunkedDocumentService
# - create_embedding(): No longer needed - embeddings handled by EnhancedChunkedDocumentService via LLM
# All embedding creation is now centralized in services/enhanced_chunked_document_service.py

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """
    Split text into chunks without using spaCy
    Uses sentence-based chunking with overlap.
    
    NOTE: This function is kept for backward compatibility, but new code should use
    EnhancedChunkedDocumentService.intelligent_chunking() which provides better chunking.
    """
    # Split by sentences using simple regex
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    
    chunks = []
    current_chunk = ""
    current_length = 0
    
    for sentence in sentences:
        sentence_length = len(sentence.split())
        
        # If adding this sentence would exceed chunk size, save current chunk
        if current_length + sentence_length > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            
            # Start new chunk with overlap
            if overlap > 0:
                overlap_words = current_chunk.split()[-overlap:]
                current_chunk = " ".join(overlap_words) + " " + sentence
                current_length = len(overlap_words) + sentence_length
            else:
                current_chunk = sentence
                current_length = sentence_length
        else:
            current_chunk += " " + sentence if current_chunk else sentence
            current_length += sentence_length
    
    # Add the last chunk if it exists
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    # If no chunks were created (e.g., single long sentence), split by words
    if not chunks and text:
        words = text.split()
        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            chunks.append(" ".join(chunk_words))
    
    return chunks

# =============================================================================
# FASTAPI ROUTER SETUP
# =============================================================================
# Note: Router is already defined above at line 316 with proper multi-method handling
# No duplicate router needed here

