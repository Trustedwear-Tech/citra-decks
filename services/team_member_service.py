"""
Team Member Service - Manage team membership
"""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from bson import ObjectId

from models.team import (
    TeamMemberDocument, TeamRole, MemberStatus, MemberPermissions,
    TeamMemberResponse, MemberRoleUpdate
)
from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
from services.team_service import get_team_service

logger = logging.getLogger(__name__)


class TeamMemberService:
    """Service for managing team members"""
    
    def __init__(self):
        self.db = None
        self._initialized = False
    
    async def _ensure_initialized(self):
        """Lazy initialization of database connection"""
        if not self._initialized:
            client = get_async_mongo_client()
            self.db = client[MONGODB_DATABASE]
            self.members_col = self.db[TeamMemberDocument.COLLECTION_NAME]
            self.users_col = self.db["users"]
            self._initialized = True
    
    async def add_member(
        self,
        team_id: str,
        user_id: str,
        user_email: str,
        role: TeamRole = TeamRole.MEMBER,
        user_name: Optional[str] = None,
        invited_by: Optional[str] = None,
        permissions: Optional[MemberPermissions] = None
    ) -> Dict[str, Any]:
        """
        Add a user to a team
        
        Returns: {"success": bool, "member": dict, "error": str}
        """
        await self._ensure_initialized()
        
        try:
            user_email = user_email.lower()
            
            # Check if already a member
            existing = await self.members_col.find_one({
                "team_id": team_id,
                "user_email": user_email
            })
            
            if existing:
                if existing["status"] == MemberStatus.ACTIVE.value:
                    return {"success": False, "error": "User is already a team member"}
                
                # Re-activate removed member
                await self.members_col.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {
                        "status": MemberStatus.ACTIVE.value,
                        "role": role.value,
                        "joined_at": datetime.utcnow(),
                        "invited_by": invited_by
                    }}
                )
                logger.info(f"✅ Re-activated member {user_email} in team {team_id}")
                return {"success": True, "member": {"user_email": user_email, "reactivated": True}}
            
            # Get user info if not provided
            if not user_name:
                user = await self.users_col.find_one({"email": user_email})
                if user:
                    user_name = user.get("name")
            
            # Create member document
            permissions_dict = permissions.model_dump() if permissions else None
            member_doc = TeamMemberDocument.create_document(
                team_id=team_id,
                user_id=user_id,
                user_email=user_email,
                user_name=user_name,
                role=role,
                invited_by=invited_by,
                permissions=permissions_dict
            )
            
            await self.members_col.insert_one(member_doc)
            
            logger.info(f"✅ Added member {user_email} to team {team_id} with role {role.value}")
            
            return {
                "success": True,
                "member": {
                    "user_id": user_id,
                    "user_email": user_email,
                    "user_name": user_name,
                    "role": role.value,
                    "joined_at": member_doc["joined_at"].isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to add member: {e}")
            return {"success": False, "error": str(e)}
    
    async def remove_member(
        self,
        team_id: str,
        target_user_email: str,
        removed_by: str
    ) -> Dict[str, Any]:
        """
        Remove a member from team (soft delete)
        
        Returns: {"success": bool, "error": str}
        """
        await self._ensure_initialized()
        
        try:
            target_email = target_user_email.lower()
            
            # Get target member
            member = await self.members_col.find_one({
                "team_id": team_id,
                "user_email": target_email,
                "status": MemberStatus.ACTIVE.value
            })
            
            if not member:
                return {"success": False, "error": "Member not found"}
            
            # Can't remove owner
            if member["role"] == TeamRole.OWNER.value:
                return {"success": False, "error": "Cannot remove team owner"}
            
            # Check if remover has permission
            team_service = get_team_service()
            remover_member = await self.members_col.find_one({
                "team_id": team_id,
                "$or": [
                    {"user_id": removed_by},
                    {"user_email": removed_by.lower()}
                ],
                "status": MemberStatus.ACTIVE.value
            })
            
            if not remover_member:
                return {"success": False, "error": "Not authorized"}
            
            # Check permission
            can_remove = (
                remover_member["role"] in [TeamRole.OWNER.value, TeamRole.ADMIN.value] or
                remover_member.get("permissions", {}).get("can_remove_members", False)
            )
            
            if not can_remove:
                return {"success": False, "error": "Not authorized to remove members"}
            
            # Soft delete
            await self.members_col.update_one(
                {"_id": member["_id"]},
                {"$set": {
                    "status": MemberStatus.REMOVED.value,
                    "removed_at": datetime.utcnow(),
                    "removed_by": removed_by
                }}
            )
            
            # Revoke all shared resource access for this user in this workspace
            try:
                from services.authorization_service import get_authorization_service
                auth_service = get_authorization_service()
                revoke_result = await auth_service.revoke_all_user_access_in_workspace(
                    team_id=team_id,
                    user_id=member.get("user_id", target_email),
                    revoked_by=removed_by
                )
                if revoke_result.get("success"):
                    logger.info(f"✅ Revoked {revoke_result.get('revoked_count', 0)} shared resource access for {target_email}")
                else:
                    logger.warning(f"⚠️ Failed to revoke shared access: {revoke_result.get('error')}")
            except Exception as auth_e:
                logger.warning(f"⚠️ Could not revoke shared access (authorization service may not be initialized): {auth_e}")
            
            logger.info(f"✅ Removed member {target_email} from team {team_id}")
            return {"success": True}
            
        except Exception as e:
            logger.error(f"❌ Failed to remove member: {e}")
            return {"success": False, "error": str(e)}
    
    async def update_member_role(
        self,
        team_id: str,
        target_user_email: str,
        update_data: MemberRoleUpdate,
        updated_by: str
    ) -> Dict[str, Any]:
        """Update a member's role and permissions"""
        await self._ensure_initialized()
        
        try:
            target_email = target_user_email.lower()
            
            # Get target member
            member = await self.members_col.find_one({
                "team_id": team_id,
                "user_email": target_email,
                "status": MemberStatus.ACTIVE.value
            })
            
            if not member:
                return {"success": False, "error": "Member not found"}
            
            # Can't change owner's role
            if member["role"] == TeamRole.OWNER.value:
                return {"success": False, "error": "Cannot change owner's role"}
            
            # Check if updater is admin/owner
            team_service = get_team_service()
            is_admin = await team_service.is_team_admin(team_id, updated_by)
            if not is_admin:
                return {"success": False, "error": "Only admins can update roles"}
            
            # Build update
            update_doc = {"role": update_data.role.value}
            if update_data.permissions:
                update_doc["permissions"] = update_data.permissions.model_dump()
            else:
                # Set default permissions for new role
                update_doc["permissions"] = TeamMemberDocument.get_default_permissions(update_data.role)
            
            await self.members_col.update_one(
                {"_id": member["_id"]},
                {"$set": update_doc}
            )
            
            logger.info(f"✅ Updated role for {target_email} to {update_data.role.value}")
            return {"success": True, "role": update_data.role.value}
            
        except Exception as e:
            logger.error(f"❌ Failed to update member role: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_team_members(
        self,
        team_id: str,
        include_removed: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all members of a team"""
        await self._ensure_initialized()
        
        try:
            query = {"team_id": team_id}
            if not include_removed:
                query["status"] = MemberStatus.ACTIVE.value
            
            cursor = self.members_col.find(query).sort("joined_at", 1)
            members = await cursor.to_list(length=500)
            
            # Enrich with user profile info
            result = []
            for member in members:
                # Get profile picture from users collection
                user = await self.users_col.find_one({"email": member["user_email"]})
                
                result.append({
                    "user_id": member["user_id"],
                    "user_email": member["user_email"],
                    "user_name": member.get("user_name"),
                    "role": member["role"],
                    "status": member["status"],
                    "permissions": member.get("permissions", {}),
                    "joined_at": member["joined_at"],
                    "profile_picture": user.get("profilePicture") if user else None
                })
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to get team members: {e}")
            return []
    
    async def get_member(
        self,
        team_id: str,
        user_email: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific member's details"""
        await self._ensure_initialized()
        
        try:
            member = await self.members_col.find_one({
                "team_id": team_id,
                "user_email": user_email.lower(),
                "status": MemberStatus.ACTIVE.value
            })
            
            if not member:
                return None
            
            return {
                "user_id": member["user_id"],
                "user_email": member["user_email"],
                "user_name": member.get("user_name"),
                "role": member["role"],
                "status": member["status"],
                "permissions": member.get("permissions", {}),
                "joined_at": member["joined_at"]
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get member: {e}")
            return None
    
    async def search_team_members(
        self,
        team_id: str,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search team members by name or email (for autocomplete).
        This is the SECURE autocomplete - only returns team members.
        """
        await self._ensure_initialized()
        
        try:
            # Case-insensitive search on email and name
            cursor = self.members_col.find({
                "team_id": team_id,
                "status": MemberStatus.ACTIVE.value,
                "$or": [
                    {"user_email": {"$regex": query, "$options": "i"}},
                    {"user_name": {"$regex": query, "$options": "i"}}
                ]
            }).limit(limit)
            
            members = await cursor.to_list(length=limit)
            
            return [
                {
                    "user_id": m["user_id"],
                    "user_email": m["user_email"],
                    "user_name": m.get("user_name"),
                    "role": m["role"]
                }
                for m in members
            ]
            
        except Exception as e:
            logger.error(f"❌ Failed to search members: {e}")
            return []


# Global singleton instance
_member_service: Optional[TeamMemberService] = None


def get_member_service() -> TeamMemberService:
    """Get or create global member service instance"""
    global _member_service
    if _member_service is None:
        _member_service = TeamMemberService()
    return _member_service
