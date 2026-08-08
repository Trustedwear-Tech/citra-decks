"""
Sharing API Router for Citra AI Service

This module provides REST endpoints for managing resource sharing:
- Grant access to a resource
- Revoke access from a resource
- List users with access to a resource
- Get user's shared resources

All endpoints require JWT authentication.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, status, Request, Query
from pydantic import BaseModel, Field

from citra_auth import get_secure_user_id
from services.authorization_service import (
    get_authorization_service,
    RESOURCE_TYPES,
    PERMISSION_LEVELS
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sharing", tags=["sharing"])


# =========================================================================
# Migration Endpoints
# =========================================================================

@router.post("/migrate-legacy", response_model=dict)
async def migrate_legacy_shares(request: Request):
    """
    Migrate existing sharing data from legacy collections to centralized authorization.
    
    This migrates:
    - vault_shares -> resource_permissions
    - shared_with_me -> resource_permissions
    
    Safe to run multiple times (idempotent).
    
    Requires admin privileges (for now just authenticated).
    """
    user_id = get_secure_user_id(request)
    
    logger.info(f"🔄 Migration requested by user: {user_id}")
    
    try:
        from services.sharing_migration_service import get_migration_service
        
        migration_service = get_migration_service()
        results = await migration_service.migrate_all()
        
        return {
            "success": True,
            "message": "Migration completed",
            "results": results
        }
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Migration failed: {str(e)}"
        )


# =========================================================================
# Pydantic Models
# =========================================================================

class ShareResourceRequest(BaseModel):
    """Request to share a resource with a user or team."""
    resource_id: str = Field(..., description="ID of the resource to share")
    resource_type: str = Field(..., description="Type of resource (vault, presentation, etc.)")
    target_id: str = Field(..., description="User ID or Team ID to share with")
    target_type: str = Field(default="user", description="Type of target: 'user' or 'team'")
    permission: str = Field(default="read", description="Permission level: read, write, or admin")
    team_id: Optional[str] = Field(default=None, description="Workspace/team ID (context)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "resource_id": "pres_123abc",
                "resource_type": "presentation",
                "target_id": "user_456def",
                "target_type": "user",
                "permission": "read",
                "team_id": "team_789ghi"
            }
        }


class RevokeAccessRequest(BaseModel):
    """Request to revoke a user or team's access to a resource."""
    resource_id: str = Field(..., description="ID of the resource")
    resource_type: str = Field(..., description="Type of resource")
    target_id: str = Field(..., description="User ID or Team ID to revoke access from")
    target_type: str = Field(default="user", description="Type of target: 'user' or 'team'")


class BulkShareRequest(BaseModel):
    """Request to share a resource with multiple users."""
    resource_id: str = Field(..., description="ID of the resource to share")
    resource_type: str = Field(..., description="Type of resource")
    target_user_ids: List[str] = Field(..., description="List of user IDs to share with")
    permission: str = Field(default="read", description="Permission level for all users")
    team_id: Optional[str] = Field(default=None, description="Workspace/team ID")


class WorkspaceMemberRemovalRequest(BaseModel):
    """Request to remove all access for a user in a workspace."""
    team_id: str = Field(..., description="Workspace/team ID")
    user_id: str = Field(..., description="User ID to remove access for")


class SharedUserInfo(BaseModel):
    """Information about a user with access."""
    user_id: str
    permission: str
    shared_at: datetime
    shared_by: str

class SharedTeamInfo(BaseModel):
    """Information about a team with access."""
    team_id: str
    permission: str
    shared_at: datetime
    shared_by: str


class ResourcePermissionsResponse(BaseModel):
    """Response with resource permissions information."""
    resource_id: str
    resource_type: str
    owner_id: str
    shared_with: List[SharedUserInfo]
    shared_with_teams: List[SharedTeamInfo] = []
    is_public: bool
    created_at: Optional[datetime]


class ShareActionResponse(BaseModel):
    """Response from share/revoke actions."""
    success: bool
    message: str
    resource_id: str
    resource_type: str
    target_user_id: Optional[str] = None
    permission: Optional[str] = None


# =========================================================================
# Validation Helpers
# =========================================================================

def validate_resource_type(resource_type: str) -> None:
    """Validate that resource_type is supported."""
    if resource_type not in RESOURCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_resource_type",
                "message": f"Resource type '{resource_type}' is not supported",
                "valid_types": sorted(RESOURCE_TYPES)
            }
        )


