"""
Vault Sharing Service

This service handles vault sharing functionality including:
- Sharing vaults with other users via email
- Listing shared vaults for a user
- Revoking vault shares
- Checking share permissions
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from models.vault_share import VaultShareDocument, VaultShareResponse, SharedVaultListItem, VaultSharerInfo

logger = logging.getLogger(__name__)


class VaultSharingService:
    """Service for managing vault sharing"""
    
    def __init__(self, mongo_client: AsyncIOMotorClient, database_name: str):
        self.db = mongo_client[database_name]
        self.shares_collection = self.db[VaultShareDocument.COLLECTION_NAME]
        self.folders_collection = self.db["folders"]  # Folders collection for vault info
        self.logger = logging.getLogger(__name__)
    
    async def ensure_indexes(self):
        """Create necessary indexes for efficient queries"""
        try:
            # Authoritative: find every share for a given SA so the
            # user-delete worker can rewrite them in one update_many when
            # the SA transfers to a new admin.
            await self.shares_collection.create_index(
                [("owner_sa_id", 1), ("status", 1)],
                name="owner_sa_shares_idx"
            )
            # Audit / "shares I created" — kept for back-compat reads.
            await self.shares_collection.create_index(
                [("owner_id", 1), ("status", 1)],
                name="owner_shares_idx"
            )
            # Index for finding shares by recipient email
            await self.shares_collection.create_index(
                [("shared_with_email", 1), ("status", 1)],
                name="recipient_shares_idx"
            )
            # Index for finding specific vault shares
            await self.shares_collection.create_index(
                [("vault_id", 1), ("shared_with_email", 1)],
                name="vault_recipient_idx",
                unique=True
            )
            self.logger.info("✅ Vault sharing indexes created/verified")
        except Exception as e:
            self.logger.error(f"❌ Failed to create vault sharing indexes: {e}")
    
    async def share_vault(
        self,
        vault_id: str,
        owner_id: str,
        owner_email: str,
        shared_with_email: str,
        permission: str = "read",
        caller_personal_sa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Share a vault with another user.

        Ownership semantics (Personal-SA edition):
            Each vault is owned by exactly one user's Personal SA. Only
            that user can share it; ``caller_personal_sa_id`` must match
            the folder's ``owner_id``.

        Args:
            vault_id: ID of the vault/folder to share
            owner_id: User ID of the calling user (audit only)
            owner_email: Email of the calling user (audit only)
            shared_with_email: Email address of the recipient
            permission: Permission level ('read' or 'write')
            caller_personal_sa_id: Caller's Personal SA id from JWT.
                Must equal the folder's owner_id to authorise the share.
        """
        try:
            # Normalize email
            shared_with_email = shared_with_email.lower().strip()

            # Don't allow sharing with yourself
            if shared_with_email == owner_email.lower():
                return {
                    "success": False,
                    "error": "Cannot share vault with yourself"
                }

            # Look up the vault. Folder _ids are string UUIDs (see
            # folder_management.py:201), NOT ObjectIds.
            vault = await self.folders_collection.find_one({"_id": vault_id})
            if not vault:
                return {
                    "success": False,
                    "error": "Vault not found"
                }

            # Authorisation: the caller's Personal SA must own this vault.
            vault_owner_sa = vault.get("owner_id") if vault.get("owner_type") == "service_account" else None
            if not vault_owner_sa:
                return {
                    "success": False,
                    "error": "Vault has no Personal-SA owner; ask admin to run 'Fix Service Accounts' (or just re-list folders to auto-stamp)"
                }
            if not caller_personal_sa_id or caller_personal_sa_id != vault_owner_sa:
                return {
                    "success": False,
                    "error": "Only the owner can share this vault"
                }

            vault_name = vault.get("name", "Unnamed Vault")

            # Check if share already exists
            existing_share = await self.shares_collection.find_one({
                "vault_id": vault_id,
                "shared_with_email": shared_with_email,
                "status": "active"
            })

            if existing_share:
                return {
                    "success": False,
                    "error": f"Vault is already shared with {shared_with_email}"
                }

            # Create the share document, keyed against the owning SA.
            share_doc = VaultShareDocument.create_document(
                vault_id=vault_id,
                vault_name=vault_name,
                owner_sa_id=vault_owner_sa,
                owner_email=owner_email,
                owner_id=owner_id,
                shared_with_email=shared_with_email,
                permission=permission
            )
            
            result = await self.shares_collection.insert_one(share_doc)
            share_doc["_id"] = result.inserted_id
            
            # Sync to centralized authorization system
            try:
                from services.authorization_service import get_authorization_service
                
                # Look up user_id from email
                users_col = self.db["users"]
                shared_user = await users_col.find_one(
                    {"email": {"$regex": f"^{shared_with_email}$", "$options": "i"}}
                )
                
                if shared_user:
                    shared_user_id = str(shared_user.get("_id") or shared_user.get("uid"))
                    auth_service = get_authorization_service()
                    
                    # Register resource if not exists
                    await auth_service.register_resource(
                        resource_id=vault_id,
                        resource_type="vault",
                        owner_id=owner_id,
                        team_id=share_doc.get("team_id")
                    )
                    
                    # Grant access
                    await auth_service.grant_access(
                        owner_id=owner_id,
                        resource_id=vault_id,
                        resource_type="vault",
                        target_user_id=shared_user_id,
                        permission=permission,
                        team_id=share_doc.get("team_id")
                    )
                    self.logger.info(f"✅ Synced vault share to centralized auth: {vault_id} -> {shared_user_id}")
            except Exception as sync_e:
                self.logger.warning(f"⚠️ Could not sync to centralized auth (will work via legacy): {sync_e}")
            
            self.logger.info(f"✅ Vault '{vault_name}' shared with {shared_with_email} by {owner_email}")
            
            return {
                "success": True,
                "share": {
                    "id": str(result.inserted_id),
                    "vault_id": vault_id,
                    "vault_name": vault_name,
                    "shared_with_email": shared_with_email,
                    "permission": permission,
                    "created_at": share_doc["created_at"].isoformat()
                }
            }
            
        except Exception as e:
            self.logger.error(f"❌ Failed to share vault: {e}")
            return {
                "success": False,
                "error": f"Failed to share vault: {str(e)}"
            }
    
    async def revoke_share(
        self,
        share_id: str,
        owner_id: str
    ) -> Dict[str, Any]:
        """
        Revoke a vault share.
        
        Args:
            share_id: ID of the share to revoke
            owner_id: User ID of the vault owner (for verification)
            
        Returns:
            Dict with success status
        """
        try:
            result = await self.shares_collection.update_one(
                {
                    "_id": ObjectId(share_id),
                    "owner_id": owner_id,
                    "status": "active"
                },
                {
                    "$set": {
                        "status": "revoked",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                self.logger.info(f"✅ Share {share_id} revoked by owner {owner_id}")
                
                # Sync revocation to centralized authorization system
                try:
                    # Get the share details before it was revoked to get user info
                    share = await self.shares_collection.find_one({"_id": ObjectId(share_id)})
                    if share:
                        from services.authorization_service import get_authorization_service
                        
                        shared_with_email = share.get("shared_with_email", "").lower()
                        vault_id = share.get("vault_id")
                        
                        # Look up user_id from email
                        users_col = self.db["users"]
                        shared_user = await users_col.find_one(
                            {"email": {"$regex": f"^{shared_with_email}$", "$options": "i"}}
                        )
                        
                        if shared_user:
                            shared_user_id = str(shared_user.get("_id") or shared_user.get("uid"))
                            auth_service = get_authorization_service()
                            
                            await auth_service.revoke_access(
                                revoker_id=owner_id,
                                resource_id=vault_id,
                                resource_type="vault",
                                target_user_id=shared_user_id
                            )
                            self.logger.info(f"✅ Synced vault revoke to centralized auth: {vault_id} X {shared_user_id}")
                except Exception as sync_e:
                    self.logger.warning(f"⚠️ Could not sync revoke to centralized auth: {sync_e}")
                
                return {"success": True, "message": "Share revoked successfully"}
            else:
                return {"success": False, "error": "Share not found or already revoked"}
                
        except Exception as e:
            self.logger.error(f"❌ Failed to revoke share: {e}")
            return {"success": False, "error": f"Failed to revoke share: {str(e)}"}
    
    async def get_shared_with_me(
        self,
        user_email: str
    ) -> List[SharedVaultListItem]:
        """
        Get all vaults shared with a user.
        
        Args:
            user_email: Email of the user
            
        Returns:
            List of shared vault items
        """
        try:
            user_email = user_email.lower().strip()
            
            shares = await self.shares_collection.find({
                "shared_with_email": user_email,
                "status": "active"
            }).sort("created_at", -1).to_list(length=100)
            
            result = []
            for share in shares:
                result.append(SharedVaultListItem(
                    vault_id=share["vault_id"],
                    vault_name=share["vault_name"],
                    owner_email=share["owner_email"],
                    owner_id=share["owner_id"],
                    permission=share["permission"],
                    shared_at=share["created_at"]
                ))
            
            self.logger.info(f"📋 Found {len(result)} vaults shared with {user_email}")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Failed to get shared vaults: {e}")
            return []
    
    async def get_vault_shares(
        self,
        vault_id: str,
        owner_id: str
    ) -> List[VaultSharerInfo]:
        """
        Get list of users a vault is shared with.
        
        Args:
            vault_id: ID of the vault
            owner_id: User ID of the vault owner (for verification)
            
        Returns:
            List of share info for each recipient
        """
        try:
            shares = await self.shares_collection.find({
                "vault_id": vault_id,
                "owner_id": owner_id,
                "status": "active"
            }).to_list(length=100)
            
            result = []
            for share in shares:
                result.append(VaultSharerInfo(
                    email=share["shared_with_email"],
                    permission=share["permission"],
                    status=share["status"],
                    shared_at=share["created_at"]
                ))
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Failed to get vault shares: {e}")
            return []
    
    async def check_share_permission(
        self,
        vault_id: str,
        user_email: str
    ) -> Optional[str]:
        """
        Check if a user has share access to a vault.
        
        Args:
            vault_id: ID of the vault
            user_email: Email of the user checking access
            
        Returns:
            Permission level ('read', 'write') or None if no access
        """
        try:
            user_email = user_email.lower().strip()
            
            share = await self.shares_collection.find_one({
                "vault_id": vault_id,
                "shared_with_email": user_email,
                "status": "active"
            })
            
            if share:
                return share["permission"]
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Failed to check share permission: {e}")
            return None


# Global instance
_vault_sharing_service: Optional[VaultSharingService] = None


def get_vault_sharing_service(
    mongo_client: AsyncIOMotorClient,
    database_name: str
) -> VaultSharingService:
    """Get or create the vault sharing service singleton"""
    global _vault_sharing_service
    
    if _vault_sharing_service is None:
        _vault_sharing_service = VaultSharingService(mongo_client, database_name)
        logger.info("✅ Vault Sharing Service initialized")
    
    return _vault_sharing_service
