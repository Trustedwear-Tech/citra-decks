"""
Folder Management API for Citra AI Service
Provides endpoints for creating, reading, updating, and deleting folders
for organizing documents and content within the Citra AI system.
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status, Query, Body, Request
from fastapi.responses import JSONResponse
import logging
import pymongo
from datetime import datetime
import uuid
from pydantic import BaseModel, Field
from citra_auth import get_secure_user_id

# Import MongoDB utilities
from CRUD_utils import get_mongo_client, MONGODB_DATABASE

# Set up logging
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter()

# Pydantic models for request/response validation
class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Folder name")
    description: Optional[str] = Field(None, max_length=500, description="Folder description")
    color: Optional[str] = Field("#6b7280", description="Folder color in hex format")

class FolderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Folder name")
    description: Optional[str] = Field(None, max_length=500, description="Folder description")
    color: Optional[str] = Field(None, description="Folder color in hex format")

class FolderResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    color: str
    document_count: int
    created_at: str
    updated_at: str
    is_system: bool
    is_default: bool

# System folders - empty array as users must create their own vaults
# The "My First Vault" is auto-created on first login for new users
SYSTEM_FOLDERS = []

def get_folders_collection():
    """Get the folders collection from MongoDB"""
    try:
        mongo_client = get_mongo_client()
        db = mongo_client[MONGODB_DATABASE]
        return db.folders
    except Exception as e:
        logger.error(f"Failed to get folders collection: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database connection failed"
        )

@router.get("/api/folders/list")
async def list_folders(
    request: Request,
    team_id: Optional[str] = Query(None, description="Team ID to filter folders by workspace"),
    all_workspaces: bool = Query(False, description="If true, returns all folders for the user regardless of workspace")
):
    """
    List all folders for a specific device.
    - If all_workspaces is True: returns ALL folders for user (personal + all teams)
    - If team_id is None: returns personal workspace folders
    - If team_id is set: returns folders for that specific workspace
    """
    try:
        user_id = get_secure_user_id(request)
        logger.info(f"📁 Listing folders for device: {user_id}, team_id: {team_id}, all_workspaces: {all_workspaces}")

        folders_collection = get_folders_collection()

        # Personal-SA-only visibility. Folders/vaults are personal-output
        # collections, scoped to the user's Personal SA (same lifecycle as
        # presentations / printables / reports / diagrams). Legacy folders
        # (no owner_id) are auto-migrated to the caller's Personal SA on
        # first list.
        _personal_sa_id = getattr(request.state, "personal_sa_id", "") or ""
        _owner_org_id = getattr(request.state, "org_id", "") or ""

        if not _personal_sa_id:
            logger.warning(
                "[folders] reject list: personal_sa_id missing for user=%s org=%s",
                user_id, _owner_org_id,
            )
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "personal_sa_id_missing",
                    "message": (
                        "Cannot list folders: your Personal Service Account is not "
                        "provisioned. Sign out + sign in to refresh, or contact "
                        "your admin to run 'Fix Service Accounts' on your user record."
                    ),
                },
            )

        # One-shot auto-migration of legacy folders this user owns.
        # Idempotent — once owner_id is set, the clause matches nothing
        # on subsequent calls. Restricted to folders the caller wrote
        # (user_id == caller) so we never adopt someone else's legacy folder.
        legacy_q = {
            "user_id": user_id,
            "deleted": {"$ne": True},
            "$or": [
                {"owner_id": {"$exists": False}},
                {"owner_id": None},
                {"owner_id": ""},
            ],
        }
        mig = folders_collection.update_many(legacy_q, {"$set": {
            "owner_type": "service_account",
            "owner_id": _personal_sa_id,
            "org_id": _owner_org_id or None,
        }})
        if getattr(mig, "modified_count", 0):
            logger.info(
                "[folders] auto-migrated %d legacy folders to personal_sa=%s for user=%s",
                mig.modified_count, _personal_sa_id, user_id,
            )

        query = {
            "owner_type": "service_account",
            "owner_id": _personal_sa_id,
            "deleted": {"$ne": True},
            # Internal/system folders (e.g. the chat report vault — transient
            # grounding storage for chat-built presentations/reports) are
            # never shown in the user's folder picker.
            "internal": {"$ne": True},
        }

        # Workspace scoping (independent of ownership). Only applies when
        # the caller did NOT ask for all_workspaces.
        if not all_workspaces:
            if team_id:
                query["team_id"] = team_id
            else:
                # Personal workspace: either no team_id field or team_id is null
                query["$or"] = [
                    {"team_id": {"$exists": False}},
                    {"team_id": None},
                ]

        # Get user-created folders from database
        user_folders_cursor = folders_collection.find(query).sort("created_at", 1)
        
        user_folders = list(user_folders_cursor)
        
        # Convert ObjectId to string (remove document counts for faster loading)
        processed_user_folders = []
        for folder in user_folders:
            folder_data = {
                "id": str(folder["_id"]),
                "name": folder["name"],
                "description": folder.get("description", ""),
                "color": folder.get("color", "#6b7280"),
                "created_at": folder["created_at"].isoformat() if isinstance(folder["created_at"], datetime) else folder["created_at"],
                "updated_at": folder["updated_at"].isoformat() if isinstance(folder["updated_at"], datetime) else folder["updated_at"],
                "is_system": False,
                "is_default": False
            }
            processed_user_folders.append(folder_data)
        
        # Add system folders (remove document counts for faster loading)
        system_folders_with_counts = []
        for sys_folder in SYSTEM_FOLDERS:
            folder_data = {
                **sys_folder,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            system_folders_with_counts.append(folder_data)
        
        # Combine system folders first, then user folders
        all_folders = system_folders_with_counts + processed_user_folders
        
        logger.info(f"📁 Found {len(system_folders_with_counts)} system folders and {len(processed_user_folders)} user folders")
        
        return {
            "folders": all_folders,
            "total_count": len(all_folders),
            "system_folders_count": len(system_folders_with_counts),
            "user_folders_count": len(processed_user_folders)
        }
        
    except Exception as e:
        logger.error(f"Failed to list folders for device {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve folders: {str(e)}"
        )

@router.post("/api/folders/create")
async def create_folder(
    request: Request,
    team_id: Optional[str] = Query(None, description="Team ID to associate folder with workspace"),
    folder_data: FolderCreate = Body(..., description="Folder creation data")
):
    """
    Create a new folder for a specific device and workspace.
    - If team_id is None: creates folder in personal workspace
    - If team_id is set: creates folder in that specific workspace
    """
    try:
        user_id = get_secure_user_id(request)
        logger.info(f"📁 Creating folder '{folder_data.name}' for device: {user_id}, team_id: {team_id}")

        # Personal-SA ownership stamp: folders/vaults are personal-output
        # collections (same lifecycle bucket as presentations, printables,
        # reports, diagrams). They live on the user's Personal SA and are
        # cascade-deleted with the user. Team sharing is handled separately
        # via the vault_shares collection. Reject if personal_sa_id is
        # missing; admin must run 'Fix Service Accounts' on the user record
        # first.
        _personal_sa_id = getattr(request.state, "personal_sa_id", "") or ""
        _owner_org_id = getattr(request.state, "org_id", "") or ""
        if not _personal_sa_id:
            logger.warning(
                "[folders] reject create: personal_sa_id missing for user=%s org=%s",
                user_id, _owner_org_id,
            )
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "personal_sa_id_missing",
                    "message": (
                        "Cannot create folder: your Personal Service Account is not "
                        "provisioned. Sign out + sign in to refresh, or contact "
                        "your admin to run 'Fix Service Accounts' on your user record."
                    ),
                },
            )

        # Check if folder name is reserved
        reserved_names = [folder["name"].lower() for folder in SYSTEM_FOLDERS]
        if folder_data.name.lower() in reserved_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Folder name '{folder_data.name}' is reserved. Please choose a different name."
            )

        folders_collection = get_folders_collection()
        
        # Build query for duplicate check - include team_id
        duplicate_query = {
            "user_id": user_id,
            "name": {"$regex": f"^{folder_data.name}$", "$options": "i"},
            "deleted": {"$ne": True}
        }
        
        # Add team_id to duplicate check
        if team_id:
            duplicate_query["team_id"] = team_id
        else:
            duplicate_query["$or"] = [
                {"team_id": {"$exists": False}},
                {"team_id": None}
            ]
        
        # Check if folder with same name already exists in this workspace
        existing_folder = folders_collection.find_one(duplicate_query)
        
        if existing_folder:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Folder with name '{folder_data.name}' already exists in this workspace"
            )
        
        # Create new folder document
        folder_id = str(uuid.uuid4())
        current_time = datetime.now()
        
        new_folder = {
            "_id": folder_id,
            "user_id": user_id,            # legacy field — kept for audit
            "team_id": team_id,            # None for personal workspace, team id for shared workspaces
            "owner_type": "service_account",
            "owner_id": _personal_sa_id,   # the user's Personal SA — cascade-deleted with user
            "org_id": _owner_org_id or None,
            "name": folder_data.name,
            "description": folder_data.description or "",
            "color": folder_data.color or "#6b7280",
            "created_at": current_time,
            "updated_at": current_time,
            "deleted": False
        }
        
        # Insert folder into database
        result = folders_collection.insert_one(new_folder)
        
        if result.inserted_id:
            logger.info(f"📁 Successfully created folder '{folder_data.name}' with ID: {folder_id}")
            
            # Return the created folder
            return {
                "id": folder_id,
                "name": folder_data.name,
                "description": folder_data.description or "",
                "color": folder_data.color or "#6b7280",
                "document_count": 0,
                "created_at": current_time.isoformat(),
                "updated_at": current_time.isoformat(),
                "is_system": False,
                "is_default": False
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create folder"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create folder for device {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create folder: {str(e)}"
        )

@router.put("/api/folders/update/{folder_id}")
async def update_folder(
    folder_id: str,
    request: Request,
    folder_data: FolderUpdate = Body(..., description="Folder update data")
):
    """
    Update an existing folder for a specific device.
    System folders cannot be updated.
    """
    try:
        user_id = get_secure_user_id(request)
        logger.info(f"📁 Updating folder {folder_id} for device: {user_id}")
        
        # Check if it's a system folder
        system_folder_ids = [folder["id"] for folder in SYSTEM_FOLDERS]
        if folder_id in system_folder_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="System folders cannot be updated"
            )
        
        folders_collection = get_folders_collection()
        
        # Check if folder exists and belongs to the device
        existing_folder = folders_collection.find_one({
            "_id": folder_id,
            "user_id": user_id,
            "deleted": {"$ne": True}
        })
        
        if not existing_folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found"
            )
        
        # Prepare update data
        update_data = {"updated_at": datetime.now()}
        
        if folder_data.name is not None:
            # Check if new name conflicts with reserved names
            reserved_names = [folder["name"].lower() for folder in SYSTEM_FOLDERS]
            if folder_data.name.lower() in reserved_names:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Folder name '{folder_data.name}' is reserved"
                )
            
            # Check if new name conflicts with existing folders
            name_conflict = folders_collection.find_one({
                "user_id": user_id,
                "name": {"$regex": f"^{folder_data.name}$", "$options": "i"},
                "deleted": {"$ne": True},
                "_id": {"$ne": folder_id}
            })
            
            if name_conflict:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Folder with name '{folder_data.name}' already exists"
                )
            
            update_data["name"] = folder_data.name
        
        if folder_data.description is not None:
            update_data["description"] = folder_data.description
            
        if folder_data.color is not None:
            update_data["color"] = folder_data.color
        
        # Update folder in database
        result = folders_collection.update_one(
            {"_id": folder_id, "user_id": user_id},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            # Get updated folder
            updated_folder = folders_collection.find_one({"_id": folder_id})
            
            logger.info(f"📁 Successfully updated folder {folder_id}")
            
            return {
                "id": folder_id,
                "name": updated_folder["name"],
                "description": updated_folder.get("description", ""),
                "color": updated_folder.get("color", "#6b7280"),
                "created_at": updated_folder["created_at"].isoformat(),
                "updated_at": updated_folder["updated_at"].isoformat(),
                "is_system": False,
                "is_default": False
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update folder"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update folder {folder_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update folder: {str(e)}"
        )

@router.delete("/api/folders/delete/{folder_id}")
@router.delete("/api/folders/{folder_id}")
async def delete_folder(
    folder_id: str,
    request: Request,
    move_documents_to: str = Query("documents", description="Folder ID to move documents to before deletion")
):
    """
    Delete a folder for a specific device.
    System folders cannot be deleted.
    Documents in the folder will be moved to the specified folder (default: 'documents' folder).
    """
    try:
        user_id = get_secure_user_id(request)
        logger.info(f"📁 Deleting folder {folder_id} for device: {user_id}")
        
        # Check if it's a system folder
        system_folder_ids = [folder["id"] for folder in SYSTEM_FOLDERS]
        if folder_id in system_folder_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="System folders cannot be deleted"
            )
        
        folders_collection = get_folders_collection()
        
        # Check if folder exists and belongs to the device
        existing_folder = folders_collection.find_one({
            "_id": folder_id,
            "user_id": user_id,
            "deleted": {"$ne": True}
        })
        
        if not existing_folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found"
            )
        
        # Get all related documents and transcripts before deletion for cascade cleanup
        logger.info(f"🔍 Finding related documents and transcripts for folder {folder_id}")

        mongo_client = get_mongo_client()
        db = mongo_client[MONGODB_DATABASE]

        # Get related documents
        documents_collection = db["document_chunked"]
        related_docs = list(documents_collection.find({
            "user_id": user_id,
            "folder_id": folder_id
        }))

        # Get related transcripts (audio and video)
        transcripts_collection = db["transcripts"]
        related_transcripts = list(transcripts_collection.find({
            "user_id": user_id,
            "folder_id": folder_id
        }))

        # Get related video transcripts
        video_transcripts_collection = db["video_transcripts"]
        related_video_transcripts = list(video_transcripts_collection.find({
            "user_id": user_id,
            "folder_id": folder_id
        }))

        logger.info(f"📊 Found {len(related_docs)} documents, {len(related_transcripts)} audio transcripts, {len(related_video_transcripts)} video transcripts to delete")

        # Delete associated files from S3
        await _delete_s3_files_cascade(user_id, folder_id, related_docs, related_transcripts, related_video_transcripts)

        # Delete vectors from Milvus
        await _delete_milvus_vectors_cascade(related_docs, related_transcripts, related_video_transcripts)

        # Delete all related data from MongoDB
        _delete_mongodb_related_data_cascade(db, user_id, folder_id, related_docs, related_transcripts, related_video_transcripts)

        # Finally delete the folder itself (hard delete since we're doing cascade)
        result = folders_collection.delete_one({
            "_id": folder_id,
            "user_id": user_id
        })

        if result.deleted_count > 0:
            logger.info(f"📁 Successfully cascade deleted folder {folder_id} and all associated data")
            return {"message": f"Folder '{existing_folder['name']}' and all associated files deleted successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete folder"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete folder {folder_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete folder: {str(e)}"
        )

@router.get("/api/folders/{folder_id}")
async def get_folder(
    folder_id: str,
    request: Request
):
    """
    Get details of a specific folder.
    Works for both system folders and user-created folders.
    """
    try:
        user_id = get_secure_user_id(request)
        logger.info(f"📁 Getting folder {folder_id} for device: {user_id}")
        
        # Check if it's a system folder
        for sys_folder in SYSTEM_FOLDERS:
            if sys_folder["id"] == folder_id:
                return {
                    **sys_folder,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
        
        # Look for user-created folder
        folders_collection = get_folders_collection()
        folder = folders_collection.find_one({
            "_id": folder_id,
            "user_id": user_id,
            "deleted": {"$ne": True}
        })
        
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found"
            )
        
        return {
            "id": folder_id,
            "name": folder["name"],
            "description": folder.get("description", ""),
            "color": folder.get("color", "#6b7280"),
            "created_at": folder["created_at"].isoformat(),
            "updated_at": folder["updated_at"].isoformat(),
            "is_system": False,
            "is_default": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get folder {folder_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve folder: {str(e)}"
        )

@router.get("/api/folders/stats")
async def get_folder_stats(request: Request):
    """
    Get basic folder statistics for the authenticated device (folder counts only for performance).
    Document counts have been removed to improve loading performance.
    """
    try:
        # Get authenticated user_id from JWT token
        user_id = get_secure_user_id(request)
        
        logger.info(f"📁 Getting folder statistics for authenticated device: {user_id}")
        
        folders_collection = get_folders_collection()
        
        # Count user folders
        user_folder_count = folders_collection.count_documents({
            "user_id": user_id,
            "deleted": {"$ne": True}
        })
        
        # Return basic stats without document counts for performance
        return {
            "total_folders": len(SYSTEM_FOLDERS) + user_folder_count,
            "system_folders": len(SYSTEM_FOLDERS),
            "user_folders": user_folder_count,
            "note": "Document counts removed for improved performance"
        }
        total_size = 0
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get folder stats for device {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve folder statistics: {str(e)}"
        )

# Cascade deletion helper functions

async def _delete_s3_files_cascade(user_id: str, folder_id: str, docs: list, transcripts: list, video_transcripts: list):
    """Delete related files from S3 using files_service for folder deletion"""
    try:
        from services.files_service import FilesService
        from bucket import delete_file
        from citra_mongo import get_async_mongo_client, MONGODB_DATABASE

        # Get files_service
        mongo_client = get_async_mongo_client()
        files_service = FilesService(mongo_client, MONGODB_DATABASE)

        # Collect all document/transcript IDs to delete
        file_ids_to_delete = set()

        # From documents
        for doc in docs:
            if "_id" in doc:
                file_ids_to_delete.add(doc["_id"])

        # From audio transcripts
        for transcript in transcripts:
            if "_id" in transcript:
                file_ids_to_delete.add(transcript["_id"])

        # From video transcripts
        for video_transcript in video_transcripts:
            if "_id" in video_transcript:
                file_ids_to_delete.add(video_transcript["_id"])

        # Delete files from S3 using files_service (single source of truth)
        deleted_count = 0
        for file_id in file_ids_to_delete:
            try:
                # Get S3 URL from files collection
                file_resources = await files_service.get_file_resources(file_id, user_id)
                
                if file_resources and file_resources.get("s3_url"):
                    s3_url = file_resources["s3_url"]
                    
                    # Extract S3 key from URL
                    if ".amazonaws.com/" in s3_url:
                        s3_key = s3_url.split(".amazonaws.com/")[-1]
                    elif "s3://" in s3_url:
                        s3_key = s3_url.split("s3://", 1)[-1].split("/", 1)[-1]
                    else:
                        s3_key = s3_url  # Fallback
                    
                    # Delete from S3
                    if delete_file(s3_key):
                        deleted_count += 1
                        logger.info(f"✅ Deleted S3 file: {s3_key}")
                    else:
                        logger.warning(f"⚠️ S3 delete failed for {s3_key}")
                    
                    # Delete from files registry
                    await files_service.delete_file(file_id, user_id)
                else:
                    logger.warning(f"⚠️ No S3 URL found for file {file_id}")
                    
            except Exception as e:
                # Log but don't fail - S3 might be unavailable
                logger.warning(f"S3 delete failed for {file_id} (continuing): {e}")
        
        logger.info(f"✅ Deleted {deleted_count} files from S3 for folder {folder_id}")

    except Exception as e:
        # Log S3 connection errors but don't fail folder deletion
        logger.warning(f"S3 Storage connection failed during folder cleanup (continuing): {e}")


async def _delete_milvus_vectors_cascade(docs: list, transcripts: list, video_transcripts: list):
    """Delete related vectors from Milvus for folder deletion"""
    try:
        import os
        from config.milvus_config import get_milvus_client, get_collection_name

        collection_name = get_collection_name()

        # Initialize Milvus client
        milvus_client = get_milvus_client()

        # Collect all document IDs to delete
        document_ids = []

        # From documents
        for doc in docs:
            if "document_id" in doc:
                document_ids.append(doc["document_id"])

        # From audio transcripts
        for transcript in transcripts:
            if "transcript_id" in transcript:
                document_ids.append(transcript["transcript_id"])

        # From video transcripts
        for video_transcript in video_transcripts:
            if "transcript_id" in video_transcript:
                document_ids.append(video_transcript["transcript_id"])

        # Delete vectors using filter expressions
        if document_ids:
            # Get user_id for filtering
            user_id = None
            if docs and docs[0].get("user_id"):
                user_id = docs[0]["user_id"]
            elif transcripts and transcripts[0].get("user_id"):
                user_id = transcripts[0]["user_id"]
            elif video_transcripts and video_transcripts[0].get("user_id"):
                user_id = video_transcripts[0]["user_id"]

            if user_id:
                # Delete each document's vectors using filter
                total_deleted = 0
                for doc_id in document_ids:
                    try:
                        filter_expr = f'document_id == "{doc_id}" and user_id == "{user_id}"'
                        result = milvus_client.delete(
                            collection_name=collection_name,
                            filter=filter_expr
                        )
                        delete_count = result.get("delete_count", 0)
                        total_deleted += delete_count
                        logger.info(f"Deleted {delete_count} vectors for document {doc_id}")
                    except Exception as e:
                        logger.warning(f"Failed to delete vectors for document {doc_id}: {e}")

                logger.info(f"Total vectors deleted from Milvus: {total_deleted}")

                # Delete KG embeddings from Milvus
                try:
                    from graph.embedding_service import KGEmbeddingService
                    kg_service = KGEmbeddingService()
                    total_kg_deleted = 0
                    for doc_id in document_ids:
                        try:
                            kg_deleted = await kg_service.delete_document_embeddings(
                                user_id=user_id,
                                document_id=doc_id
                            )
                            total_kg_deleted += (kg_deleted or 0)
                        except Exception as e:
                            logger.warning(f"Failed to delete KG embeddings for document {doc_id}: {e}")
                    if total_kg_deleted > 0:
                        logger.info(f"✅ Deleted {total_kg_deleted} KG embeddings from Milvus for folder cascade")
                except Exception as kg_err:
                    logger.warning(f"⚠️ KG embedding cleanup failed during folder cascade (non-blocking): {kg_err}")
            else:
                logger.warning("No user_id found, skipping Milvus deletion")

    except Exception as e:
        logger.error(f"Error deleting Milvus vectors for folder cascade: {e}")


def _delete_mongodb_related_data_cascade(db, user_id: str, folder_id: str, docs: list, transcripts: list, video_transcripts: list):
    """Delete related documents and transcripts from MongoDB for folder deletion"""
    try:
        # Delete document chunks
        doc_result = db.document_chunked.delete_many({
            "user_id": user_id,
            "folder_id": folder_id
        })
        logger.info(f"Deleted {doc_result.deleted_count} document chunks from folder {folder_id}")

        # Delete audio transcripts
        transcript_result = db.transcripts.delete_many({
            "user_id": user_id,
            "folder_id": folder_id
        })
        logger.info(f"Deleted {transcript_result.deleted_count} audio transcripts from folder {folder_id}")

        # Delete video transcripts
        video_result = db.video_transcripts.delete_many({
            "user_id": user_id,
            "folder_id": folder_id
        })
        logger.info(f"Deleted {video_result.deleted_count} video transcripts from folder {folder_id}")

        # Delete milvus_chunks entries for all document_ids in this folder
        document_ids = []
        for doc in docs:
            if "document_id" in doc:
                document_ids.append(doc["document_id"])
        for transcript in transcripts:
            if "transcript_id" in transcript:
                document_ids.append(transcript["transcript_id"])
        for video_transcript in video_transcripts:
            if "transcript_id" in video_transcript:
                document_ids.append(video_transcript["transcript_id"])

        if document_ids:
            milvus_chunks_result = db.milvus_chunks.delete_many({
                "document_id": {"$in": document_ids}
            })
            logger.info(f"Deleted {milvus_chunks_result.deleted_count} milvus_chunks entries from folder {folder_id}")

            # Delete structured_file_metadata — folder-level sweep
            try:
                connection_ids = [f"file_{doc_id}" for doc_id in document_ids if doc_id]
                meta_result = db.structured_file_metadata.delete_many({
                    "user_id": user_id,
                    "$or": [
                        {"folder_id": folder_id},
                        {"document_id": {"$in": document_ids}}
                    ]
                })
                if meta_result.deleted_count > 0:
                    logger.info(f"✅ Deleted {meta_result.deleted_count} structured_file_metadata entries from folder {folder_id}")
            except Exception as meta_err:
                logger.warning(f"⚠️ structured_file_metadata cleanup failed during folder cascade (non-blocking): {meta_err}")

            # Delete unstructured_file_metadata — folder-level sweep
            try:
                u_meta_result = db.unstructured_file_metadata.delete_many({
                    "user_id": user_id,
                    "$or": [
                        {"folder_id": folder_id},
                        {"document_id": {"$in": document_ids}}
                    ]
                })
                if u_meta_result.deleted_count > 0:
                    logger.info(f"✅ Deleted {u_meta_result.deleted_count} unstructured_file_metadata entries from folder {folder_id}")
            except Exception as u_meta_err:
                logger.warning(f"⚠️ unstructured_file_metadata cleanup failed during folder cascade (non-blocking): {u_meta_err}")

            # Invalidate structured bulk-fetch cache for all documents in this folder
            try:
                from citra_cache import get_cache_manager
                cache = get_cache_manager()
                from document_manager import clear_document_progress
                for doc_id in document_ids:
                    if doc_id:
                        cache.delete(f"structured_file_metadata:{user_id}:{doc_id}")
                        clear_document_progress(doc_id)
                logger.info(f"✅ Invalidated structured bulk-fetch cache for {len(document_ids)} document(s) in folder {folder_id}")
            except Exception as cache_err:
                logger.warning(f"⚠️ Bulk-fetch cache invalidation failed during folder cascade (non-blocking): {cache_err}")

    except Exception as e:
        logger.error(f"Error deleting MongoDB related data for folder cascade: {e}")
        raise