def validate_permission(permission: str) -> None:
    """Validate that permission level is valid."""
    if permission not in PERMISSION_LEVELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_permission",
                "message": f"Permission '{permission}' is not valid",
                "valid_permissions": list(PERMISSION_LEVELS.keys())
            }
        )


# =========================================================================
# Share Endpoints
# =========================================================================

@router.post("/share", response_model=ShareActionResponse)
async def share_resource(
    request: Request,
    data: ShareResourceRequest
):
    """
    Share a resource with another user.
    
    Only the resource owner or users with admin permission can share.
    
    Args:
        data: Share request with resource_id, resource_type, target_user_id, permission
        
    Returns:
        ShareActionResponse with success status
    """
    user_id = get_secure_user_id(request)
    
    # Validate inputs
    validate_resource_type(data.resource_type)
    validate_permission(data.permission)
    
    # Prevent sharing with self (only for users)
    if data.target_type == "user" and data.target_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_share_target",
                "message": "Cannot share a resource with yourself"
            }
        )
    
    auth_service = get_authorization_service()
    
    result = await auth_service.grant_access(
        owner_id=user_id,
        resource_id=data.resource_id,
        resource_type=data.resource_type,
        target_id=data.target_id,
        target_type=data.target_type,
        permission=data.permission,
        team_id=data.team_id
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN if result.get("error") == "not_authorized" else status.HTTP_400_BAD_REQUEST,
            detail={
                "error": result.get("error", "share_failed"),
                "message": result.get("message", "Failed to share resource")
            }
        )
    
    logger.info(f"✅ Resource shared: {data.resource_type}:{data.resource_id} -> {data.target_type}={data.target_id} by {user_id}")
    
    return ShareActionResponse(
        success=True,
        message=f"Successfully shared {data.resource_type} with {data.target_type}",
        resource_id=data.resource_id,
        resource_type=data.resource_type,
        target_user_id=data.target_id, # Reusing field for ID
        permission=data.permission
    )


@router.post("/share/bulk", response_model=dict)
async def bulk_share_resource(
    request: Request,
    data: BulkShareRequest
):
    """
    Share a resource with multiple users at once.
    
    Args:
        data: Bulk share request with list of target user IDs
        
    Returns:
        Dict with success count and failures
    """
    user_id = get_secure_user_id(request)
    
    validate_resource_type(data.resource_type)
    validate_permission(data.permission)
    
    # Remove self from target list
    target_users = [uid for uid in data.target_user_ids if uid != user_id]
    
    if not target_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid target users provided"
        )
    
    auth_service = get_authorization_service()
    
    successes = []
    failures = []
    
    for target_user_id in target_users:
        result = await auth_service.grant_access(
            owner_id=user_id,
            resource_id=data.resource_id,
            resource_type=data.resource_type,
            target_id=target_user_id,
            permission=data.permission,
            team_id=data.team_id
        )
        
        if result.get("success"):
            successes.append(target_user_id)
        else:
            failures.append({
                "user_id": target_user_id,
                "error": result.get("message", "Unknown error")
            })
    
    logger.info(f"✅ Bulk share: {data.resource_type}:{data.resource_id} -> {len(successes)} users by {user_id}")
    
    return {
        "success": len(failures) == 0,
        "resource_id": data.resource_id,
        "resource_type": data.resource_type,
        "shared_count": len(successes),
        "shared_with": successes,
        "failures": failures
    }


# =========================================================================
# Revoke Endpoints
# =========================================================================

@router.post("/revoke", response_model=ShareActionResponse)
async def revoke_access(
    request: Request,
    data: RevokeAccessRequest
):
    """
    Revoke a user's access to a resource.
    
    Only the resource owner or users with admin permission can revoke access.
    
    Args:
        data: Revoke request with resource_id, resource_type, target_user_id
        
    Returns:
        ShareActionResponse with success status
    """
    user_id = get_secure_user_id(request)
    
    validate_resource_type(data.resource_type)
    
    auth_service = get_authorization_service()
    
    result = await auth_service.revoke_access(
        revoker_id=user_id,
        resource_id=data.resource_id,
        resource_type=data.resource_type,
        target_id=data.target_id,
        target_type=data.target_type
    )
    
    if not result.get("success"):
        status_code = status.HTTP_403_FORBIDDEN if result.get("error") == "not_authorized" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": result.get("error", "revoke_failed"),
                "message": result.get("message", "Failed to revoke access")
            }
        )
    
    logger.info(f"✅ Access revoked: {data.resource_type}:{data.resource_id} X {data.target_type}={data.target_id} by {user_id}")
    
    return ShareActionResponse(
        success=True,
        message=f"Successfully revoked access to {data.resource_type}",
        resource_id=data.resource_id,
        resource_type=data.resource_type,
        target_user_id=data.target_id
    )


