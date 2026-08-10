# ============================  Chunked Documents API  =============================
# Purpose: API endpoints for chunked document operations with pagination
# Features: Upload, retrieve, paginate, and manage large documents
# ----------------------------------------------------------------------------------------

from fastapi import APIRouter, HTTPException, Query, Depends, File, UploadFile, Form, Request
from typing import Optional, List, Dict, Any
import logging
import tempfile
import os
import uuid
from datetime import datetime, timedelta
import urllib.parse
import re
from pathlib import Path

from services.enhanced_chunked_document_service import EnhancedChunkedDocumentService
from models.document_chunk import (
    ChunkResponse, DocumentMetadataResponse, PaginatedChunksResponse,
    DocumentListResponse, DocumentMetadataModel
)

# Import MongoDB connection (you'll need to adapt this to your existing setup)
from utils import get_mongo_collection

# Import auth middleware for secure user_id extraction
from citra_auth import get_secure_user_id

# Import note functions


router = APIRouter(prefix="/api/v2/documents/chunked", tags=["chunked-documents"])
logger = logging.getLogger(__name__)

def _normalize_file_extension(file_extension: Optional[str]) -> str:
    if not file_extension:
        return ''
    return file_extension if file_extension.startswith('.') else f".{file_extension}"


def _sanitize_blob_filename(filename: Optional[str]) -> str:
    """
    Sanitize filename for Azure Blob Storage compatibility.
    MUST MATCH the logic in document_manager.py for consistency!
    
    Azure Blob Storage naming rules:
    - Avoid: < > : " / \\ | ? * and characters with ASCII values 0-31
    - Normalize spaces, dots, and special characters
    - Remove leading/trailing problematic characters
    """
    if not filename:
        return ''
    
    # Remove leading/trailing whitespace
    filename = filename.strip()
    
    # Replace Azure-forbidden characters with underscore
    forbidden_chars = r'[<>:"/\\|?*\x00-\x1f]'
    filename = re.sub(forbidden_chars, '_', filename)
    
    # Normalize multiple consecutive spaces to single space
    filename = re.sub(r'\s+', ' ', filename)
    
    # Replace spaces with underscores for better URL compatibility
    filename = filename.replace(' ', '_')
    
    # Normalize multiple consecutive dots
    filename = re.sub(r'\.{2,}', '.', filename)
    
    # Normalize multiple consecutive underscores
    filename = re.sub(r'_{2,}', '_', filename)
    
    # Normalize multiple consecutive parentheses
    filename = re.sub(r'\({2,}', '(', filename)
    filename = re.sub(r'\){2,}', ')', filename)
    
    # Remove leading/trailing dots and underscores
    filename = filename.strip('._')
    
    # Special case: Remove trailing underscore before extension
    from pathlib import Path
    path_obj = Path(filename)
    if path_obj.suffix:
        stem = path_obj.stem.rstrip('_')
        filename = f"{stem}{path_obj.suffix}"
    
    # Limit length (keeping it reasonable)
    max_length = 200
    if len(filename) > max_length:
        path_obj = Path(filename)
        ext = path_obj.suffix
        stem = path_obj.stem[:max_length - len(ext)]
        filename = f"{stem}{ext}"
    
    return filename


