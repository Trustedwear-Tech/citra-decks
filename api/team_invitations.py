"""
Team Invitation API Routes - REST API for team invitations
"""
from fastapi import APIRouter, Request, HTTPException, status, Query
from typing import Optional, List
import logging

from models.team import (
    TeamRole, InvitationStatus, InviteMemberRequest,
    TeamInvitationResponse, PendingInvitation
)
from services.team_invitation_service import get_invitation_service
from services.team_service import get_team_service
from citra_auth import get_secure_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2", tags=["Team Invitations"])


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


# ==================== Send Invitations ====================

@router.post("/teams/{team_id}/members/invite", response_model=dict)
async def invite_member(
    team_id: str,
    invite_data: InviteMemberRequest,
    request: Request
):
    """
    Send an invitation to join a team.
    Only team admins/owners can invite new members.
    """
    user_info = await get_current_user_info(request)
    
    # Check permission to invite
    team_service = get_team_service()
    role = await team_service.get_member_role(team_id, user_info["user_id"])
    
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this team"
        )
    
    # Check if user has invite permission
    from services.team_member_service import get_member_service
    member_service = get_member_service()
    member = await member_service.get_member(team_id, user_info["user_email"])
    
    can_invite = (
        role in [TeamRole.OWNER, TeamRole.ADMIN] or
        (member and member.get("permissions", {}).get("can_invite", False))
    )
    
    if not can_invite:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to invite members"
        )
    
    # Create invitation
    invitation_service = get_invitation_service()
    auth_token = (request.headers.get("authorization") or "").replace("Bearer ", "").strip() or None
    result = await invitation_service.create_invitation(
        team_id=team_id,
        invited_email=invite_data.email,
        invited_by_id=user_info["user_id"],
        invited_by_email=user_info["user_email"],
        invited_by_name=user_info["user_name"],
        role=invite_data.role,
        message=invite_data.message,
        auth_token=auth_token
    )
    
    if not result.get("success"):
        error = result.get("error", "Failed to send invitation")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return result


@router.get("/teams/{team_id}/invitations", response_model=List[dict])
async def list_team_invitations(
    team_id: str,
    request: Request,
    status_filter: Optional[str] = Query(None, description="Filter by status: pending, accepted, declined, expired")
):
    """
    List all invitations for a team.
    Only team admins/owners can view.
    """
    user_info = await get_current_user_info(request)
    
    # Check admin permission
    team_service = get_team_service()
    is_admin = await team_service.is_team_admin(team_id, user_info["user_id"])
    
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team admins can view invitations"
        )
    
    invitation_service = get_invitation_service()
    status_enum = InvitationStatus(status_filter) if status_filter else None
    
    invitations = await invitation_service.get_team_invitations(team_id, status_enum)
    
    return invitations


@router.delete("/teams/{team_id}/invitations/{invitation_token}", response_model=dict)
async def revoke_invitation(
    team_id: str,
    invitation_token: str,
    request: Request
):
    """
    Revoke a pending invitation.
    Only team admins/owners can revoke.
    """
    user_info = await get_current_user_info(request)
    
    invitation_service = get_invitation_service()
    result = await invitation_service.revoke_invitation(
        invitation_token=invitation_token,
        revoked_by=user_info["user_id"],
        team_id=team_id
    )
    
    if not result.get("success"):
        error = result.get("error", "Failed to revoke invitation")
        if "Not authorized" in error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return result


# ==================== User's Pending Invitations ====================

@router.get("/invitations/pending", response_model=List[dict])
async def get_my_pending_invitations(request: Request):
    """
    Get all pending invitations for the current user.
    Shows teams they've been invited to join.
    """
    user_info = await get_current_user_info(request)
    
    invitation_service = get_invitation_service()
    invitations = await invitation_service.get_pending_invitations(user_info["user_email"])
    
    return invitations


@router.post("/invitations/accept/{invitation_token}", response_model=dict)
async def accept_invitation(
    invitation_token: str,
    request: Request
):
    """
    Accept a team invitation.
    
    SECURITY: The logged-in user's email MUST match the invited email.
    This prevents link forwarding attacks.
    
    If the logged-in user's email doesn't match the invited email,
    returns requires_claim=true to allow the user to claim the invitation
    with their current account (after confirmation).
    """
    user_info = await get_current_user_info(request)
    
    invitation_service = get_invitation_service()
    result = await invitation_service.accept_invitation(
        invitation_token=invitation_token,
        accepting_user_id=user_info["user_id"],
        accepting_user_email=user_info["user_email"],
        accepting_user_name=user_info["user_name"]
    )
    
    # If requires_claim, return 200 with the claim data (not an error)
    if result.get("requires_claim"):
        return result
    
    if not result.get("success"):
        error = result.get("error", "Failed to accept invitation")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return result


@router.post("/invitations/claim/{invitation_token}", response_model=dict)
async def claim_invitation(
    invitation_token: str,
    request: Request
):
    """
    Claim a team invitation with a different email account.
    
    Use this endpoint when:
    1. User received invite at email A (e.g., xyz@yahoo.com)
    2. User logged in with email B (e.g., abc@gmail.com)
    3. User confirms they want to claim the invite with email B
    
    SECURITY:
    - Requires valid invitation token
    - Requires authenticated user
    - Sends notification email to original invited email for security audit
    """
    user_info = await get_current_user_info(request)
    
    invitation_service = get_invitation_service()
    auth_token = (request.headers.get("authorization") or "").replace("Bearer ", "").strip() or None
    result = await invitation_service.claim_invitation(
        invitation_token=invitation_token,
        claiming_user_id=user_info["user_id"],
        claiming_user_email=user_info["user_email"],
        claiming_user_name=user_info["user_name"],
        auth_token=auth_token
    )
    
    if not result.get("success"):
        error = result.get("error", "Failed to claim invitation")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return result


@router.post("/invitations/decline/{invitation_token}", response_model=dict)
async def decline_invitation(
    invitation_token: str,
    request: Request
):
    """
    Decline a team invitation.
    """
    user_info = await get_current_user_info(request)
    
    invitation_service = get_invitation_service()
    result = await invitation_service.decline_invitation(
        invitation_token=invitation_token,
        declining_user_email=user_info["user_email"]
    )
    
    if not result.get("success"):
        error = result.get("error", "Failed to decline invitation")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return result


# ==================== Public Validation (No Auth Required) ====================

@router.get("/invitations/validate/{invitation_token}", response_model=dict)
async def validate_invitation(invitation_token: str):
    """
    Validate an invitation token.
    This endpoint is PUBLIC (no auth required) so users can see 
    invitation details before logging in.
    
    Returns: Team name, who invited, expected email (masked), role
    """
    invitation_service = get_invitation_service()
    result = await invitation_service.validate_invitation(invitation_token)
    
    if not result.get("valid"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.get("error", "Invalid invitation")
        )
    
    # Mask email for privacy (show first 3 chars + domain)
    invited_email = result.get("invited_email", "")
    if "@" in invited_email:
        local, domain = invited_email.split("@")
        masked_email = f"{local[:3]}***@{domain}"
    else:
        masked_email = "***"
    
    return {
        "valid": True,
        "team_name": result.get("team_name"),
        "invited_email_masked": masked_email,
        "invited_by_name": result.get("invited_by_name"),
        "role": result.get("role"),
        "message": result.get("message")
    }
