"""
Sharing Migration Service

Migrates existing sharing data from legacy collections to the centralized 
resource_permissions collection for unified authorization.

Legacy Collections:
- vault_shares: Vault sharing via email
- shared_with_me: Presentations/reports received via public links
- public_shares: Public shareable links

Target Collection:
- resource_permissions: Centralized permission store
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from bson import ObjectId

logger = logging.getLogger(__name__)


class SharingMigrationService:
    """
    Service to migrate existing sharing data to centralized authorization.
    """
    
    def __init__(self, db):
        self.db = db
        self.permissions_col = db["resource_permissions"]
        self.vault_shares_col = db["vault_shares"]
        self.shared_with_me_col = db["shared_with_me"]
        self.public_shares_col = db["public_shares"]
        self.users_col = db["users"]
    
    async def migrate_all(self) -> Dict[str, Any]:
        """
        Run full migration of all legacy sharing data.
        
        Returns:
            Dict with migration statistics
        """
        logger.info("🔄 Starting sharing data migration to centralized authorization...")
        
        results = {
            "vault_shares": await self.migrate_vault_shares(),
            "shared_with_me": await self.migrate_shared_with_me(),
            "total_migrated": 0,
            "errors": []
        }
        
        results["total_migrated"] = (
            results["vault_shares"].get("migrated", 0) +
            results["shared_with_me"].get("migrated", 0)
        )
        
        logger.info(f"✅ Migration complete. Total migrated: {results['total_migrated']}")
        
        return results
    
    async def migrate_vault_shares(self) -> Dict[str, Any]:
        """
        Migrate vault_shares collection to resource_permissions.
        
        vault_shares structure:
        {
            vault_id, vault_name, owner_id, owner_email,
            shared_with_email, permission, status, created_at
        }
        """
        logger.info("📂 Migrating vault shares...")
        
        migrated = 0
        skipped = 0
        errors = []
        
        try:
            # Get all active vault shares
            cursor = self.vault_shares_col.find({"status": "active"})
            vault_shares = await cursor.to_list(length=10000)
            
            for share in vault_shares:
                try:
                    vault_id = share.get("vault_id")
                    owner_id = share.get("owner_id")
                    shared_with_email = share.get("shared_with_email", "").lower()
                    permission = share.get("permission", "read")
                    
                    if not vault_id or not owner_id or not shared_with_email:
                        skipped += 1
                        continue
                    
                    # Look up user_id from email
                    shared_user = await self.users_col.find_one(
                        {"email": {"$regex": f"^{shared_with_email}$", "$options": "i"}}
                    )
                    
                    if not shared_user:
                        # User not found, skip but log
                        logger.warning(f"⚠️ User not found for email: {shared_with_email}")
                        skipped += 1
                        continue
                    
                    shared_user_id = str(shared_user.get("_id") or shared_user.get("uid"))
                    
                    # Check if permission already exists
                    existing = await self.permissions_col.find_one({
                        "resource_id": vault_id,
                        "resource_type": "vault"
                    })
                    
                    if existing:
                        # Add to shared_with if not already there
                        already_shared = any(
                            s["user_id"] == shared_user_id 
                            for s in existing.get("shared_with", [])
                        )
                        
                        if not already_shared:
                            await self.permissions_col.update_one(
                                {"_id": existing["_id"]},
                                {
                                    "$push": {
                                        "shared_with": {
                                            "user_id": shared_user_id,
                                            "user_email": shared_with_email,
                                            "permission": permission,
                                            "shared_at": share.get("created_at", datetime.utcnow()),
                                            "shared_by": owner_id,
                                            "migrated_from": "vault_shares"
                                        }
                                    },
                                    "$set": {"updated_at": datetime.utcnow()}
                                }
                            )
                            migrated += 1
                        else:
                            skipped += 1
                    else:
                        # Create new permission record
                        await self.permissions_col.insert_one({
                            "resource_id": vault_id,
                            "resource_type": "vault",
                            "owner_id": owner_id,
                            "team_id": share.get("team_id"),
                            "shared_with": [{
                                "user_id": shared_user_id,
                                "user_email": shared_with_email,
                                "permission": permission,
                                "shared_at": share.get("created_at", datetime.utcnow()),
                                "shared_by": owner_id,
                                "migrated_from": "vault_shares"
                            }],
                            "is_public": False,
                            "created_at": share.get("created_at", datetime.utcnow()),
                            "updated_at": datetime.utcnow()
                        })
                        migrated += 1
                        
                except Exception as e:
                    errors.append(f"vault_share {share.get('_id')}: {str(e)}")
                    logger.error(f"❌ Error migrating vault share: {e}")
            
            logger.info(f"📂 Vault shares: {migrated} migrated, {skipped} skipped, {len(errors)} errors")
            
        except Exception as e:
            logger.error(f"❌ Failed to migrate vault shares: {e}")
            errors.append(f"vault_shares collection: {str(e)}")
        
        return {"migrated": migrated, "skipped": skipped, "errors": errors}
    
    async def migrate_shared_with_me(self) -> Dict[str, Any]:
        """
        Migrate shared_with_me collection to resource_permissions.
        
        shared_with_me structure:
        {
            user_id, content_type, source_id, share_token,
            owner_id, title, permission, accepted_at
        }
        """
        logger.info("📋 Migrating shared_with_me entries...")
        
        migrated = 0
        skipped = 0
        errors = []
        
        # Map content_type to resource_type
        type_mapping = {
            "presentation": "presentation",
            "report": "report",
            "diagram": "diagram",
            "chat": "chat",
            "document": "document"
        }
        
        try:
            cursor = self.shared_with_me_col.find({})
            shared_entries = await cursor.to_list(length=10000)
            
            for entry in shared_entries:
                try:
                    user_id = entry.get("user_id")
                    content_type = entry.get("content_type")
                    source_id = entry.get("source_id")
                    owner_id = entry.get("owner_id")
                    permission = entry.get("permission", "read")
                    
                    if not user_id or not content_type or not source_id:
                        skipped += 1
                        continue
                    
                    resource_type = type_mapping.get(content_type)
                    if not resource_type:
                        logger.warning(f"⚠️ Unknown content_type: {content_type}")
                        skipped += 1
                        continue
                    
                    # Check if permission already exists
                    existing = await self.permissions_col.find_one({
                        "resource_id": source_id,
                        "resource_type": resource_type
                    })
                    
                    if existing:
                        # Add to shared_with if not already there
                        already_shared = any(
                            s["user_id"] == user_id 
                            for s in existing.get("shared_with", [])
                        )
                        
                        if not already_shared:
                            await self.permissions_col.update_one(
                                {"_id": existing["_id"]},
                                {
                                    "$push": {
                                        "shared_with": {
                                            "user_id": user_id,
                                            "permission": permission,
                                            "shared_at": entry.get("accepted_at", datetime.utcnow()),
                                            "shared_by": owner_id,
                                            "migrated_from": "shared_with_me"
                                        }
                                    },
                                    "$set": {"updated_at": datetime.utcnow()}
                                }
                            )
                            migrated += 1
                        else:
                            skipped += 1
                    else:
                        # Create new permission record
                        # We may not have owner_id, so mark it
                        await self.permissions_col.insert_one({
                            "resource_id": source_id,
                            "resource_type": resource_type,
                            "owner_id": owner_id or "unknown",  # May need to look up
                            "team_id": None,
                            "shared_with": [{
                                "user_id": user_id,
                                "permission": permission,
                                "shared_at": entry.get("accepted_at", datetime.utcnow()),
                                "shared_by": owner_id,
                                "migrated_from": "shared_with_me"
                            }],
                            "is_public": False,
                            "created_at": entry.get("accepted_at", datetime.utcnow()),
                            "updated_at": datetime.utcnow()
                        })
                        migrated += 1
                        
                except Exception as e:
                    errors.append(f"shared_with_me {entry.get('_id')}: {str(e)}")
                    logger.error(f"❌ Error migrating shared_with_me entry: {e}")
            
            logger.info(f"📋 Shared with me: {migrated} migrated, {skipped} skipped, {len(errors)} errors")
            
        except Exception as e:
            logger.error(f"❌ Failed to migrate shared_with_me: {e}")
            errors.append(f"shared_with_me collection: {str(e)}")
        
        return {"migrated": migrated, "skipped": skipped, "errors": errors}
    
    async def sync_vault_shares_to_centralized(self, vault_share: Dict) -> bool:
        """
        Sync a single vault share to centralized permissions.
        Called when a new vault share is created.
        """
        try:
            from services.authorization_service import get_authorization_service
            
            vault_id = vault_share.get("vault_id")
            owner_id = vault_share.get("owner_id")
            shared_with_email = vault_share.get("shared_with_email", "").lower()
            permission = vault_share.get("permission", "read")
            team_id = vault_share.get("team_id")
            
            # Look up user_id from email
            shared_user = await self.users_col.find_one(
                {"email": {"$regex": f"^{shared_with_email}$", "$options": "i"}}
            )
            
            if not shared_user:
                logger.warning(f"⚠️ Cannot sync vault share - user not found: {shared_with_email}")
                return False
            
            shared_user_id = str(shared_user.get("_id") or shared_user.get("uid"))
            
            auth_service = get_authorization_service()
            result = await auth_service.grant_access(
                owner_id=owner_id,
                resource_id=vault_id,
                resource_type="vault",
                target_user_id=shared_user_id,
                permission=permission,
                team_id=team_id
            )
            
            return result.get("success", False)
            
        except Exception as e:
            logger.error(f"❌ Failed to sync vault share to centralized: {e}")
            return False
    
    async def sync_shared_with_me_to_centralized(self, shared_entry: Dict) -> bool:
        """
        Sync a single shared_with_me entry to centralized permissions.
        Called when a user accepts a share.
        """
        try:
            from services.authorization_service import get_authorization_service
            
            user_id = shared_entry.get("user_id")
            content_type = shared_entry.get("content_type")
            source_id = shared_entry.get("source_id")
            owner_id = shared_entry.get("owner_id")
            permission = shared_entry.get("permission", "read")
            
            type_mapping = {
                "presentation": "presentation",
                "report": "report",
                "diagram": "diagram",
                "chat": "chat",
                "document": "document"
            }
            
            resource_type = type_mapping.get(content_type)
            if not resource_type:
                return False
            
            auth_service = get_authorization_service()
            
            # First register the resource if not exists
            await auth_service.register_resource(
                resource_id=source_id,
                resource_type=resource_type,
                owner_id=owner_id or "unknown",
                team_id=None
            )
            
            # Then grant access
            result = await auth_service.grant_access(
                owner_id=owner_id or "system",
                resource_id=source_id,
                resource_type=resource_type,
                target_user_id=user_id,
                permission=permission,
                team_id=None
            )
            
            return result.get("success", False)
            
        except Exception as e:
            logger.error(f"❌ Failed to sync shared_with_me to centralized: {e}")
            return False


# Singleton instance
_migration_service: Optional[SharingMigrationService] = None


def get_migration_service(db=None) -> SharingMigrationService:
    """Get or create the migration service instance."""
    global _migration_service
    if _migration_service is None:
        if db is None:
            from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
            client = get_async_mongo_client()
            db = client[MONGODB_DATABASE]
        _migration_service = SharingMigrationService(db)
    return _migration_service