def _build_download_blob_name(document_id: str, file_type: Optional[str], filename: Optional[str]) -> str:
    """
    Build blob name matching Azure upload logic.
    
    MUST MATCH the logic in _get_blob_filename_variants() in document_manager.py:
    - Sanitize filename using same rules
    - Extract stem and suffix using Path
    - Use filename extension if present, otherwise use file_type
    - Fallback to document_id if no filename
    """
    from pathlib import Path
    
    normalized_ext = _normalize_file_extension(file_type)
    safe_filename = _sanitize_blob_filename(filename)

    logger.debug(f"🔍 BLOB_NAME_DEBUG: document_id={document_id}, file_type={file_type}, filename={filename}")
    logger.debug(f"🔍 BLOB_NAME_DEBUG: normalized_ext={normalized_ext}, safe_filename={safe_filename}")

    if safe_filename:
        # Match document_manager.py logic exactly
        filename_path = Path(safe_filename)
        filename_base = filename_path.stem[:100].lstrip('_')
        filename_ext = filename_path.suffix or normalized_ext
        result = f"{filename_base}{filename_ext}"
        logger.debug(f"🔍 BLOB_NAME_DEBUG: Using filename - base={filename_base}, ext={filename_ext}, result={result}")
        return result

    # No filename: fallback to document_id
    result = f"{document_id}{normalized_ext}" if normalized_ext else document_id
    logger.debug(f"🔍 BLOB_NAME_DEBUG: Using document_id - result={result}")
    return result


def _generate_download_url(document_id: str, user_id: str, file_type: str, filename: Optional[str] = None) -> Optional[str]:
    """
    Generate S3 download URL for document file.
    
    Uses files_service as single source of truth for S3 URLs.
    Returns backend download endpoint that generates presigned URLs.
    """
    try:
        logger.info(f"Generating S3 download URL for document_id={document_id}, user_id={user_id}")
        
        # Get S3 URL from files collection (single source of truth)
        from citra_mongo import get_sync_database
        from services.files_service import FilesService
        
        # Use sync MongoDB for this function
        db = get_sync_database()
        files_collection = db.files
        
        # Look up file in files registry
        file_record = files_collection.find_one({
            "_id": document_id,
            "user_id": user_id
        })
        
        if file_record and file_record.get("s3_url"):
            s3_url = file_record["s3_url"]
            
            # Extract S3 key from URL
            _bucket = os.getenv("BUCKET_NAME", "citra-documents")
            if ".amazonaws.com/" in s3_url:
                s3_key = s3_url.split(".amazonaws.com/")[-1]
            elif "s3://" in s3_url:
                s3_key = s3_url.split("s3://", 1)[-1].split("/", 1)[-1]
            else:
                s3_key = s3_url  # Fallback
            
            # Return backend download endpoint (will generate presigned URL on-demand)
            base_url = os.getenv("BASE_URL", "http://localhost:8085/")
            if not base_url.endswith("/"):
                base_url += "/"
            
            # URL-encode the S3 key for safe transmission
            encoded_key = urllib.parse.quote(s3_key, safe="")
            download_url = f"{base_url}download/{encoded_key}"
            
            logger.info(f"✅ Generated S3 download URL: {download_url}")
            return download_url
        else:
            logger.warning(f"⚠️ No S3 URL found in files collection for document_id={document_id}")
            return None
            
    except Exception as e:
        logger.error(f"Error generating S3 download URL for {document_id}: {e}")
        return None

def get_chunked_service() -> EnhancedChunkedDocumentService:
    """Get EnhancedChunkedDocumentService instance using centralized MongoDB manager"""
    from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
    
    async_mongo_client = get_async_mongo_client()
    return EnhancedChunkedDocumentService(async_mongo_client, MONGODB_DATABASE)