@router.delete("/revoke/{resource_type}/{resource_id}/{target_user_id}", response_model=ShareActionResponse)
async def revoke_access_delete(
    request: Request,
    resource_type: str,
    resource_id: str,
    target_user_id: str
):
    """
    Revoke a user's access to a resource (DELETE method).
    
    Alternative to POST /revoke for RESTful clients.
    """
    user_id = get_secure_user_id(request)
    
    validate_resource_type(resource_type)
    
    auth_service = get_authorization_service()
    
    result = await auth_service.revoke_access(
        revoker_id=user_id,
        resource_id=resource_id,
        resource_type=resource_type,
        target_id=target_user_id
    )
    
    if not result.get("success"):
        status_code = status.HTTP_403_FORBIDDEN if result.get("error") == "not_authorized" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": result.get("error", "revoke_failed"),
                "message": result.get("message", "Failed to revoke access")
            }
        )
    
    return ShareActionResponse(
        success=True,
        message=f"Successfully revoked access to {resource_type}",
        resource_id=resource_id,
        resource_type=resource_type,
        target_user_id=target_user_id
    )


# =========================================================================
# Workspace Member Removal
# =========================================================================

@router.post("/workspace/remove-member", response_model=dict)
async def remove_workspace_member_access(
    request: Request,
    data: WorkspaceMemberRemovalRequest
):
    """
    Remove all resource access for a user being removed from a workspace.
    
    This should be called when a user is removed from a workspace/team.
    It revokes access to all shared resources in that workspace.
    
    Only workspace owners/admins should call this endpoint.
    
    Args:
        data: Request with team_id and user_id to remove
        
    Returns:
        Dict with count of revoked permissions
    """
    user_id = get_secure_user_id(request)
    
    # TODO: Add workspace admin check here
    # For now, we trust the caller is authorized
    
    auth_service = get_authorization_service()
    
    result = await auth_service.revoke_all_user_access_in_workspace(
        team_id=data.team_id,
        user_id=data.user_id,
        revoked_by=user_id
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": result.get("error", "removal_failed"),
                "message": result.get("message", "Failed to remove workspace member access")
            }
        )
    
    logger.info(f"✅ Workspace member access removed: {data.user_id} from {data.team_id} by {user_id}")
    
    return {
        "success": True,
        "team_id": data.team_id,
        "user_id": data.user_id,
        "revoked_count": result.get("revoked_count", 0),
        "message": f"Revoked access to {result.get('revoked_count', 0)} resources"
    }


# =========================================================================
# Query Endpoints
# =========================================================================

