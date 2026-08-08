"""
Vault Sharing API Router

Endpoints for sharing vaults with other users via email.
"""

import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from motor.motor_asyncio import AsyncIOMotorClient

from citra_auth import get_current_user
from services.vault_sharing_service import VaultSharingService, get_vault_sharing_service
from models.vault_share import VaultShareCreate, VaultShareResponse, SharedVaultListItem, VaultSharerInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vault-sharing", tags=["vault-sharing"])


# Request/Response models
class ShareVaultRequest(BaseModel):
    """Request to share a vault"""
    vault_id: str
    shared_with_email: EmailStr
    permission: str = "read"


class RevokeShareRequest(BaseModel):
    """Request to revoke a vault share"""
    share_id: str


class VaultSharesQuery(BaseModel):
    """Query for vault shares"""
    vault_id: str


# Global service instance
_sharing_service: VaultSharingService = None


async def get_sharing_service() -> VaultSharingService:
    """Dependency to get the vault sharing service"""
    global _sharing_service
    if _sharing_service is None:
        # This will be properly initialized when the router is included
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vault sharing service not initialized"
        )
    return _sharing_service


def initialize_vault_sharing_service(mongo_client: AsyncIOMotorClient, database_name: str):
    """Initialize the vault sharing service (called from main.py)"""
    global _sharing_service
    _sharing_service = get_vault_sharing_service(mongo_client, database_name)
    logger.info("✅ Vault sharing API service initialized")


@router.post("/share", response_model=dict)
async def share_vault(
    request: ShareVaultRequest,
    http_request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Share a vault with another user.

    Authorisation: caller must admin the Work-SA that owns the vault.
    The SA-admin list comes from JWT (X-Sa-Admin-Of → request.state).
    """
    service = await get_sharing_service()

    user_id = current_user.get("user_id")
    user_email = current_user.get("email", user_id)
    # Personal-SA from JWT claims (populated by citra-auth middleware).
    # Folders are owned by the user's Personal SA; only that SA can share.
    personal_sa_id = getattr(http_request.state, "personal_sa_id", "") or ""

    result = await service.share_vault(
        vault_id=request.vault_id,
        owner_id=user_id,
        owner_email=user_email,
        shared_with_email=request.shared_with_email,
        permission=request.permission,
        caller_personal_sa_id=personal_sa_id,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Failed to share vault")
        )

    return result


@router.delete("/revoke/{share_id}")
async def revoke_share(
    share_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Revoke a vault share.
    
    Only the vault owner can revoke shares.
    """
    service = await get_sharing_service()
    
    user_id = current_user.get("user_id")
    
    result = await service.revoke_share(
        share_id=share_id,
        owner_id=user_id
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Failed to revoke share")
        )
    
    return result


@router.get("/shared-with-me", response_model=List[SharedVaultListItem])
async def get_shared_with_me(
    current_user: dict = Depends(get_current_user)
):
    """
    Get all vaults shared with the current user.
    
    Returns a list of vaults that other users have shared with you.
    """
    service = await get_sharing_service()
    
    user_email = current_user.get("email", current_user.get("user_id"))
    
    return await service.get_shared_with_me(user_email)


@router.get("/vault-shares/{vault_id}", response_model=List[VaultSharerInfo])
async def get_vault_shares(
    vault_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of users a vault is shared with.
    
    Only the vault owner can see who they have shared the vault with.
    """
    service = await get_sharing_service()
    
    user_id = current_user.get("user_id")
    
    return await service.get_vault_shares(
        vault_id=vault_id,
        owner_id=user_id
    )


@router.get("/check-access/{vault_id}")
async def check_vault_access(
    vault_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Check if the current user has access to a shared vault.
    
    Returns the permission level if access exists, or null if no access.
    """
    service = await get_sharing_service()
    
    user_email = current_user.get("email", current_user.get("user_id"))
    
    permission = await service.check_share_permission(
        vault_id=vault_id,
        user_email=user_email
    )
    
    return {
        "vault_id": vault_id,
        "has_access": permission is not None,
        "permission": permission
    }
