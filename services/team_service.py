"""
Team Service - Core business logic for team/workspace management
"""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from bson import ObjectId

from models.team import (
    TeamDocument, TeamMemberDocument, TeamRole, TeamStatus, MemberStatus,
    TeamCreate, TeamUpdate, TeamResponse, TeamListItem, TeamSettings,
    MemberPermissions, ShareValidation
)
from citra_mongo import get_async_mongo_client, MONGODB_DATABASE

logger = logging.getLogger(__name__)


class TeamService:
    """Service for team CRUD operations and team-level queries"""
    
    def __init__(self):
        self.db = None
        self._initialized = False
    
    async def _ensure_initialized(self):
        """Lazy initialization of database connection"""
        if not self._initialized:
            client = get_async_mongo_client()
            self.db = client[MONGODB_DATABASE]
            self.teams_col = self.db[TeamDocument.COLLECTION_NAME]
            self.members_col = self.db[TeamMemberDocument.COLLECTION_NAME]
            self._initialized = True
            await self._ensure_indexes()
    
    async def _ensure_indexes(self):
        """Create necessary indexes"""
        try:
            # Teams indexes
            await self.teams_col.create_index("team_id", unique=True)
            await self.teams_col.create_index([("owner_id", 1), ("status", 1)])
            
            # Members indexes
            await self.members_col.create_index([("team_id", 1), ("status", 1)])
            await self.members_col.create_index([("user_email", 1), ("status", 1)])
            await self.members_col.create_index(
                [("team_id", 1), ("user_email", 1)], 
                unique=True
            )
            
            logger.info("✅ Team indexes created/verified")
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")
    
    # ==================== Team CRUD ====================
    
    async def create_team(
        self,
        name: str,
        owner_id: str,
        owner_email: str,
        owner_name: Optional[str] = None,
        description: Optional[str] = None,
        settings: Optional[TeamSettings] = None
    ) -> Dict[str, Any]:
        """
        Create a new team and add the creator as owner
        
        Returns: {"success": bool, "team": TeamResponse, "error": str}
        """
        await self._ensure_initialized()
        
        try:
            # Create team document
            settings_dict = settings.model_dump() if settings else TeamSettings().model_dump()
            team_doc = TeamDocument.create_document(
                name=name,
                owner_id=owner_id,
                owner_email=owner_email,
                description=description,
                settings=settings_dict
            )
            
            # Insert team
            result = await self.teams_col.insert_one(team_doc)
            team_id = team_doc["team_id"]
            
            # Add owner as first member
            owner_member = TeamMemberDocument.create_document(
                team_id=team_id,
                user_id=owner_id,
                user_email=owner_email,
                user_name=owner_name,
                role=TeamRole.OWNER,
                invited_by=None
            )
            await self.members_col.insert_one(owner_member)
            
            logger.info(f"✅ Team '{name}' created by {owner_email} (ID: {team_id})")
            
            return {
                "success": True,
                "team": {
                    "team_id": team_id,
                    "name": name,
                    "description": description,
                    "owner_id": owner_id,
                    "owner_email": owner_email,
                    "settings": settings_dict,
                    "status": TeamStatus.ACTIVE.value,
                    "member_count": 1,
                    "created_at": team_doc["created_at"].isoformat(),
                    "updated_at": team_doc["updated_at"].isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to create team: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_team(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Get team by ID with member count"""
        await self._ensure_initialized()
        
        try:
            team = await self.teams_col.find_one({"team_id": team_id})
            if not team:
                return None
            
            # Get member count
            member_count = await self.members_col.count_documents({
                "team_id": team_id,
                "status": MemberStatus.ACTIVE.value
            })
            
            return {
                "team_id": team["team_id"],
                "name": team["name"],
                "description": team.get("description"),
                "owner_id": team["owner_id"],
                "owner_email": team["owner_email"],
                "settings": team.get("settings", {}),
                "status": team["status"],
                "member_count": member_count,
                "created_at": team["created_at"],
                "updated_at": team["updated_at"]
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get team {team_id}: {e}")
            return None
    
    async def update_team(
        self,
        team_id: str,
        user_id: str,
        update_data: TeamUpdate
    ) -> Dict[str, Any]:
        """Update team details (only owner/admin can update)"""
        await self._ensure_initialized()
        
        try:
            # Verify permission
            is_authorized = await self.is_team_admin(team_id, user_id)
            if not is_authorized:
                return {"success": False, "error": "Not authorized to update team"}
            
            # Build update document
            update_doc = {"updated_at": datetime.utcnow()}
            if update_data.name is not None:
                update_doc["name"] = update_data.name
            if update_data.description is not None:
                update_doc["description"] = update_data.description
            if update_data.settings is not None:
                update_doc["settings"] = update_data.settings.model_dump()
            
            result = await self.teams_col.update_one(
                {"team_id": team_id},
                {"$set": update_doc}
            )
            
            if result.modified_count == 0:
                return {"success": False, "error": "Team not found"}
            
            logger.info(f"✅ Team {team_id} updated by {user_id}")
            return {"success": True, "team_id": team_id}
            
        except Exception as e:
            logger.error(f"❌ Failed to update team: {e}")
            return {"success": False, "error": str(e)}
    
    async def archive_team(self, team_id: str, user_id: str) -> Dict[str, Any]:
        """Archive a team (soft delete) - only owner can archive"""
        await self._ensure_initialized()
        
        try:
            # Verify owner
            team = await self.teams_col.find_one({"team_id": team_id})
            if not team:
                return {"success": False, "error": "Team not found"}
            
            if team["owner_id"] != user_id:
                return {"success": False, "error": "Only team owner can archive"}
            
            await self.teams_col.update_one(
                {"team_id": team_id},
                {"$set": {
                    "status": TeamStatus.ARCHIVED.value,
                    "updated_at": datetime.utcnow()
                }}
            )
            
            logger.info(f"✅ Team {team_id} archived by {user_id}")
            return {"success": True}
            
        except Exception as e:
            logger.error(f"❌ Failed to archive team: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_user_teams(
        self,
        user_id: str,
        user_email: str
    ) -> List[TeamListItem]:
        """Get all teams a user belongs to"""
        await self._ensure_initialized()
        
        try:
            # Find all memberships for user
            cursor = self.members_col.find({
                "$or": [
                    {"user_id": user_id},
                    {"user_email": user_email.lower()}
                ],
                "status": MemberStatus.ACTIVE.value
            })
            
            memberships = await cursor.to_list(length=100)
            team_ids = [m["team_id"] for m in memberships]
            
            if not team_ids:
                return []
            
            # Get team details
            teams_cursor = self.teams_col.find({
                "team_id": {"$in": team_ids},
                "status": TeamStatus.ACTIVE.value
            })
            teams = await teams_cursor.to_list(length=100)
            
            # Build response with roles
            membership_map = {m["team_id"]: m for m in memberships}
            result = []
            
            for team in teams:
                membership = membership_map.get(team["team_id"], {})
                member_count = await self.members_col.count_documents({
                    "team_id": team["team_id"],
                    "status": MemberStatus.ACTIVE.value
                })
                
                result.append({
                    "team_id": team["team_id"],
                    "name": team["name"],
                    "role": membership.get("role", "member"),
                    "member_count": member_count,
                    "is_owner": team["owner_id"] == user_id
                })
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to get user teams: {e}")
            return []
    
    # ==================== Permission Checks ====================
    
    async def is_team_member(self, team_id: str, user_email: str) -> bool:
        """Check if user is an active member of team"""
        await self._ensure_initialized()
        
        member = await self.members_col.find_one({
            "team_id": team_id,
            "user_email": user_email.lower(),
            "status": MemberStatus.ACTIVE.value
        })
        return member is not None
    
    async def is_team_admin(self, team_id: str, user_id: str) -> bool:
        """Check if user is owner or admin of team"""
        await self._ensure_initialized()
        
        member = await self.members_col.find_one({
            "team_id": team_id,
            "$or": [
                {"user_id": user_id},
                {"user_email": user_id.lower()}  # Support email as user_id
            ],
            "status": MemberStatus.ACTIVE.value,
            "role": {"$in": [TeamRole.OWNER.value, TeamRole.ADMIN.value]}
        })
        return member is not None
    
    async def get_member_role(
        self,
        team_id: str,
        user_id: str
    ) -> Optional[TeamRole]:
        """Get user's role in a team"""
        await self._ensure_initialized()
        
        member = await self.members_col.find_one({
            "team_id": team_id,
            "$or": [
                {"user_id": user_id},
                {"user_email": user_id.lower()}
            ],
            "status": MemberStatus.ACTIVE.value
        })
        
        if member:
            return TeamRole(member["role"])
        return None
    
    async def get_team_settings(self, team_id: str) -> Optional[TeamSettings]:
        """Get team settings"""
        await self._ensure_initialized()
        
        team = await self.teams_col.find_one({"team_id": team_id})
        if team and "settings" in team:
            return TeamSettings(**team["settings"])
        return None
    
    # ==================== Share Validation ====================
    
    async def validate_share_target(
        self,
        team_id: str,
        owner_email: str,
        target_email: str
    ) -> ShareValidation:
        """
        Validate if sharing with target email is allowed.
        Implements security layers:
        1. Team member check → Allow immediately
        2. Domain whitelist → Allow if matches
        3. External user → Return warning or block
        """
        await self._ensure_initialized()
        
        target_email = target_email.lower().strip()
        
        # Can't share with yourself
        if target_email == owner_email.lower():
            return ShareValidation(
                allowed=False,
                reason="Cannot share with yourself"
            )
        
        # Layer 1: Team member check
        is_member = await self.is_team_member(team_id, target_email)
        if is_member:
            return ShareValidation(
                allowed=True,
                is_team_member=True,
                is_external=False
            )
        
        # Get team settings
        settings = await self.get_team_settings(team_id)
        if not settings:
            # No team context (personal workspace) - allow with warning
            return ShareValidation(
                allowed=True,
                is_external=True,
                warning="⚠️ Sharing outside your workspace. Please verify the email address."
            )
        
        # Layer 2: Domain whitelist
        target_domain = "@" + target_email.split("@")[1]
        if target_domain in settings.domain_whitelist:
            return ShareValidation(
                allowed=True,
                is_team_member=False,
                is_external=False,
                same_domain=True
            )
        
        # Layer 3: External sharing
        if settings.allow_external_sharing:
            return ShareValidation(
                allowed=True,
                is_external=True,
                warning=f"⚠️ {target_email} is outside your team. Are you sure you want to share?"
            )
        
        # External sharing disabled
        return ShareValidation(
            allowed=False,
            is_external=True,
            reason="External sharing is disabled for this team"
        )


# Global singleton instance
_team_service: Optional[TeamService] = None


def get_team_service() -> TeamService:
    """Get or create global team service instance"""
    global _team_service
    if _team_service is None:
        _team_service = TeamService()
    return _team_service