@router.get("/metadata/{document_id}")
async def get_document_metadata(
    document_id: str,
    service: EnhancedChunkedDocumentService = Depends(get_chunked_service)
):
    """Get document metadata"""
    try:
        metadata = await service.get_document_metadata(document_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Generate download URL if missing
        file_url = metadata.fileUrl
        if not file_url:
            file_url = _generate_download_url(
                metadata.document_id,
                metadata.user_id,
                metadata.file_type,
                getattr(metadata, 'topic_or_filename', None)
            )
        
        # Handle KG processing status
        kg_processed = getattr(metadata, 'kg_processed', False)
        kg_processed_at = getattr(metadata, 'kg_processed_at', None)
        kg_processed_at_str = kg_processed_at.isoformat() if kg_processed_at else None
        
        return DocumentMetadataResponse(
            document_id=metadata.document_id,
            file_type=metadata.file_type,
            total_pages=metadata.total_pages,
            total_chunks=metadata.total_chunks,
            chunk_size=metadata.chunk_size,
            processing_status=metadata.processing_status,
            created_at=metadata.created_at.isoformat(),
            updated_at=metadata.updated_at.isoformat(),
            topic_or_filename=metadata.topic_or_filename,
            file_size=metadata.file_size,
            fileUrl=file_url,
            kg_processed=kg_processed,
            kg_processed_at=kg_processed_at_str
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document metadata: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{document_id}/chunks")
async def get_document_chunks(
    document_id: str,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Chunks per page"),
    hybrid: bool = Query(False, description="Use True Hybrid mode (fetch text from Milvus)"),
    service: EnhancedChunkedDocumentService = Depends(get_chunked_service)
):
    """Get chunks for a document with pagination.
    
    Args:
        document_id: Document ID to fetch
        page: Page number (1-based)
        per_page: Chunks per page
        hybrid: If True, use True Hybrid mode (text from Milvus), else MongoDB-only
    
    Returns:
        Paginated chunks with content
    """
    try:
        # Choose fetch method based on hybrid flag
        if hybrid:
            # TRUE HYBRID: Schema from MongoDB, text from Milvus
            # Note: get_chunks_hybrid returns raw dicts, not MongoDbChunkModel objects
            chunks_raw, total = await service.get_chunks_hybrid(
                document_id=document_id,
                user_id="",  # Will be extracted from token in future
                page=page,
                limit=per_page
            )
            
            # Convert raw dicts to response format
            chunk_responses = []
            for chunk_dict in chunks_raw:
                chunk_metadata = chunk_dict.get("metadata", {})
                chunk_responses.append(ChunkResponse(
                    chunk_index=chunk_dict.get("chunk_index", 0),
                    start_page=chunk_dict.get("start_page", 1),
                    end_page=chunk_dict.get("end_page", 1),
                    total_pages=chunk_dict.get("total_pages", 1),
                    content=chunk_dict.get("content", ""),  # Text from Milvus
                    # Populate citation fields from root level (not metadata)
                    topic_or_filename=chunk_dict.get('topic_or_filename'),
                    source=chunk_dict.get('topic_or_filename'),
                    file_type=chunk_dict.get('file_type'),
                    metadata=chunk_metadata
                ))
        else:
            # MongoDB-only fetch (backward compatible)
            chunks, total = await service.get_document_chunks(
                document_id=document_id,
                page=page,
                per_page=per_page
            )
            
            # ✅ Content and citation fields from metadata (no fallback)
            chunk_responses = []
            for chunk in chunks:
                chunk_metadata = chunk.metadata or {}
                
                # Extract citation fields from metadata for API response
                chunk_responses.append(ChunkResponse(
                    chunk_index=chunk.chunk_index,
                    start_page=chunk.start_page,
                    end_page=chunk.end_page,
                    total_pages=chunk.total_pages,
                    content=chunk_metadata.get('text', ''),
                    # Populate citation fields from root level (not metadata)
                    topic_or_filename=chunk.topic_or_filename,
                    source=chunk.topic_or_filename,
                    file_type=chunk.file_type,
                    metadata=chunk_metadata
                ))
        
        total_pages = (total + per_page - 1) // per_page
        
        return PaginatedChunksResponse(
            chunks=chunk_responses,
            pagination={
                "current_page": page,
                "per_page": per_page,
                "total_chunks": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
                "next_page": page + 1 if page < total_pages else None,
                "prev_page": page - 1 if page > 1 else None
            }
        )
    
    except Exception as e:
        logger.error(f"Error getting document chunks: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# @router.get("/{document_id}/search")
# async def search_document_chunks(
#     document_id: str,
#     query: str = Query(..., description="Search query"),
#     page: int = Query(1, ge=1, description="Page number (1-based)"),
#     per_page: int = Query(20, ge=1, le=100, description="Results per page"),
#     service: EnhancedChunkedDocumentService = Depends(get_chunked_service)
# ):
#     """Search within a specific document's chunks"""
#     try:
#         chunks, total = await service.search_document_chunks(
#             document_id=document_id,
#             search_query=query,
#             page=page,
#             per_page=per_page
#         )
#         
#         total_pages = (total + per_page - 1) // per_page
#         
#         # ✅ BREAKING CHANGE: Content and citation fields ONLY from metadata (no fallback)
#         chunk_responses = []
#         for chunk in chunks:
#             chunk_metadata = chunk.metadata or {}
#             
#             # Extract citation fields from metadata for API response
#             chunk_responses.append(ChunkResponse(
#                 chunk_index=chunk.chunk_index,
#                 start_page=chunk.start_page,
#                 end_page=chunk.end_page,
#                 total_pages=chunk.total_pages,
#                 content=chunk_metadata.get('text', ''),
#                 # Populate citation fields from metadata
#                 page_number=chunk_metadata.get('page_number'),
#                 paragraph_number=chunk_metadata.get('paragraph_number'),
#                 topic_or_filename=chunk_metadata.get('topic_or_filename'),
#                 document_title=chunk_metadata.get('topic_or_filename'),
#                 file_type=chunk_metadata.get('file_type'),
#                 metadata=chunk_metadata
#             ))
#         
#         
#         return PaginatedChunksResponse(
#             chunks=chunk_responses,
#             pagination={
#                 "current_page": page,
#                 "per_page": per_page,
#                 "total_chunks": total,
#                 "total_pages": total_pages,
#                 "has_next": page < total_pages,
#                 "has_prev": page > 1,
#                 "next_page": page + 1 if page < total_pages else None,
#                 "prev_page": page - 1 if page > 1 else None
#             }
#         )
#     
#     except Exception as e:
#         logger.error(f"Error searching document chunks: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

@router.get("/{document_id}/pages")
async def get_document_pages(
    document_id: str,
    start_page: int = Query(1, ge=1, description="Starting page number"),
    end_page: int = Query(None, description="Ending page number (inclusive)"),
    service: EnhancedChunkedDocumentService = Depends(get_chunked_service)
):
    """Get specific pages from a document"""
    try:
        # Get document metadata to validate page numbers
        metadata = await service.get_document_metadata(document_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Validate page numbers
        if start_page > metadata.total_pages:
            raise HTTPException(
                status_code=400, 
                detail=f"Start page {start_page} exceeds document total pages {metadata.total_pages}"
            )
        
        if end_page is None:
            end_page = start_page
        elif end_page > metadata.total_pages:
            end_page = metadata.total_pages
        elif end_page < start_page:
            raise HTTPException(
                status_code=400, 
                detail="End page must be greater than or equal to start page"
            )
        
        # Get chunks for the specified page range
        pages_content = await service.get_document_pages(
            document_id=document_id,
            start_page=start_page,
            end_page=end_page
        )
        
        return {
            "document_id": document_id,
            "start_page": start_page,
            "end_page": end_page,
            "pages": pages_content,
            "total_pages_returned": len(pages_content)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pages: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/list", response_model=DocumentListResponse)
async def list_documents(
    request: Request,
    folder_id: Optional[str] = Query(None, description="Filter by folder ID"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Documents per page"),
    search: Optional[str] = Query(None, description="Search in topic_or_filename only"),
    service: EnhancedChunkedDocumentService = Depends(get_chunked_service)
):
    """List chunked documents (PDFs, Word, Excel) for the authenticated user.

    This endpoint ONLY handles chunked documents like PDFs, Word files, and Excel files.
    For notes, use the dedicated /note endpoint.
    For transcripts, use the dedicated audio-to-text and video-to-text endpoints.

    🔒 SECURITY: Uses authenticated user_id from JWT token to prevent data spoofing.
    """
    try:
        # 🔒 SECURITY: Get authenticated user_id from JWT token (prevents spoofing)
        user_id = get_secure_user_id(request)
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Authentication required - no valid user_id in token"
            )

        logger.info(f"🔒 Fetching chunked documents for authenticated user_id={user_id}, folder_id={folder_id}")

        # Get direct access to MongoDB collection for optimized querying
        from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
        async_mongo_client = get_async_mongo_client()
        db = async_mongo_client[MONGODB_DATABASE]
        chunk_collection = db.document_chunked

        # Determine effective user_id for querying
        # If folder_id is provided, check if the folder is shared with this user
        effective_user_id = user_id
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
                        effective_user_id = vault_owner
                        logger.info(f"📂 Shared folder access: querying with owner_id={effective_user_id} for shared user={user_id}")
            except Exception as share_err:
                logger.warning(f"⚠️ Shared folder check failed: {share_err}")

        # Build base query filter
        base_filter = {
            "user_id": effective_user_id,
            "chunk_index": 0,  # Only get metadata from first chunk
            # Exclude enterprise uploads from personal folder views
            # is_enterprise is either True (enterprise) or False/None/missing (personal)
            "is_enterprise": {"$ne": True}  # Exclude documents where is_enterprise is explicitly True
        }

        # Add folder filter if provided
        if folder_id:
            base_filter["folder_id"] = folder_id

        # Add topic_or_filename search filter if search provided
        search_filter = {}
        if search and search.strip():
            search_term = search.strip()
            # Case-insensitive regex search in topic_or_filename only
            search_filter = {"topic_or_filename": {"$regex": search_term, "$options": "i"}}

        # Combine filters
        final_filter = {**base_filter, **search_filter}

        # Get total count for filtered results using aggregation (more reliable than count_documents)
        total_pipeline = [{"$match": final_filter}, {"$count": "total"}]
        total_result = await chunk_collection.aggregate(total_pipeline).to_list(length=None)
        total = total_result[0]["total"] if total_result else 0

        # Get paginated results with sorting
        skip = (page - 1) * per_page
        cursor = chunk_collection.find(final_filter).sort("created_at", -1).skip(skip).limit(per_page)

        # Get files collection for accurate file metadata
        files_collection = db["files"]

        documents = []
        async for doc in cursor:
            # Handle ObjectId conversion
            if "_id" in doc and doc["_id"]:
                doc["_id"] = str(doc["_id"])

            document_id = doc.get('document_id', doc.get('_id', ''))

            # 🔍 ENHANCED: Fetch accurate file_type from files collection
            file_type_from_chunked = doc.get('file_type', '')
            file_record = await files_collection.find_one({"_id": document_id, "user_id": effective_user_id})
            
            if file_record:
                # Use file_extension from files collection (more reliable)
                file_type = file_record.get('file_extension', file_type_from_chunked)
                logger.info(f"📄 Document {document_id}: file_type from files collection: {file_type}")
            else:
                # Fallback to document_chunked file_type
                file_type = file_type_from_chunked
                if file_type_from_chunked:
                    logger.debug(f"📄 Document {document_id}: using file_type from document_chunked: {file_type}")

            # Safely handle datetime conversion
            created_at = doc.get('created_at', datetime.utcnow())
            updated_at = doc.get('updated_at', datetime.utcnow())

            created_at_str = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
            updated_at_str = updated_at.isoformat() if isinstance(updated_at, datetime) else str(updated_at)

            # Generate download URL - DISABLED (not needed, URLs generated on-demand when downloading)
            file_url = doc.get('fileUrl')
            # if not file_url:
            #     file_url = _generate_download_url(
            #         document_id,
            #         doc.get('user_id', user_id),
            #         file_type,
            #         doc.get('topic_or_filename')
            #     )

            # Handle is_enterprise field - convert None/null to False
            is_enterprise_value = doc.get('is_enterprise', False)
            if is_enterprise_value is None:
                is_enterprise_value = False

            # Handle KG processing status
            kg_processed_value = doc.get('kg_processed', False)
            kg_processed_at_value = doc.get('kg_processed_at')
            if kg_processed_at_value and isinstance(kg_processed_at_value, datetime):
                kg_processed_at_str = kg_processed_at_value.isoformat()
            else:
                kg_processed_at_str = None

            document_responses = DocumentMetadataResponse(
                document_id=document_id,
                file_type=file_type,  # Use file_type from files collection
                total_pages=doc.get('total_pages', 0),
                total_chunks=doc.get('total_chunks', 0),
                chunk_size=doc.get('chunk_size', 0),
                processing_status=doc.get('processing_status', 'completed'),
                created_at=created_at_str,
                updated_at=updated_at_str,
                topic_or_filename=doc.get('topic_or_filename'),
                file_size=doc.get('file_size', 0),
                fileUrl=file_url,
                is_enterprise=is_enterprise_value,
                kg_processed=kg_processed_value,
                kg_processed_at=kg_processed_at_str
            )

            documents.append(document_responses)

        total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0

        return DocumentListResponse(
            documents=documents,
            pagination={
                "current_page": page,
                "per_page": per_page,
                "total_documents": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
                "next_page": page + 1 if page < total_pages else None,
                "prev_page": page - 1 if page > 1 else None
            }
        )

    except Exception as e:
        logger.error(f"❌ Error listing documents: {e}")
        # Return empty response instead of raising exception to prevent UI crashes
        return DocumentListResponse(
            documents=[],
            pagination={
                "current_page": page,
                "per_page": per_page,
                "total_documents": 0,
                "total_pages": 0,
                "has_next": False,
                "has_prev": False,
                "next_page": None,
                "prev_page": None
            }
        )

@router.get("/enterprise/list", response_model=DocumentListResponse)
async def list_enterprise_documents(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Documents per page"),
    search: Optional[str] = Query(None, description="Search in filename or topic"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    service: EnhancedChunkedDocumentService = Depends(get_chunked_service)
):
    """List enterprise documents for the authenticated user.
    
    This endpoint returns only enterprise documents uploaded via the enterprise menu.
    Used for enterprise menu history display.
    
    🔒 SECURITY: Uses authenticated user_id from JWT token to prevent data spoofing.
    """
    try:
        # 🔒 SECURITY: Get authenticated user_id from JWT token (prevents spoofing)
        user_id = get_secure_user_id(request)
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Authentication required - no valid user_id in token"
            )
        
        logger.info(f"🏢 Fetching enterprise documents for authenticated user_id={user_id}, entity_id={entity_id}")
        
        # Get enterprise documents only using new service method
        documents, total = await service.list_enterprise_documents_for_device(
            user_id=user_id,
            page=page,
            per_page=per_page,
            search_query=search,
            entity_id=entity_id
        )
        
        total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0
        
        # Convert to response format
        document_responses = []
        for doc in documents:
            # Handle both dict and object formats returned by service
            if isinstance(doc, dict):
                file_url = doc.get('fileUrl')
                # URL generation disabled - not needed for listing, generated on-demand when downloading
                # if not file_url:
                #     file_url = _generate_download_url(
                #         doc.get('document_id', doc.get('_id', '')), 
                #         doc.get('user_id', user_id), 
                #         doc.get('file_type', '.pdf'),
                #         doc.get('topic_or_filename', 'document')
                #     )
                
                created_at = doc.get('created_at')
                updated_at = doc.get('updated_at')
                created_at_str = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
                updated_at_str = updated_at.isoformat() if isinstance(updated_at, datetime) else str(updated_at)
                
                # Format date in human readable IST format for UI
                utc_date_formatted = ""
                if created_at:
                    # Convert UTC to IST (UTC+5:30)
                    ist_time = created_at + timedelta(hours=5, minutes=30)
                    utc_date_formatted = ist_time.strftime("%d %b %Y, %I:%M %p IST")
                
                # Get entity information
                entity_id = doc.get('entity_id')
                entity_name = None
                if entity_id:
                    # Look up entity name from enterprise_entities collection
                    try:
                        from citra_mongo import MongoDBManager
                        mongo_manager = MongoDBManager()
                        mongo_client = mongo_manager.get_async_client()
                        entities_coll = mongo_client[mongo_manager.database_name]["enterprise_entities"]
                        entity_doc = await entities_coll.find_one(
                            {"entity_id": entity_id, "user_id": user_id},
                            {"entity_name": 1}
                        )
                        if entity_doc:
                            entity_name = entity_doc.get("entity_name")
                    except Exception as e:
                        logger.warning(f"Failed to lookup entity name for {entity_id}: {e}")
                
                # Handle KG processing status
                kg_processed = doc.get('kg_processed', False)
                kg_processed_at = doc.get('kg_processed_at')
                kg_processed_at_str = kg_processed_at.isoformat() if kg_processed_at and isinstance(kg_processed_at, datetime) else None
                
                document_responses.append(DocumentMetadataResponse(
                    document_id=doc.get('document_id', doc.get('_id', '')),
                    file_type=doc.get('file_type', ''),
                    total_pages=doc.get('total_pages', 0),
                    total_chunks=doc.get('total_chunks', 0),
                    chunk_size=doc.get('chunk_size', 0),
                    processing_status=doc.get('processing_status', 'completed'),
                    created_at=created_at_str,
                    updated_at=updated_at_str,
                    topic_or_filename=doc.get('topic_or_filename', None),
                    file_size=doc.get('file_size', 0),
                    fileUrl=file_url,
                    is_enterprise=True,  # Enterprise documents endpoint
                    utc_date=utc_date_formatted,
                    entity_id=entity_id,
                    entity_name=entity_name,
                    kg_processed=kg_processed,
                    kg_processed_at=kg_processed_at_str
                ))
            else:
                # Handle object format
                file_url = getattr(doc, 'fileUrl', None)
                # URL generation disabled - not needed for listing, generated on-demand when downloading
                # if not file_url:
                #     file_url = _generate_download_url(
                #         getattr(doc, 'document_id', ''), 
                #         getattr(doc, 'user_id', user_id), 
                #         getattr(doc, 'file_type', '.pdf'),
                #         getattr(doc, 'topic_or_filename', 'document')
                #     )
                
                created_at = getattr(doc, 'created_at', None)
                updated_at = getattr(doc, 'updated_at', None)
                created_at_str = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
                updated_at_str = updated_at.isoformat() if isinstance(updated_at, datetime) else str(updated_at)
                
                # Handle KG processing status
                kg_processed = getattr(doc, 'kg_processed', False)
                kg_processed_at = getattr(doc, 'kg_processed_at', None)
                kg_processed_at_str = kg_processed_at.isoformat() if kg_processed_at and isinstance(kg_processed_at, datetime) else None
                
                document_responses.append(DocumentMetadataResponse(
                    document_id=getattr(doc, 'document_id', ''),
                    file_type=getattr(doc, 'file_type', ''),
                    total_pages=getattr(doc, 'total_pages', 0),
                    total_chunks=getattr(doc, 'total_chunks', 0),
                    chunk_size=getattr(doc, 'chunk_size', 0),
                    processing_status=getattr(doc, 'processing_status', 'completed'),
                    created_at=created_at_str,
                    updated_at=updated_at_str,
                    topic_or_filename=getattr(doc, 'topic_or_filename', None),
                    file_size=getattr(doc, 'file_size', 0),
                    fileUrl=file_url,
                    is_enterprise=True,  # Enterprise documents endpoint
                    kg_processed=kg_processed,
                    kg_processed_at=kg_processed_at_str
                ))
        
        return DocumentListResponse(
            documents=document_responses,
            pagination={
                "current_page": page,
                "per_page": per_page,
                "total_documents": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
                "next_page": page + 1 if page < total_pages else None,
                "prev_page": page - 1 if page > 1 else None
            }
        )
            
    except Exception as e:
        logger.error(f"❌ Error listing enterprise documents: {e}")
        # Return empty response instead of raising exception to prevent UI crashes
        return DocumentListResponse(
            documents=[],
            pagination={
                "current_page": page,
                "per_page": per_page,
                "total_documents": 0,
                "total_pages": 0,
                "has_next": False,
                "has_prev": False,
                "next_page": None,
                "prev_page": None
            }
        )

@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    request: Request,
    service: EnhancedChunkedDocumentService = Depends(get_chunked_service)
):
    """Delete a document and all its chunks (authenticated endpoint)"""
    try:
        # 🔒 SECURITY: Get authenticated user_id from JWT token (prevents unauthorized deletion)
        user_id = get_secure_user_id(request)
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Authentication required - no valid user_id in token"
            )
        
        logger.info(f"🗑️ Processing delete request for document {document_id} by authenticated user: {user_id}")
        
        # Verify the document belongs to the authenticated user before deletion
        metadata = await service.get_document_metadata(document_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="Document not found")
        
        if metadata.user_id != user_id:
            logger.warning(f"🚫 Unauthorized delete attempt: user {user_id} tried to delete document {document_id} owned by {metadata.user_id}")
            raise HTTPException(status_code=403, detail="Forbidden - document belongs to different user")
        
        success = await service.delete_document(document_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Document not found or already deleted")
        
        logger.info(f"🗑️ ✅ Document {document_id} successfully deleted by user {user_id}")
        return {"message": "Document deleted successfully", "document_id": document_id}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# =================== END COMPATIBILITY ENDPOINT ===================

@router.get("/chunk/{vector_id}")
async def get_chunk_by_vector_id(
    vector_id: str,
    request: Request,
    service: EnhancedChunkedDocumentService = Depends(get_chunked_service)
):
    """Get chunk content by Milvus vector ID (authenticated endpoint)
    
    This endpoint retrieves a specific chunk using its Milvus vector ID,
    which is used in CHUNK:: citations. Returns the chunk text and metadata.
    """
    try:
        # 🔒 SECURITY: Get authenticated user_id from JWT token
        user_id = get_secure_user_id(request)
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Authentication required - no valid user_id in token"
            )
        
        logger.info(f"📄 Fetching chunk {vector_id} for authenticated user: {user_id}")
        
        # Retrieve chunk from Milvus using vector ID
        chunk_data = await service.get_chunk_by_vector_id(vector_id, user_id)
        
        if not chunk_data:
            logger.warning(f"🚫 Chunk not found: {vector_id} for user {user_id}")
            raise HTTPException(
                status_code=404, 
                detail=f"Chunk with vector ID {vector_id} not found or not accessible"
            )
        
        logger.info(f"📄 ✅ Successfully retrieved chunk {vector_id} for user {user_id}")
        return {
            "vector_id": chunk_data.get("vector_id"),
            "text": chunk_data.get("text"),
            "document_id": chunk_data.get("document_id"),
            "topic": chunk_data.get("topic"),
            "filename": chunk_data.get("filename"),
            "page_number": chunk_data.get("page_number"),
            "paragraph_number": chunk_data.get("paragraph_number"),
            "chunk_index": chunk_data.get("chunk_index"),
            "file_type": chunk_data.get("file_type"),
            "metadata": chunk_data.get("metadata", {})
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching chunk {vector_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

