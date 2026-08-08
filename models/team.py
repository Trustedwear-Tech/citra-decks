"""
Team Models - Pydantic models for team/workspace management
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, EmailStr
from enum import Enum
import uuid


class TeamRole(str, Enum):
    """Team member roles with hierarchical permissions"""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class TeamStatus(str, Enum):
    """Team lifecycle status"""
    ACTIVE = "active"
    ARCHIVED = "archived"
    SUSPENDED = "suspended"


class MemberStatus(str, Enum):
    """Team member status"""
    ACTIVE = "active"
    PENDING = "pending"
    REMOVED = "removed"


class InvitationStatus(str, Enum):
    """Invitation lifecycle status"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class ContentVisibility(str, Enum):
    """Content visibility levels"""
    PRIVATE = "private"      # Only owner can see
    TEAM = "team"            # All team members can see
    PUBLIC = "public"        # Anyone with link


# ==================== Team Settings ====================

class TeamSettings(BaseModel):
    """Team configuration settings"""
    allow_external_sharing: bool = False
    default_permission: str = "read"
    domain_whitelist: List[str] = Field(default_factory=list)  # e.g., ["@company.com"]
    require_invite_approval: bool = False
    max_members: Optional[int] = None


# ==================== Team Models ====================

class TeamCreate(BaseModel):
    """Request model for creating a new team"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    settings: Optional[TeamSettings] = None


class TeamUpdate(BaseModel):
    """Request model for updating team"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    settings: Optional[TeamSettings] = None


class TeamResponse(BaseModel):
    """Response model for team data"""
    team_id: str
    name: str
    description: Optional[str] = None
    owner_id: str
    owner_email: str
    settings: TeamSettings
    status: TeamStatus
    member_count: int = 0
    created_at: datetime
    updated_at: datetime


class TeamListItem(BaseModel):
    """Simplified team info for lists"""
    team_id: str
    name: str
    role: TeamRole
    member_count: int = 0
    is_owner: bool = False


# ==================== Member Models ====================

class MemberPermissions(BaseModel):
    """Granular member permissions"""
    can_invite: bool = False
    can_remove_members: bool = False
    can_share_externally: bool = False
    can_manage_resources: bool = True


class TeamMemberCreate(BaseModel):
    """Internal model for creating team member record"""
    team_id: str
    user_id: str
    user_email: str
    user_name: Optional[str] = None
    role: TeamRole = TeamRole.MEMBER
    invited_by: Optional[str] = None
    permissions: Optional[MemberPermissions] = None


class TeamMemberResponse(BaseModel):
    """Response model for team member"""
    user_id: str
    user_email: str
    user_name: Optional[str] = None
    role: TeamRole
    status: MemberStatus
    permissions: MemberPermissions
    joined_at: datetime
    profile_picture: Optional[str] = None


class MemberRoleUpdate(BaseModel):
    """Request to update member role"""
    role: TeamRole
    permissions: Optional[MemberPermissions] = None


# ==================== Invitation Models ====================

class InviteMemberRequest(BaseModel):
    """Request to invite a new member"""
    email: EmailStr
    role: TeamRole = TeamRole.MEMBER
    message: Optional[str] = Field(None, max_length=500)


class TeamInvitationResponse(BaseModel):
    """Response model for invitation"""
    invitation_id: str
    invitation_token: str
    team_id: str
    team_name: str
    invited_email: str
    invited_by_email: str
    invited_by_name: Optional[str] = None
    role: TeamRole
    message: Optional[str] = None
    status: InvitationStatus
    created_at: datetime
    expires_at: datetime


class PendingInvitation(BaseModel):
    """Invitation shown to invitee"""
    invitation_token: str
    team_id: str
    team_name: str
    invited_by_email: str
    invited_by_name: Optional[str] = None
    role: TeamRole
    message: Optional[str] = None
    created_at: datetime
    expires_at: datetime


# ==================== Share Validation ====================

class ShareValidation(BaseModel):
    """Result of share target validation"""
    allowed: bool
    is_team_member: bool = False
    is_external: bool = False
    same_domain: bool = False
    warning: Optional[str] = None
    reason: Optional[str] = None


# ==================== Document Helpers ====================

class TeamDocument:
    """MongoDB document structure for teams"""
    COLLECTION_NAME = "teams"
    
    @staticmethod
    def create_document(
        name: str,
        owner_id: str,
        owner_email: str,
        description: Optional[str] = None,
        settings: Optional[dict] = None
    ) -> dict:
        now = datetime.utcnow()
        return {
            "team_id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "owner_id": owner_id,
            "owner_email": owner_email,
            "settings": settings or TeamSettings().model_dump(),
            "status": TeamStatus.ACTIVE.value,
            "created_at": now,
            "updated_at": now
        }


class TeamMemberDocument:
    """MongoDB document structure for team members"""
    COLLECTION_NAME = "team_members"
    
    @staticmethod
    def create_document(
        team_id: str,
        user_id: str,
        user_email: str,
        role: TeamRole,
        user_name: Optional[str] = None,
        invited_by: Optional[str] = None,
        permissions: Optional[dict] = None
    ) -> dict:
        # Set default permissions based on role
        if permissions is None:
            permissions = TeamMemberDocument.get_default_permissions(role)
        
        return {
            "team_id": team_id,
            "user_id": user_id,
            "user_email": user_email.lower(),
            "user_name": user_name,
            "role": role.value,
            "status": MemberStatus.ACTIVE.value,
            "permissions": permissions,
            "invited_by": invited_by,
            "joined_at": datetime.utcnow()
        }
    
    @staticmethod
    def get_default_permissions(role: TeamRole) -> dict:
        """Get default permissions based on role"""
        if role == TeamRole.OWNER:
            return {
                "can_invite": True,
                "can_remove_members": True,
                "can_share_externally": True,
                "can_manage_resources": True
            }
        elif role == TeamRole.ADMIN:
            return {
                "can_invite": True,
                "can_remove_members": True,
                "can_share_externally": True,
                "can_manage_resources": True
            }
        elif role == TeamRole.MEMBER:
            return {
                "can_invite": False,
                "can_remove_members": False,
                "can_share_externally": False,
                "can_manage_resources": True
            }
        else:  # VIEWER
            return {
                "can_invite": False,
                "can_remove_members": False,
                "can_share_externally": False,
                "can_manage_resources": False
            }


class TeamInvitationDocument:
    """MongoDB document structure for invitations"""
    COLLECTION_NAME = "team_invitations"
    
    @staticmethod
    def create_document(
        team_id: str,
        team_name: str,
        invited_email: str,
        invited_by_id: str,
        invited_by_email: str,
        invited_by_name: Optional[str] = None,
        role: TeamRole = TeamRole.MEMBER,
        message: Optional[str] = None,
        expires_in_days: int = 7
    ) -> dict:
        now = datetime.utcnow()
        from datetime import timedelta
        
        return {
            "invitation_token": str(uuid.uuid4()),
            "team_id": team_id,
            "team_name": team_name,
            "invited_email": invited_email.lower(),
            "invited_by_id": invited_by_id,
            "invited_by_email": invited_by_email,
            "invited_by_name": invited_by_name,
            "role": role.value,
            "message": message,
            "status": InvitationStatus.PENDING.value,
            "created_at": now,
            "expires_at": now + timedelta(days=expires_in_days),
            "accepted_at": None,
            "accepted_by_user_id": None
        }
