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
