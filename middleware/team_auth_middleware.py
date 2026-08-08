"""
Team Authorization Middleware - Permission checks for team-based access control
"""
import logging
from typing import Optional, Callable
from functools import wraps

from fastapi import Request, HTTPException, status
from services.team_service import get_team_service
from services.team_member_service import get_member_service
from models.team import TeamRole

logger = logging.getLogger(__name__)


async def require_team_membership(
    team_id: str,
    user_id: str,
    user_email: str,
    min_role: Optional[TeamRole] = None
) -> dict:
    """
    Verify user has at least the minimum required role in a team.
    
    Args:
        team_id: The team to check membership for
        user_id: The user's ID
        user_email: The user's email
        min_role: Minimum role required (None = any member)
        
    Returns:
        Member info dict if authorized
        
    Raises:
        HTTPException 403 if not authorized
    """
    team_service = get_team_service()
    member_service = get_member_service()
    
    # Get member info
    member = await member_service.get_member(team_id, user_email)
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this team"
        )
    
    # Check role hierarchy if min_role specified
    if min_role:
        role_hierarchy = {
            TeamRole.VIEWER: 0,
            TeamRole.MEMBER: 1,
            TeamRole.ADMIN: 2,
            TeamRole.OWNER: 3
        }
        
        member_role = TeamRole(member["role"])
        required_level = role_hierarchy.get(min_role, 0)
        actual_level = role_hierarchy.get(member_role, 0)
        
        if actual_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {min_role.value} role or higher"
            )
    
    return member


async def require_team_admin(team_id: str, user_id: str) -> bool:
    """
    Verify user is admin or owner of a team.
    
    Raises:
        HTTPException 403 if not admin/owner
    """
    team_service = get_team_service()
    is_admin = await team_service.is_team_admin(team_id, user_id)
    
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or owner access required"
        )
    
    return True


async def require_team_owner(team_id: str, user_id: str) -> bool:
    """
    Verify user is the owner of a team.
    
    Raises:
        HTTPException 403 if not owner
    """
    team_service = get_team_service()
    team = await team_service.get_team(team_id)
    
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    
    if team["owner_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owner can perform this action"
        )
    
    return True


async def get_user_team_context(request: Request) -> dict:
    """
    Extract team context from request.
    Looks for team_id in:
    1. Request headers (X-Team-ID)
    2. Query parameters (?team_id=...)
    3. Request body (for POST/PUT)
    
    Returns:
        {
            "team_id": str | None,  # None = personal workspace
            "is_personal": bool
        }
    """
    # Check header first
    team_id = request.headers.get("X-Team-ID")
    
    # Check query params
    if not team_id:
        team_id = request.query_params.get("team_id")
    
    # Check if it's "personal" or None
    is_personal = team_id is None or team_id.lower() == "personal"
    
    return {
        "team_id": None if is_personal else team_id,
        "is_personal": is_personal
    }


async def validate_content_access(
    team_id: Optional[str],
    user_id: str,
    user_email: str,
    content_owner_id: str,
    content_team_id: Optional[str]
) -> bool:
    """
    Validate if user can access content based on team context.
    
    Rules:
    - Personal content (team_id=None): Only owner can access
    - Team content: Any team member can access
    
    Raises:
        HTTPException 403 if not authorized
    """
    # Content in personal workspace - only owner
    if content_team_id is None:
        if content_owner_id != user_id and content_owner_id != user_email:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied - this is private content"
            )
        return True
    
    # Content in a team - check membership
    team_service = get_team_service()
    is_member = await team_service.is_team_member(content_team_id, user_email)
    
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied - you are not a member of this team"
        )
    
    return True


def build_team_query(
    user_id: str,
    user_email: str,
    team_id: Optional[str] = None,
    include_shared: bool = False
) -> dict:
    """
    Build MongoDB query filter for team-aware content access.
    
    Args:
        user_id: Current user's ID
        user_email: Current user's email
        team_id: Active team ID (None = personal workspace)
        include_shared: Whether to include content shared with user
        
    Returns:
        MongoDB query dict to be used in find operations
    """
    if team_id:
        # Team workspace - show all team content
        query = {"team_id": team_id}
    else:
        # Personal workspace - show user's personal content only
        query = {
            "$and": [
                {"team_id": {"$in": [None, ""]}},  # No team assignment
                {"$or": [
                    {"user_id": user_id},
                    {"user_id": user_email}
                ]}
            ]
        }
    
    # Optionally include shared content
    if include_shared:
        query = {
            "$or": [
                query,
                {
                    "shared_with": {
                        "$elemMatch": {
                            "email": {"$regex": f"^{user_email}$", "$options": "i"}
                        }
                    }
                }
            ]
        }
    
    return query


class TeamPermissionChecker:
    """
    Dependency class for checking team permissions in route handlers.
    
    Usage:
        @router.get("/resource/{resource_id}")
        async def get_resource(
            resource_id: str,
            request: Request,
            team_check: dict = Depends(TeamPermissionChecker(min_role=TeamRole.MEMBER))
        ):
            team_id = team_check["team_id"]
            ...
    """
    
    def __init__(self, min_role: Optional[TeamRole] = None, required: bool = False):
        """
        Args:
            min_role: Minimum role required (None = any member)
            required: If True, team_id must be provided (not personal workspace)
        """
        self.min_role = min_role
        self.required = required
    
    async def __call__(self, request: Request) -> dict:
        user_id = getattr(request.state, 'user_id', None)
        user_email = getattr(request.state, 'user_email', None) or user_id
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        
        team_context = await get_user_team_context(request)
        team_id = team_context["team_id"]
        
        if self.required and team_context["is_personal"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Team context required for this operation"
            )
        
        # If team is specified, validate membership
        member_info = None
        if team_id:
            member_info = await require_team_membership(
                team_id=team_id,
                user_id=user_id,
                user_email=user_email,
                min_role=self.min_role
            )
        
        return {
            "team_id": team_id,
            "is_personal": team_context["is_personal"],
            "user_id": user_id,
            "user_email": user_email,
            "member_info": member_info
        }


# Convenience dependency instances
require_any_member = TeamPermissionChecker()
require_member_role = TeamPermissionChecker(min_role=TeamRole.MEMBER)
require_admin_role = TeamPermissionChecker(min_role=TeamRole.ADMIN)
require_owner_role = TeamPermissionChecker(min_role=TeamRole.OWNER)
require_team_context = TeamPermissionChecker(required=True)
