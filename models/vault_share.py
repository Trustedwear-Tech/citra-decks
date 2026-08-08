"""
Vault Sharing Model

This module defines the data models for vault sharing functionality.
Users can share their vaults with other users via email.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr


class VaultShareCreate(BaseModel):
    """Request model for creating a vault share"""
    vault_id: str = Field(..., description="ID of the vault/folder to share")
    shared_with_email: str = Field(..., description="Email address of the user to share with")
    permission: str = Field(default="read", description="Permission level: 'read' or 'write'")


class VaultShareResponse(BaseModel):
    """Response model for vault share"""
    id: str = Field(..., description="Unique share ID")
    vault_id: str = Field(..., description="ID of the shared vault/folder")
    vault_name: str = Field(..., description="Name of the shared vault/folder")
    owner_email: str = Field(..., description="Email of the vault owner")
    owner_id: str = Field(..., description="User ID of the vault owner")
    shared_with_email: str = Field(..., description="Email of the user vault is shared with")
    shared_with_id: Optional[str] = Field(None, description="User ID of the recipient (if they exist)")
    permission: str = Field(default="read", description="Permission level")
    status: str = Field(default="active", description="Share status: 'active', 'revoked', 'pending'")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class VaultShareDocument:
    """MongoDB document schema for vault shares.

    Vaults (folders) are owned by a Work Service Account. Shares are keyed
    against the *owning SA*, not the user — so when a user is deleted and
    admin transfers the Work SA to another user, every share on every
    folder under that SA follows automatically.
    """
    COLLECTION_NAME = "vault_shares"

    @staticmethod
    def create_document(
        vault_id: str,
        vault_name: str,
        owner_sa_id: str,
        owner_email: str,
        owner_id: str,
        shared_with_email: str,
        shared_with_id: Optional[str] = None,
        permission: str = "read"
    ) -> dict:
        """Create a new vault share document.

        Args:
            owner_sa_id: The Work-SA that owns the folder. Authoritative.
            owner_email / owner_id: The user who created the share, kept
                for audit only — they do NOT control transfer semantics.
        """
        now = datetime.utcnow()
        return {
            "vault_id": vault_id,
            "vault_name": vault_name,
            "owner_sa_id": owner_sa_id,            # authoritative — transfer rewrites this
            "owner_email": owner_email,            # audit only
            "owner_id": owner_id,                  # audit only
            "shared_with_email": shared_with_email.lower(),  # Normalize email
            "shared_with_id": shared_with_id,
            "permission": permission,
            "status": "active",
            "created_at": now,
            "updated_at": now
        }


class SharedVaultListItem(BaseModel):
    """Model for listing shared vaults"""
    vault_id: str
    vault_name: str
    owner_email: str
    owner_id: str
    permission: str
    shared_at: datetime


class VaultSharerInfo(BaseModel):
    """Model for showing who a vault is shared with"""
    email: str
    permission: str
    status: str
    shared_at: datetime
