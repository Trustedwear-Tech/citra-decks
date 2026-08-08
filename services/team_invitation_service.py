"""
Team Invitation Service - Handle team invitations with email
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import os

from models.team import (
    TeamInvitationDocument, TeamRole, InvitationStatus,
    InviteMemberRequest, TeamInvitationResponse, PendingInvitation
)
from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
from services.team_service import get_team_service
from services.team_member_service import get_member_service

logger = logging.getLogger(__name__)


class TeamInvitationService:
    """Service for managing team invitations"""
    
    def __init__(self):
        self.db = None
        self._initialized = False
        # Email service URL (user-service handles emails)
        self.user_service_url = os.getenv("USER_SERVICE_URL", "http://localhost:7004")
    
    async def _ensure_initialized(self):
        """Lazy initialization of database connection"""
        if not self._initialized:
            client = get_async_mongo_client()
            self.db = client[MONGODB_DATABASE]
            self.invitations_col = self.db[TeamInvitationDocument.COLLECTION_NAME]
            self.teams_col = self.db["teams"]
            self._initialized = True
            await self._ensure_indexes()
    
    async def _ensure_indexes(self):
        """Create necessary indexes"""
        try:
            await self.invitations_col.create_index("invitation_token", unique=True)
            await self.invitations_col.create_index([("invited_email", 1), ("status", 1)])
            await self.invitations_col.create_index([("team_id", 1), ("status", 1)])
            # TTL index to auto-expire old invitations (keep for audit, but mark expired)
            await self.invitations_col.create_index(
                "expires_at",
                expireAfterSeconds=30 * 24 * 60 * 60  # 30 days after expiry
            )
            logger.info("✅ Invitation indexes created/verified")
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")
    
    async def create_invitation(
        self,
        team_id: str,
        invited_email: str,
        invited_by_id: str,
        invited_by_email: str,
        invited_by_name: Optional[str] = None,
        role: TeamRole = TeamRole.MEMBER,
        message: Optional[str] = None,
        expires_in_days: int = 7,
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create an invitation to join a team
        
        Returns: {"success": bool, "invitation": dict, "error": str}
        """
        await self._ensure_initialized()
        
        try:
            invited_email = invited_email.lower().strip()
            
            # Get team info
            team = await self.teams_col.find_one({"team_id": team_id})
            if not team:
                return {"success": False, "error": "Team not found"}
            
            team_name = team["name"]
            
            # Check if user is already a member
            member_service = get_member_service()
            existing_member = await member_service.get_member(team_id, invited_email)
            if existing_member:
                return {"success": False, "error": f"{invited_email} is already a team member"}
            
            # Check for existing pending invitation
            existing_invite = await self.invitations_col.find_one({
                "team_id": team_id,
                "invited_email": invited_email,
                "status": InvitationStatus.PENDING.value,
                "expires_at": {"$gt": datetime.utcnow()}
            })
            
            if existing_invite:
                # Return existing invitation
                return {
                    "success": True,
                    "invitation": {
                        "invitation_id": str(existing_invite["_id"]),
                        "invitation_token": existing_invite["invitation_token"],
                        "team_id": team_id,
                        "team_name": team_name,
                        "invited_email": invited_email,
                        "status": "pending",
                        "already_exists": True
                    }
                }
            
            # Create new invitation
            invite_doc = TeamInvitationDocument.create_document(
                team_id=team_id,
                team_name=team_name,
                invited_email=invited_email,
                invited_by_id=invited_by_id,
                invited_by_email=invited_by_email,
                invited_by_name=invited_by_name,
                role=role,
                message=message,
                expires_in_days=expires_in_days
            )
            
            result = await self.invitations_col.insert_one(invite_doc)
            invitation_token = invite_doc["invitation_token"]
            
            logger.info(f"✅ Created invitation for {invited_email} to team {team_name}")
            
            # Send invitation email (async, don't block)
            try:
                await self._send_invitation_email(
                    invited_email=invited_email,
                    team_name=team_name,
                    invited_by_name=invited_by_name or invited_by_email,
                    invitation_token=invitation_token,
                    message=message,
                    auth_token=auth_token
                )
            except Exception as email_error:
                logger.warning(f"⚠️ Failed to send invitation email: {email_error}")
            
            return {
                "success": True,
                "invitation": {
                    "invitation_id": str(result.inserted_id),
                    "invitation_token": invitation_token,
                    "team_id": team_id,
                    "team_name": team_name,
                    "invited_email": invited_email,
                    "invited_by_email": invited_by_email,
                    "role": role.value,
                    "status": "pending",
                    "expires_at": invite_doc["expires_at"].isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to create invitation: {e}")
            return {"success": False, "error": str(e)}
    
    async def accept_invitation(
        self,
        invitation_token: str,
        accepting_user_id: str,
        accepting_user_email: str,
        accepting_user_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Accept an invitation - CRITICAL SECURITY: Verify email match
        
        Returns: {"success": bool, "team_id": str, "error": str}
        """
        await self._ensure_initialized()
        
        try:
            accepting_email = accepting_user_email.lower().strip()
            
            # Get invitation
            invitation = await self.invitations_col.find_one({
                "invitation_token": invitation_token
            })
            
            if not invitation:
                return {"success": False, "error": "Invitation not found"}
            
            # Check expiration
            if invitation["expires_at"] < datetime.utcnow():
                await self.invitations_col.update_one(
                    {"_id": invitation["_id"]},
                    {"$set": {"status": InvitationStatus.EXPIRED.value}}
                )
                return {"success": False, "error": "Invitation has expired"}
            
            # Check status
            if invitation["status"] != InvitationStatus.PENDING.value:
                return {"success": False, "error": f"Invitation already {invitation['status']}"}
            
            # Check if email matches
            if accepting_email != invitation["invited_email"].lower():
                logger.info(
                    f"📧 Email mismatch on invitation accept. "
                    f"Invited: {invitation['invited_email']}, Accepting: {accepting_email}. "
                    f"Returning requires_claim=true for user confirmation."
                )
                # Return requires_claim instead of hard error - let user confirm claim
                return {
                    "success": False,
                    "requires_claim": True,
                    "invited_email": invitation["invited_email"],
                    "accepting_email": accepting_email,
                    "team_name": invitation["team_name"],
                    "invitation_token": invitation_token,
                    "message": "This invitation was sent to a different email address. "
                               "You can claim this invitation with your current account."
                }
            
            # Add user to team
            member_service = get_member_service()
            add_result = await member_service.add_member(
                team_id=invitation["team_id"],
                user_id=accepting_user_id,
                user_email=accepting_email,
                user_name=accepting_user_name,
                role=TeamRole(invitation["role"]),
                invited_by=invitation["invited_by_id"]
            )
            
            if not add_result.get("success"):
                return add_result
            
            # Update invitation status
            await self.invitations_col.update_one(
                {"_id": invitation["_id"]},
                {"$set": {
                    "status": InvitationStatus.ACCEPTED.value,
                    "accepted_at": datetime.utcnow(),
                    "accepted_by_user_id": accepting_user_id
                }}
            )
            
            logger.info(f"✅ {accepting_email} accepted invitation to team {invitation['team_name']}")
            
            return {
                "success": True,
                "team_id": invitation["team_id"],
                "team_name": invitation["team_name"],
                "role": invitation["role"]
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to accept invitation: {e}")
            return {"success": False, "error": str(e)}
    
    async def claim_invitation(
        self,
        invitation_token: str,
        claiming_user_id: str,
        claiming_user_email: str,
        claiming_user_name: Optional[str] = None,
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Claim an invitation with a different email account.
        
        This allows users who received an invite at one email (e.g., yahoo)
        to accept it while logged in with a different email (e.g., gmail).
        
        Security: Sends notification to original email for verification.
        
        Returns: {"success": bool, "team_id": str, "error": str}
        """
        await self._ensure_initialized()
        
        try:
            claiming_email = claiming_user_email.lower().strip()
            
            # Get invitation
            invitation = await self.invitations_col.find_one({
                "invitation_token": invitation_token
            })
            
            if not invitation:
                return {"success": False, "error": "Invitation not found"}
            
            # Check expiration
            if invitation["expires_at"] < datetime.utcnow():
                await self.invitations_col.update_one(
                    {"_id": invitation["_id"]},
                    {"$set": {"status": InvitationStatus.EXPIRED.value}}
                )
                return {"success": False, "error": "Invitation has expired"}
            
            # Check status
            if invitation["status"] != InvitationStatus.PENDING.value:
                return {"success": False, "error": f"Invitation already {invitation['status']}"}
            
            original_email = invitation["invited_email"].lower()
            
            # Add user to team
            member_service = get_member_service()
            add_result = await member_service.add_member(
                team_id=invitation["team_id"],
                user_id=claiming_user_id,
                user_email=claiming_email,
                user_name=claiming_user_name,
                role=TeamRole(invitation["role"]),
                invited_by=invitation["invited_by_id"]
            )
            
            if not add_result.get("success"):
                return add_result
            
            # Update invitation status with claim info
            await self.invitations_col.update_one(
                {"_id": invitation["_id"]},
                {"$set": {
                    "status": InvitationStatus.ACCEPTED.value,
                    "accepted_at": datetime.utcnow(),
                    "accepted_by_user_id": claiming_user_id,
                    # Track the claim for audit
                    "claimed": True,
                    "original_invited_email": original_email,
                    "claimed_by_email": claiming_email,
                    "claimed_at": datetime.utcnow()
                }}
            )
            
            logger.info(
                f"✅ Invitation claimed: {claiming_email} claimed invite for {original_email} "
                f"to team {invitation['team_name']}"
            )
            
            # Send security notification to original email
            try:
                await self._send_claim_notification_email(
                    original_email=original_email,
                    claiming_email=claiming_email,
                    claiming_user_name=claiming_user_name,
                    team_name=invitation["team_name"],
                    invited_by_name=invitation.get("invited_by_name") or invitation["invited_by_email"],
                    auth_token=auth_token
                )
            except Exception as email_error:
                logger.warning(f"⚠️ Failed to send claim notification email: {email_error}")
            
            return {
                "success": True,
                "team_id": invitation["team_id"],
                "team_name": invitation["team_name"],
                "role": invitation["role"],
                "claimed": True,
                "original_email": original_email
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to claim invitation: {e}")
            return {"success": False, "error": str(e)}

    async def decline_invitation(
        self,
        invitation_token: str,
        declining_user_email: str
    ) -> Dict[str, Any]:
        """Decline an invitation"""
        await self._ensure_initialized()
        
        try:
            declining_email = declining_user_email.lower().strip()
            
            invitation = await self.invitations_col.find_one({
                "invitation_token": invitation_token
            })
            
            if not invitation:
                return {"success": False, "error": "Invitation not found"}
            
            # Verify email match
            if declining_email != invitation["invited_email"].lower():
                return {"success": False, "error": "Not authorized to decline this invitation"}
            
            if invitation["status"] != InvitationStatus.PENDING.value:
                return {"success": False, "error": f"Invitation already {invitation['status']}"}
            
            await self.invitations_col.update_one(
                {"_id": invitation["_id"]},
                {"$set": {
                    "status": InvitationStatus.DECLINED.value,
                    "declined_at": datetime.utcnow()
                }}
            )
            
            logger.info(f"✅ {declining_email} declined invitation to team {invitation['team_name']}")
            return {"success": True}
            
        except Exception as e:
            logger.error(f"❌ Failed to decline invitation: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_pending_invitations(
        self,
        user_email: str
    ) -> List[PendingInvitation]:
        """Get all pending invitations for a user"""
        await self._ensure_initialized()
        
        try:
            user_email = user_email.lower().strip()
            
            cursor = self.invitations_col.find({
                "invited_email": user_email,
                "status": InvitationStatus.PENDING.value,
                "expires_at": {"$gt": datetime.utcnow()}
            }).sort("created_at", -1)
            
            invitations = await cursor.to_list(length=50)
            
            return [
                {
                    "invitation_token": inv["invitation_token"],
                    "team_id": inv["team_id"],
                    "team_name": inv["team_name"],
                    "invited_by_email": inv["invited_by_email"],
                    "invited_by_name": inv.get("invited_by_name"),
                    "role": inv["role"],
                    "message": inv.get("message"),
                    "created_at": inv["created_at"].isoformat(),
                    "expires_at": inv["expires_at"].isoformat()
                }
                for inv in invitations
            ]
            
        except Exception as e:
            logger.error(f"❌ Failed to get pending invitations: {e}")
            return []
    
    async def get_team_invitations(
        self,
        team_id: str,
        status_filter: Optional[InvitationStatus] = None
    ) -> List[Dict[str, Any]]:
        """Get all invitations for a team (for admins)"""
        await self._ensure_initialized()
        
        try:
            query = {"team_id": team_id}
            if status_filter:
                query["status"] = status_filter.value
            
            cursor = self.invitations_col.find(query).sort("created_at", -1)
            invitations = await cursor.to_list(length=100)
            
            return [
                {
                    "invitation_id": str(inv["_id"]),
                    "invitation_token": inv["invitation_token"],
                    "invited_email": inv["invited_email"],
                    "invited_by_email": inv["invited_by_email"],
                    "role": inv["role"],
                    "status": inv["status"],
                    "created_at": inv["created_at"].isoformat(),
                    "expires_at": inv["expires_at"].isoformat(),
                    "accepted_at": inv["accepted_at"].isoformat() if inv.get("accepted_at") else None
                }
                for inv in invitations
            ]
            
        except Exception as e:
            logger.error(f"❌ Failed to get team invitations: {e}")
            return []
    
    async def revoke_invitation(
        self,
        invitation_token: str,
        revoked_by: str,
        team_id: str
    ) -> Dict[str, Any]:
        """Revoke a pending invitation (admin action)"""
        await self._ensure_initialized()
        
        try:
            # Verify admin permission
            team_service = get_team_service()
            is_admin = await team_service.is_team_admin(team_id, revoked_by)
            if not is_admin:
                return {"success": False, "error": "Not authorized"}
            
            result = await self.invitations_col.update_one(
                {
                    "invitation_token": invitation_token,
                    "team_id": team_id,
                    "status": InvitationStatus.PENDING.value
                },
                {"$set": {
                    "status": InvitationStatus.EXPIRED.value,
                    "revoked_at": datetime.utcnow(),
                    "revoked_by": revoked_by
                }}
            )
            
            if result.modified_count == 0:
                return {"success": False, "error": "Invitation not found or already processed"}
            
            logger.info(f"✅ Invitation revoked by {revoked_by}")
            return {"success": True}
            
        except Exception as e:
            logger.error(f"❌ Failed to revoke invitation: {e}")
            return {"success": False, "error": str(e)}
    
    async def validate_invitation(
        self,
        invitation_token: str
    ) -> Dict[str, Any]:
        """Validate an invitation token (for UI display before login)"""
        await self._ensure_initialized()
        
        try:
            invitation = await self.invitations_col.find_one({
                "invitation_token": invitation_token
            })
            
            if not invitation:
                return {"valid": False, "error": "Invitation not found"}
            
            if invitation["expires_at"] < datetime.utcnow():
                return {"valid": False, "error": "Invitation has expired"}
            
            if invitation["status"] != InvitationStatus.PENDING.value:
                return {"valid": False, "error": f"Invitation already {invitation['status']}"}
            
            return {
                "valid": True,
                "team_name": invitation["team_name"],
                "invited_email": invitation["invited_email"],
                "invited_by_name": invitation.get("invited_by_name") or invitation["invited_by_email"],
                "role": invitation["role"],
                "message": invitation.get("message")
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to validate invitation: {e}")
            return {"valid": False, "error": str(e)}
    
    async def _send_invitation_email(
        self,
        invited_email: str,
        team_name: str,
        invited_by_name: str,
        invitation_token: str,
        message: Optional[str] = None,
        auth_token: Optional[str] = None
    ):
        """Send invitation email via user service"""
        import aiohttp
        
        app_url = os.getenv("APP_URL", "http://localhost:8081")
        invite_link = f"{app_url}/invite/{invitation_token}"
        
        email_data = {
            "to": invited_email,
            "templateType": "team_invitation",
            "templateData": {
                "team_name": team_name,
                "invited_by_name": invited_by_name,
                "invite_link": invite_link,
                "personal_message": message
            }
        }
        
        try:
            headers = {}
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.user_service_url}/api/send",
                    json=email_data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        logger.info(f"✅ Invitation email sent to {invited_email}")
                    else:
                        body = await response.text()
                        logger.warning(f"⚠️ Email service returned {response.status}: {body}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to send invitation email: {e}")

    async def _send_claim_notification_email(
        self,
        original_email: str,
        claiming_email: str,
        claiming_user_name: Optional[str],
        team_name: str,
        invited_by_name: str,
        auth_token: Optional[str] = None
    ):
        """
        Send security notification to original email when invite is claimed.
        
        This notifies the original recipient that someone has joined using
        their invitation link with a different email account.
        """
        import aiohttp
        
        claiming_name = claiming_user_name or claiming_email
        
        email_data = {
            "to": original_email,
            "templateType": "invitation_claimed",
            "templateData": {
                "team_name": team_name,
                "invited_by_name": invited_by_name,
                "original_email": original_email,
                "claiming_email": claiming_email,
                "claiming_user_name": claiming_name,
                "claimed_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            }
        }
        
        try:
            headers = {}
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.user_service_url}/api/send",
                    json=email_data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        logger.info(f"✅ Claim notification email sent to {original_email}")
                    else:
                        body = await response.text()
                        logger.warning(f"⚠️ Email service returned {response.status} for claim notification: {body}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to send claim notification email: {e}")


# Global singleton instance
_invitation_service: Optional[TeamInvitationService] = None


def get_invitation_service() -> TeamInvitationService:
    """Get or create global invitation service instance"""
    global _invitation_service
    if _invitation_service is None:
        _invitation_service = TeamInvitationService()
    return _invitation_service