@router.get("/permissions/{resource_type}/{resource_id}", response_model=ResourcePermissionsResponse)
async def get_resource_permissions(
    request: Request,
    resource_type: str,
    resource_id: str
):
    """
    Get permissions info for a resource.
    
    Returns the owner and list of users with access.
    Only accessible by the owner or users with admin permission.
    
    Args:
        resource_type: Type of resource
        resource_id: ID of the resource
        
    Returns:
        ResourcePermissionsResponse with owner and shared users
    """
    user_id = get_secure_user_id(request)
    
    validate_resource_type(resource_type)
    
    auth_service = get_authorization_service()
    
    # First check if user has admin access
    access_result = await auth_service.check_access(
        user_id=user_id,
        resource_id=resource_id,
        resource_type=resource_type,
        required_permission="admin"
    )
    
    if not access_result.get("allowed"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only resource owner or admins can view permissions"
        )
    
    # Get the permission record
    permission_record = await auth_service.db.resource_permissions.find_one({
        "resource_id": resource_id,
        "resource_type": resource_type
    })
    
    if not permission_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No permissions found for {resource_type}:{resource_id}"
        )
    
    # Resolve user ObjectIds to emails for display (batch query)
    shares_list = permission_record.get("shared_with", [])
    oid_to_email = {}
    oid_candidates = []
    for share in shares_list:
        uid = share.get("user_id", "")
        if uid and len(uid) == 24 and all(c in "0123456789abcdef" for c in uid):
            oid_candidates.append(uid)
    if oid_candidates:
        try:
            from bson import ObjectId
            oid_objs = [ObjectId(o) for o in oid_candidates]
            cursor = auth_service.db.users.find({"_id": {"$in": oid_objs}}, {"_id": 1, "email": 1})
            async for user_doc in cursor:
                if user_doc.get("email"):
                    oid_to_email[str(user_doc["_id"])] = user_doc["email"]
        except Exception:
            pass

    shared_users = []
    for share in shares_list:
        uid = share.get("user_id", "")
        uid = oid_to_email.get(uid, uid)
        shared_users.append(SharedUserInfo(
            user_id=uid,
            permission=share["permission"],
            shared_at=share["shared_at"],
            shared_by=share.get("shared_by", permission_record["owner_id"])
        ))
    
    # Filter out corrupt team entries with None team_id
    shared_teams = [
        SharedTeamInfo(
            team_id=share["team_id"],
            permission=share["permission"],
            shared_at=share["shared_at"],
            shared_by=share.get("shared_by", permission_record["owner_id"])
        )
        for share in permission_record.get("shared_with_teams", [])
        if share.get("team_id")
    ]
    
    return ResourcePermissionsResponse(
        resource_id=resource_id,
        resource_type=resource_type,
        owner_id=permission_record["owner_id"],
        shared_with=shared_users,
        shared_with_teams=shared_teams,
        is_public=permission_record.get("is_public", False),
        created_at=permission_record.get("created_at")
    )


@router.get("/my-shared/{resource_type}")
async def get_my_shared_resources(
    request: Request,
    resource_type: str,
    team_id: Optional[str] = Query(default=None, description="Filter by workspace/team ID")
):
    """
    Get resources of a specific type that have been shared with the current user.
    
    Args:
        resource_type: Type of resource to query
        team_id: Optional workspace filter
        
    Returns:
        List of resource IDs with their permission levels and titles
    """
    user_id = get_secure_user_id(request)
    
    validate_resource_type(resource_type)
    
    auth_service = get_authorization_service()
    
    result = await auth_service.get_accessible_resources(
        user_id=user_id,
        resource_type=resource_type,
        team_id=team_id
    )
    
    # Filter to only shared resources (not owned)
    shared_resources = [
        {
            "resource_id": r["resource_id"],
            "permission": r["permission"],
            "owner_id": r.get("owner_id"),
            "shared_by": r.get("shared_by"),
            "shared_at": r.get("shared_at")
        }
        for r in result.get("shared_details", [])
    ]
    
    # Enrich shared resources with titles/names from the source collections
    if shared_resources:
        try:
            from bson import ObjectId
            resource_title_map = {
                "vault": ("folders", "name"),
                "presentation": ("presentations", "title"),
                "printable": ("printables", "title"),
                "report": ("composer_reports", "title"),
                "diagram": ("diagrams", "diagram_name"),
                "document": ("document_chunked", "topic_or_filename"),
                "chat": ("chat_sessions", "title"),
                "project": ("projects", "name"),
            }
            
            collection_info = resource_title_map.get(resource_type)
            if collection_info:
                coll_name, title_field = collection_info
                resource_ids = [r["resource_id"] for r in shared_resources]
                
                # Build deduplicated query with both string and ObjectId forms
                seen = set()
                query_ids = []
                for rid in resource_ids:
                    if rid not in seen:
                        seen.add(rid)
                        query_ids.append(rid)
                    if len(rid) == 24:
                        try:
                            oid = ObjectId(rid)
                            if oid not in seen:
                                seen.add(oid)
                                query_ids.append(oid)
                        except Exception:
                            pass
                
                collection = auth_service.db[coll_name]
                cursor = collection.find(
                    {"_id": {"$in": query_ids}},
                    {"_id": 1, title_field: 1}
                )
                
                title_map = {}
                async for doc in cursor:
                    doc_id = str(doc["_id"])
                    title_map[doc_id] = doc.get(title_field, doc_id)
                
                # Inject title into shared resources
                for r in shared_resources:
                    r["title"] = title_map.get(r["resource_id"], r["resource_id"])
        except Exception as title_err:
            logger.warning(f"⚠️ Could not enrich shared resources with titles: {title_err}")
    
    return {
        "resource_type": resource_type,
        "team_id": team_id,
        "count": len(shared_resources),
        "resources": shared_resources
    }


