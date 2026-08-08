"""
Team API Routes - REST API for team/workspace management
"""
from fastapi import APIRouter, Request, HTTPException, status, Depends, Query
from typing import Optional, List
import logging

from models.team import (
    TeamCreate, TeamUpdate, TeamResponse, TeamListItem,
    TeamRole, TeamStatus, ShareValidation
)
from services.team_service import get_team_service
from services.team_member_service import get_member_service
from citra_auth import get_secure_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2/teams", tags=["Teams"])


# ==================== Helper Functions ====================

async def get_current_user_info(request: Request) -> dict:
    """Extract user info from request state (set by auth middleware)"""
    user_id = getattr(request.state, 'user_id', None)
    user_email = getattr(request.state, 'user_email', None) or user_id
    user_name = getattr(request.state, 'user_name', None)
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    return {
        "user_id": user_id,
        "user_email": user_email,
        "user_name": user_name
    }


# ==================== Team CRUD ====================

@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_team(
    team_data: TeamCreate,
    request: Request
):
    """
    Create a new team/workspace.
    The creator becomes the team owner automatically.
    """
    user_info = await get_current_user_info(request)
    service = get_team_service()
    
    result = await service.create_team(
        name=team_data.name,
        owner_id=user_info["user_id"],
        owner_email=user_info["user_email"],
        owner_name=user_info["user_name"],
        description=team_data.description,
        settings=team_data.settings
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Failed to create team")
        )
    
    return result


@router.get("", response_model=List[dict])
async def list_user_teams(request: Request):
    """
    List all teams the current user belongs to.
    Includes personal workspace info.
    """
    user_info = await get_current_user_info(request)
    service = get_team_service()
    
    teams = await service.get_user_teams(
        user_id=user_info["user_id"],
        user_email=user_info["user_email"]
    )
    
    # Add personal workspace as first item
    result = [
        {
            "team_id": None,
            "name": "Personal Workspace",
            "role": "owner",
            "member_count": 1,
            "is_owner": True,
            "is_personal": True
        }
    ]
    result.extend(teams)
    
    return result


@router.get("/{team_id}", response_model=dict)
async def get_team(
    team_id: str,
    request: Request
):
    """
    Get team details.
    User must be a member of the team.
    """
    user_info = await get_current_user_info(request)
    service = get_team_service()
    
    # Verify membership
    is_member = await service.is_team_member(team_id, user_info["user_email"])
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this team"
        )
    
    team = await service.get_team(team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    
    return {"success": True, "team": team}


@router.put("/{team_id}", response_model=dict)
async def update_team(
    team_id: str,
    team_data: TeamUpdate,
    request: Request
):
    """
    Update team details.
    Only team owner or admin can update.
    """
    user_info = await get_current_user_info(request)
    service = get_team_service()
    
    result = await service.update_team(
        team_id=team_id,
        user_id=user_info["user_id"],
        update_data=team_data
    )
    
    if not result.get("success"):
        error = result.get("error", "Failed to update team")
        if "Not authorized" in error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return result


@router.delete("/{team_id}", response_model=dict)
async def archive_team(
    team_id: str,
    request: Request
):
    """
    Archive (soft delete) a team.
    Only team owner can archive.
    """
    user_info = await get_current_user_info(request)
    service = get_team_service()
    
    result = await service.archive_team(
        team_id=team_id,
        user_id=user_info["user_id"]
    )
    
    if not result.get("success"):
        error = result.get("error", "Failed to archive team")
        if "Only team owner" in error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return result


# ==================== Member Management ====================

@router.get("/{team_id}/members", response_model=List[dict])
async def list_team_members(
    team_id: str,
    request: Request,
    include_removed: bool = Query(False, description="Include removed members")
):
    """
    List all members of a team.
    User must be a member to view.
    """
    user_info = await get_current_user_info(request)
    team_service = get_team_service()
    
    # Verify membership
    is_member = await team_service.is_team_member(team_id, user_info["user_email"])
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this team"
        )
    
    member_service = get_member_service()
    members = await member_service.get_team_members(team_id, include_removed)
    
    return members


@router.put("/{team_id}/members/{member_email}", response_model=dict)
async def update_member_role(
    team_id: str,
    member_email: str,
    role_data: dict,  # {"role": "admin", "permissions": {...}}
    request: Request
):
    """
    Update a member's role.
    Only team owner or admin can update roles.
    """
    from models.team import MemberRoleUpdate, MemberPermissions
    
    user_info = await get_current_user_info(request)
    member_service = get_member_service()
    
    # Build update model
    update_data = MemberRoleUpdate(
        role=TeamRole(role_data.get("role", "member")),
        permissions=MemberPermissions(**role_data["permissions"]) if role_data.get("permissions") else None
    )
    
    result = await member_service.update_member_role(
        team_id=team_id,
        target_user_email=member_email,
        update_data=update_data,
        updated_by=user_info["user_id"]
    )
    
    if not result.get("success"):
        error = result.get("error", "Failed to update member")
        if "Not authorized" in error or "Only admins" in error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return result


@router.delete("/{team_id}/members/{member_email}", response_model=dict)
async def remove_member(
    team_id: str,
    member_email: str,
    request: Request
):
    """
    Remove a member from the team.
    Admins can remove members. Members can remove themselves.
    """
    user_info = await get_current_user_info(request)
    member_service = get_member_service()
    
    result = await member_service.remove_member(
        team_id=team_id,
        target_user_email=member_email,
        removed_by=user_info["user_id"]
    )
    
    if not result.get("success"):
        error = result.get("error", "Failed to remove member")
        if "Not authorized" in error or "Cannot remove" in error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return result


@router.get("/{team_id}/members/search", response_model=List[dict])
async def search_team_members(
    team_id: str,
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, le=50),
    request: Request = None
):
    """
    Search team members by name or email.
    Used for secure autocomplete in sharing UI.
    """
    user_info = await get_current_user_info(request)
    team_service = get_team_service()
    
    # Verify membership
    is_member = await team_service.is_team_member(team_id, user_info["user_email"])
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this team"
        )
    
    member_service = get_member_service()
    results = await member_service.search_team_members(team_id, q, limit)
    
    return results


# ==================== Share Validation ====================

@router.post("/{team_id}/validate-share", response_model=dict)
async def validate_share_target(
    team_id: str,
    target_email: str,
    request: Request
):
    """
    Validate if sharing with a target email is allowed.
    Returns warnings for external users.
    """
    user_info = await get_current_user_info(request)
    service = get_team_service()
    
    validation = await service.validate_share_target(
        team_id=team_id,
        owner_email=user_info["user_email"],
        target_email=target_email
    )
    
    return {
        "success": True,
        "validation": validation.model_dump() if hasattr(validation, 'model_dump') else validation
    }


@router.post("/validate-share", response_model=dict)
async def validate_share_target_personal(
    target_email: str,
    request: Request
):
    """
    Validate share target for personal workspace (no team context).
    Always returns external warning.
    """
    user_info = await get_current_user_info(request)
    
    target_email = target_email.lower().strip()
    
    # Can't share with yourself
    if target_email == user_info["user_email"].lower():
        return {
            "success": True,
            "validation": {
                "allowed": False,
                "reason": "Cannot share with yourself"
            }
        }
    
    # Personal workspace - always external with warning
    return {
        "success": True,
        "validation": {
            "allowed": True,
            "is_team_member": False,
            "is_external": True,
            "warning": "⚠️ Please verify the email address before sharing."
        }
    }
