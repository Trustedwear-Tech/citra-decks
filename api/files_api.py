# ============================  Files API  =============================
# Purpose: API endpoints for unified file management
# Features: List/search files, complete deletion from all services
# ----------------------------------------------------------------------------------------

from fastapi import APIRouter, HTTPException, Query, Request, status
from typing import Optional, List
from services.files_service import FilesService
from citra_auth import get_secure_user_id
from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
# Aliased: the DELETE /files/{file_id} route handler below is also named
# delete_file, and an unaliased import is shadowed by it — the S3 cleanup then
# calls the route (which wants a `request` arg), fails with a TypeError, and
# every delete silently orphans its S3 object while reporting success=false.
from bucket import delete_file as delete_file_from_s3
from config.milvus_config import get_milvus_client, get_collection_name
import os
import logging

router = APIRouter(prefix="/api/v2", tags=["Files"])
logger = logging.getLogger(__name__)


@router.get("/files")
async def list_files(
    request: Request,
    folder_id: Optional[str] = Query(None, description="Filter by folder ID"),
    entity_id: Optional[str] = Query(None, description="Filter by enterprise entity ID"),
    file_type: Optional[str] = Query(None, description="Filter by type: document|audio|video|image|note"),
    filename: Optional[str] = Query(None, description="Search by filename (case-insensitive)"),
    limit: int = Query(50, le=100, description="Number of results (max 100)"),
    offset: int = Query(0, ge=0, description="Pagination offset")
):
    """
    List or search user files based on folder/entity filters.
    
    **Features:**
    - Secured with JWT authentication
    - Returns files owned by authenticated user
    - Supports filtering by folder, entity, file type, filename
    - Case-insensitive filename search
    - Pagination support
    
    **Returns:**
    - total: Total count of matching files
    - files: Array of file metadata objects
    - limit: Results per page
    - offset: Current offset
    """
    try:
        # Extract secure, authenticated user_id from JWT token
        user_id = get_secure_user_id(request)
        
        mongo_client = get_async_mongo_client()
        registry_service = FilesService(mongo_client, MONGODB_DATABASE)
        
        # Build filters
        filters = {"user_id": user_id}
        
        if folder_id:
            filters["folder_id"] = folder_id
        
        if entity_id:
            filters["entity_id"] = entity_id
            filters["is_enterprise"] = True
        
        if file_type:
            valid_types = ["document", "audio", "video", "image", "note"]
            if file_type not in valid_types:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid file_type: {file_type}. Must be one of: {', '.join(valid_types)}"
                )
            filters["file_type_category"] = file_type
        
        if filename:
            # Case-insensitive filename search
            filters["filename"] = {"$regex": filename, "$options": "i"}
        
        # Get files
        files = await registry_service.list_user_files(
            filters=filters,
            limit=limit,
            offset=offset
        )
        
        # Get total count for pagination
        total = await registry_service.count_files(filters)
        
        logger.info(f"📋 Listed {len(files)} files for user {user_id} (total: {total})")
        
        return {
            "success": True,
            "total": total,
            "limit": limit,
            "offset": offset,
            "files": files
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to list files: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list files: {str(e)}"
        )


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
    request: Request
):
    """
    Delete file completely from everywhere:
    - AWS S3
    - Milvus vector database
    - MongoDB (all related collections)
    - File registry
    
    **Features:**
    - Uses registry to get all resource IDs in ONE query
    - Secured with JWT - only file owner can delete
    - Comprehensive deletion from all services
    - Detailed deletion report
    
    **Returns:**
    - success: Boolean indicating overall success
    - message: Success/error message
    - details: Breakdown of what was deleted from each service
    """
    try:
        # Extract secure, authenticated user_id from JWT token
        user_id = get_secure_user_id(request)
        
        mongo_client = get_async_mongo_client()
        registry_service = FilesService(mongo_client, MONGODB_DATABASE)
        
        # Get file resources from registry (ONE query gets everything)
        resources = await registry_service.get_file_resources(file_id, user_id)
        
        if not resources:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or you don't have permission to delete it"
            )
        
        deletion_results = {
            "file_id": file_id,
            "filename": resources.get("filename"),
            "deleted_resources": []
        }
        
        # 1. Delete from Milvus using stored primary_keys
        if resources.get("milvus_primary_keys") and len(resources["milvus_primary_keys"]) > 0:
            try:
                milvus_client = get_milvus_client()
                collection_name = get_collection_name()
                
                # Delete vectors by primary keys
                milvus_client.delete(
                    collection_name=collection_name,
                    ids=resources["milvus_primary_keys"]
                )
                
                deletion_results["deleted_resources"].append({
                    "service": "milvus",
                    "collection": collection_name,
                    "count": len(resources["milvus_primary_keys"])
                })
                logger.info(f"✅ Deleted {len(resources['milvus_primary_keys'])} vectors from Milvus for {file_id}")
                
            except Exception as e:
                logger.error(f"❌ Milvus deletion failed for {file_id}: {e}")
                deletion_results["errors"] = deletion_results.get("errors", [])
                deletion_results["errors"].append(f"Milvus deletion failed: {str(e)}")
        
        # 2. Delete from S3
        if resources.get("s3_url"):
            try:
                s3_url = resources["s3_url"]
                
                # Extract S3 key from URL
                # URL format: https://<bucket>.s3.<region>.amazonaws.com/dev/files/...
                if ".amazonaws.com/" in s3_url:
                    s3_key = s3_url.split(".amazonaws.com/")[-1]
                elif "s3://" in s3_url:
                    s3_key = s3_url.split("s3://", 1)[-1].split("/", 1)[-1]
                else:
                    s3_key = s3_url  # Fallback
                
                if s3_key:
                    s3_deleted = delete_file_from_s3(s3_key)
                    
                    if s3_deleted:
                        deletion_results["deleted_resources"].append({
                            "service": "s3",
                            "s3_key": s3_key
                        })
                        logger.info(f"✅ Deleted S3 object {s3_key} for {file_id}")
                    else:
                        logger.warning(f"⚠️ S3 deletion failed for {file_id}")
                        
            except Exception as e:
                # Log S3 errors but don't fail the deletion process
                logger.warning(f"⚠️ S3 deletion failed for {file_id} (continuing): {e}")
                deletion_results["errors"] = deletion_results.get("errors", [])
                deletion_results["errors"].append(f"S3 deletion failed (non-critical): {str(e)}")
        
        # 3. Delete from MongoDB collections
        mongodb_refs = resources.get("mongodb_refs", {})
        db = mongo_client[MONGODB_DATABASE]
        structured_cleanup_doc_ids = set()
        
        # Delete from document_chunked
        if mongodb_refs.get("document_chunked_ids"):
            for doc_id in mongodb_refs["document_chunked_ids"]:
                structured_cleanup_doc_ids.add(doc_id)
                result = await db["document_chunked"].delete_many({"document_id": doc_id})
                if result.deleted_count > 0:
                    deletion_results["deleted_resources"].append({
                        "service": "mongodb",
                        "collection": "document_chunked",
                        "count": result.deleted_count
                    })
                    logger.info(f"✅ Deleted {result.deleted_count} chunks from document_chunked for {file_id}")
        
        # Delete from milvus_chunks mapping
        if mongodb_refs.get("milvus_chunks_id"):
            result = await db["milvus_chunks"].delete_one({"_id": mongodb_refs["milvus_chunks_id"]})
            if result.deleted_count > 0:
                deletion_results["deleted_resources"].append({
                    "service": "mongodb",
                    "collection": "milvus_chunks",
                    "count": result.deleted_count
                })
                logger.info(f"✅ Deleted milvus_chunks mapping for {file_id}")
        
        # Delete from transcripts (audio)
        if mongodb_refs.get("transcripts_id"):
            result = await db["transcripts"].delete_one({"_id": mongodb_refs["transcripts_id"]})
            if result.deleted_count > 0:
                deletion_results["deleted_resources"].append({
                    "service": "mongodb",
                    "collection": "transcripts",
                    "count": result.deleted_count
                })
                logger.info(f"✅ Deleted from transcripts for {file_id}")
        
        # Delete from video_transcripts
        if mongodb_refs.get("video_transcripts_id"):
            result = await db["video_transcripts"].delete_one({"_id": mongodb_refs["video_transcripts_id"]})
            if result.deleted_count > 0:
                deletion_results["deleted_resources"].append({
                    "service": "mongodb",
                    "collection": "video_transcripts",
                    "count": result.deleted_count
                })
                logger.info(f"✅ Deleted from video_transcripts for {file_id}")

        # Delete structured file-upload artifacts (Excel/CSV/JSON row records, schema cache, Redis cache)
        if structured_cleanup_doc_ids:
            try:
                from document_manager import _delete_document_structured_metadata

                structured_deleted_total = 0
                for doc_id in structured_cleanup_doc_ids:
                    cleanup_result = await _delete_document_structured_metadata(doc_id, user_id)
                    if cleanup_result.get("success"):
                        structured_deleted_total += cleanup_result.get("deleted_count", 0)
                    else:
                        deletion_results.setdefault("errors", []).append(
                            f"Structured cleanup failed for {doc_id}"
                        )

                deletion_results["deleted_resources"].append({
                    "service": "structured_cleanup",
                    "documents": len(structured_cleanup_doc_ids),
                    "count": structured_deleted_total
                })
                logger.info(
                    f"✅ Structured cleanup completed for {len(structured_cleanup_doc_ids)} document(s) while deleting {file_id}"
                )
            except Exception as e:
                logger.error(f"❌ Structured cleanup failed for {file_id}: {e}")
                deletion_results.setdefault("errors", []).append(
                    f"Structured cleanup failed: {str(e)}"
                )
        
        # 4. Delete from file registry
        registry_deleted = await registry_service.delete_file(file_id, user_id)
        if registry_deleted:
            deletion_results["deleted_resources"].append({
                "service": "file_registry",
                "count": 1
            })
            logger.info(f"✅ Deleted from file_registry for {file_id}")
        
        # Check if we had any errors
        has_errors = "errors" in deletion_results
        
        return {
            "success": not has_errors,
            "message": "File deleted successfully from all services" if not has_errors else "File deleted with some errors",
            "details": deletion_results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file: {str(e)}"
        )


@router.get("/files/stats")
async def get_storage_stats(
    request: Request,
    entity_id: Optional[str] = Query(None, description="Filter by enterprise entity ID")
):
    """
    Get storage statistics for authenticated user.
    
    **Returns:**
    - Total files and storage size
    - Breakdown by file type (document, audio, video, image, note)
    - Sizes in bytes, MB, and GB
    """
    try:
        # Extract secure, authenticated user_id from JWT token
        user_id = get_secure_user_id(request)
        
        mongo_client = get_async_mongo_client()
        registry_service = FilesService(mongo_client, MONGODB_DATABASE)
        
        stats = await registry_service.get_storage_stats(user_id, entity_id)
        
        logger.info(f"📊 Storage stats for user {user_id}: {stats.get('total_files')} files, {stats.get('total_size_mb')}MB")
        
        return {
            "success": True,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get storage stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get storage stats: {str(e)}"
        )