@router.get("/i-shared/{resource_type}")
async def get_resources_i_shared(
    request: Request,
    resource_type: str,
    team_id: Optional[str] = Query(default=None, description="Filter by workspace/team ID")
):
    """
    Get resources of a specific type that the current user has shared with others.
    
    Args:
        resource_type: Type of resource to query
        team_id: Optional workspace filter
        
    Returns:
        List of resources with their sharing details
    """
    user_id = get_secure_user_id(request)
    
    validate_resource_type(resource_type)
    
    auth_service = get_authorization_service()
    
    # Query resources owned by user that have shares
    query = {
        "owner_id": user_id,
        "resource_type": resource_type,
        "shared_with.0": {"$exists": True}  # Has at least one share
    }
    
    if team_id:
        query["team_id"] = team_id
    
    cursor = auth_service.db.resource_permissions.find(query)
    resources = await cursor.to_list(length=100)
    
    result = []
    for r in resources:
        shared_with = [
            {
                "user_id": s["user_id"],
                "permission": s["permission"],
                "shared_at": s["shared_at"].isoformat() if s.get("shared_at") else None
            }
            for s in r.get("shared_with", [])
        ]
        result.append({
            "resource_id": r["resource_id"],
            "shared_with_count": len(shared_with),
            "shared_with": shared_with
        })
    
    return {
        "resource_type": resource_type,
        "team_id": team_id,
        "count": len(result),
        "resources": result
    }


@router.get("/check-access/{resource_type}/{resource_id}")
async def check_access(
    request: Request,
    resource_type: str,
    resource_id: str,
    permission: str = Query(default="read", description="Permission level to check")
):
    """
    Check if current user has access to a resource.
    
    Useful for UI to determine what actions to show.
    
    Args:
        resource_type: Type of resource
        resource_id: ID of the resource
        permission: Permission level to check (read, write, admin)
        
    Returns:
        Dict with access info
    """
    user_id = get_secure_user_id(request)
    
    validate_resource_type(resource_type)
    validate_permission(permission)
    
    auth_service = get_authorization_service()
    
    result = await auth_service.check_access(
        user_id=user_id,
        resource_id=resource_id,
        resource_type=resource_type,
        required_permission=permission
    )
    
    return {
        "resource_id": resource_id,
        "resource_type": resource_type,
        "requested_permission": permission,
        "has_access": result.get("allowed", False),
        "actual_permission": result.get("permission"),
        "is_owner": result.get("is_owner", False)
    }


# =========================================================================
# User Lookup for Sharing UI
# =========================================================================

@router.get("/users/search")
async def search_users_for_sharing(
    request: Request,
    query: str = Query(..., min_length=2, description="Search query (email or name)"),
    team_id: Optional[str] = Query(default=None, description="Limit to workspace members")
):
    """
    Search for users to share with.
    
    Returns a list of users matching the search query.
    If team_id is provided, only returns members of that workspace.
    
    Args:
        query: Search string (min 2 chars)
        team_id: Optional workspace filter
        
    Returns:
        List of users with id, email, name
    """
    user_id = get_secure_user_id(request)
    auth_service = get_authorization_service()
    
    # Search in users collection
    search_filter = {
        "$or": [
            {"email": {"$regex": query, "$options": "i"}},
            {"displayName": {"$regex": query, "$options": "i"}},
            {"name": {"$regex": query, "$options": "i"}}
        ]
    }
    
    # If team_id provided, filter by workspace members
    if team_id:
        # Get workspace members first
        workspace = await auth_service.db.workspaces.find_one({"_id": team_id})
        if workspace:
            member_ids = [m.get("userId") or m.get("uid") for m in workspace.get("members", [])]
            search_filter["_id"] = {"$in": member_ids}
    
    # Exclude current user
    search_filter["_id"] = {"$ne": user_id}
    
    cursor = auth_service.db.users.find(
        search_filter,
        {"_id": 1, "email": 1, "displayName": 1, "name": 1, "photoURL": 1}
    ).limit(20)
    
    users = await cursor.to_list(length=20)
    
    return {
        "count": len(users),
        "users": [
            {
                "user_id": u.get("email", str(u["_id"])),
                "email": u.get("email", ""),
                "display_name": u.get("displayName") or u.get("name", ""),
                "photo_url": u.get("photoURL")
            }
            for u in users
        ]
    }
