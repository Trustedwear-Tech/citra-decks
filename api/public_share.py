# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Public Share API - Generate shareable read-only links for diagrams, reports, and chats
Returns self-contained HTML pages that render in browser with CDN libraries
"""

import os
import traceback
import base64
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Literal
from datetime import datetime
from bson import ObjectId
import logging
import secrets
import string
import html

from citra_mongo import MongoDBManager
from services.image_processor import image_processor

logger = logging.getLogger(__name__)

router = APIRouter()

# Environment-based URL configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8085")
WEBSITE_URL = os.getenv("WEBSITE_URL", "http://localhost:8081")
_CITRA_LOGO_DATA_URI = None

def get_public_share_url(share_token: str) -> str:
    """Generate the public share URL"""
    if ENVIRONMENT == "development":
        return f"http://localhost:8085/s/{share_token}"
    else:
        return f"{BASE_URL.rstrip('/')}/s/{share_token}"


def get_citra_logo_src() -> str:
    """Return Citra logo image source for public share header."""
    global _CITRA_LOGO_DATA_URI
    if _CITRA_LOGO_DATA_URI:
        return _CITRA_LOGO_DATA_URI

    try:
        logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "citra-logo.png")
        with open(logo_path, "rb") as logo_file:
            logo_b64 = base64.b64encode(logo_file.read()).decode("ascii")
        _CITRA_LOGO_DATA_URI = f"data:image/png;base64,{logo_b64}"
    except Exception as e:
        logger.warning(f"Could not load citra-logo.png for public share header: {e}")
        _CITRA_LOGO_DATA_URI = f"{WEBSITE_URL}/favicon.ico"

    return _CITRA_LOGO_DATA_URI

# MongoDB setup - use MongoDBManager for all collections
# MongoDBManager provides connection pooling, health checks (ping),
# and automatic reconnection when connections go stale
mongo_manager = MongoDBManager()


class _LazyCollection:
    """Lazy collection proxy that always goes through MongoDBManager's
    reconnection-aware get_sync_client() on each access.
    This prevents stale connection errors (e.g., MongoDB Atlas idle timeouts)."""
    
    def __init__(self, collection_name: str):
        self._name = collection_name
    
    def _get(self):
        return mongo_manager.get_sync_collection(self._name)
    
    def __getattr__(self, name):
        return getattr(self._get(), name)
    
    def __repr__(self):
        return f"_LazyCollection({self._name!r})"


# Collections - lazy proxies that reconnect through MongoDBManager on each use
public_shares_collection = _LazyCollection('public_shares')
diagrams_collection = _LazyCollection('diagrams')
reports_collection = _LazyCollection('composer_reports')
presentations_collection = _LazyCollection('presentations')
printables_collection = _LazyCollection('printables')
chat_sessions_collection = _LazyCollection('ChatSessions')
message_pairs_collection = _LazyCollection('MessagePairs')
users_collection = _LazyCollection('users')

# Create unique index on share_token
try:
    public_shares_collection.create_index("share_token", unique=True)
    public_shares_collection.create_index([("user_id", 1), ("content_type", 1), ("source_id", 1)])
    logger.info("✅ Public shares indexes created")
except Exception as e:
    logger.warning(f"Index creation warning (may already exist): {e}")


def generate_share_token(length: int = 10) -> str:
    """Generate a short, URL-safe share token"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


CITRA_OG_LOGO_URL = "https://citra-ai.com/logo.png"


def _get_existing_thumbnail_s3_key(content_type: str, source_id: str) -> str | None:
    """Look up the saved thumbnail S3 key from the source document."""
    try:
        if content_type == "presentation":
            doc = presentations_collection.find_one({"_id": source_id}, {"thumbnail": 1})
        elif content_type == "printable":
            doc = printables_collection.find_one({"_id": source_id}, {"thumbnail": 1})
        elif content_type == "report":
            doc = reports_collection.find_one({"_id": ObjectId(source_id)}, {"thumbnail": 1})
        else:
            return None

        if not doc:
            return None

        thumbnail = doc.get("thumbnail")
        if thumbnail and thumbnail.startswith("s3://"):
            return thumbnail.split("s3://", 1)[-1].split("/", 1)[-1]
        return None
    except Exception as e:
        logger.warning(f"[OG] Could not look up existing thumbnail for {content_type}/{source_id}: {e}")
        return None


def _set_og_image_for_share(share_token: str):
    """Set the OG image for a shared item.
    
    - Presentations/printables/reports: reuse the saved thumbnail S3 key.
    - Diagrams/chats: use the public Citra logo URL directly.
    """
    try:
        share_doc = public_shares_collection.find_one(
            {"share_token": share_token},
            {"content_type": 1, "source_id": 1}
        )
        if not share_doc:
            logger.warning(f"[OG] Share doc not found for {share_token}")
            return

        content_type = share_doc.get("content_type")
        source_id = share_doc.get("source_id")

        # For presentations/printables/reports — reuse the saved thumbnail
        existing_key = _get_existing_thumbnail_s3_key(content_type, source_id)
        if existing_key:
            public_shares_collection.update_one(
                {"share_token": share_token},
                {"$set": {
                    "og_image_s3_key": existing_key,
                    "og_image_url": None,
                    "og_image_generated_at": datetime.utcnow(),
                }}
            )
            logger.info(f"✅ [OG] Reused existing thumbnail for share {share_token}")
            return

        # For diagrams/chats or missing thumbnails — use Citra logo
        public_shares_collection.update_one(
            {"share_token": share_token},
            {"$set": {
                "og_image_s3_key": None,
                "og_image_url": CITRA_OG_LOGO_URL,
                "og_image_generated_at": datetime.utcnow(),
            }}
        )
        logger.info(f"✅ [OG] Set Citra logo as OG image for share {share_token}")

    except Exception as e:
        logger.warning(f"⚠️ [OG] Failed to set OG image for {share_token}: {e}")


def get_upsell_popup_script(content_type: str) -> str:
    """Upsell popup removed — on-prem deployment."""
    return ""


class ShareRequest(BaseModel):
    title: Optional[str] = None
    permission: Literal["read", "edit"] = "read"
    access_type: Literal["public", "restricted"] = "public"
    allowed_emails: Optional[List[str]] = []


class ShareResponse(BaseModel):
    success: bool
    share_token: str
    share_url: str
    content_type: str
    source_id: str
    title: str
    created_at: str
    permission: str # Added field
    embed_code: Optional[str] = None # Added field


# ============================================================================
# SHARE MANAGEMENT ENDPOINTS (Authenticated)
# ============================================================================

@router.post("/share/{content_type}/{source_id}")
async def create_or_get_share(
    content_type: Literal["diagram", "report", "chat", "presentation", "printable"],
    source_id: str,
    request: Request,
    payload: ShareRequest = None
):
    """
    Create a public share link for a diagram, report, or chat.
    If share already exists for this source, returns existing share.
    """
    try:
        # Get user_id from auth middleware
        user_id = getattr(request.state, 'user_id', None)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Ensure latest chat data is persisted before creating/returning share
        if content_type == "chat":
            try:
                from query import wait_for_chat_persistence
                wait_for_chat_persistence(source_id)
            except ImportError:
                logger.warning("Could not import wait_for_chat_persistence from query")
        
        logger.info(f"🔗 [SHARE] Creating share for {content_type}/{source_id} by user {user_id}")
        
        # Get defaults from payload
        req_permission = payload.permission if payload else "read"
        req_access_type = payload.access_type if payload else "public"
        req_allowed_emails = payload.allowed_emails if payload else []

        # Check if share already exists for this source (by this user or the owner)
        existing_share = public_shares_collection.find_one({
            "user_id": user_id,
            "content_type": content_type,
            "source_id": source_id
        })
        
        # If no share by current user, check if the original owner has one
        if not existing_share:
            existing_share = public_shares_collection.find_one({
                "content_type": content_type,
                "source_id": source_id
            })
        
        if existing_share:
            logger.info(f"✅ [SHARE] Found existing share: {existing_share['share_token']}")
            
            # Update existing share if payload provided
            if payload:
                update_fields = {
                    "permission": req_permission,
                    "access_type": req_access_type,
                    "allowed_emails": req_allowed_emails
                }
                if payload.title:
                    update_fields["title"] = payload.title
                    
                public_shares_collection.update_one(
                    {"_id": existing_share["_id"]},
                    {"$set": update_fields}
                )
                existing_share.update(update_fields)

            return {
                "success": True,
                "share_token": existing_share["share_token"],
                "share_url": get_public_share_url(existing_share["share_token"]),
                "content_type": content_type,
                "source_id": source_id,
                "title": existing_share.get("title", "Untitled"),
                "created_at": existing_share["created_at"].isoformat() if isinstance(existing_share["created_at"], datetime) else existing_share["created_at"],
                "permission": existing_share.get("permission", "read"),
                "access_type": existing_share.get("access_type", "public"),
                "allowed_emails": existing_share.get("allowed_emails", []),
                "embed_code": f'<iframe src="{get_public_share_url(existing_share["share_token"])}?embed=true" width="100%" height="600" frameborder="0" allowfullscreen style="border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);"></iframe>',
                "is_existing": True
            }
        
        # Verify source exists and belongs to user (or user has shared access)
        source_doc = None
        title = payload.title if payload and payload.title else "Untitled"
        
        if content_type == "diagram":
            source_doc = diagrams_collection.find_one({
                "_id": ObjectId(source_id),
                "user_id": user_id
            })
            if not source_doc:
                # Check shared access
                shared_doc = diagrams_collection.find_one({"_id": ObjectId(source_id)})
                if shared_doc:
                    try:
                        from services.authorization_service import get_authorization_service
                        auth_service = get_authorization_service()
                        access_result = await auth_service.check_access(
                            user_id=user_id, resource_id=source_id,
                            resource_type="diagram", required_permission="read"
                        )
                        if access_result.get("allowed"):
                            source_doc = shared_doc
                    except Exception as auth_err:
                        logger.warning(f"⚠️ Error checking shared access for diagram: {auth_err}")
            if source_doc:
                title = source_doc.get("diagram_name", title)
                
        elif content_type == "report":
            source_doc = reports_collection.find_one({
                "_id": ObjectId(source_id),
                "user_id": user_id
            })
            if not source_doc:
                shared_doc = reports_collection.find_one({"_id": ObjectId(source_id)})
                if shared_doc:
                    try:
                        from services.authorization_service import get_authorization_service
                        auth_service = get_authorization_service()
                        access_result = await auth_service.check_access(
                            user_id=user_id, resource_id=source_id,
                            resource_type="report", required_permission="read"
                        )
                        if access_result.get("allowed"):
                            source_doc = shared_doc
                    except Exception as auth_err:
                        logger.warning(f"⚠️ Error checking shared access for report: {auth_err}")
            if source_doc:
                title = source_doc.get("title", title)
                
        elif content_type == "chat":
            source_doc = chat_sessions_collection.find_one({
                "_id": source_id,
                "user_id": user_id
            })
            if source_doc:
                title = source_doc.get("title", title)

        elif content_type == "presentation":
             source_doc = presentations_collection.find_one({
                 "_id": source_id,
                 "user_id": user_id
             })
             if not source_doc:
                 shared_doc = presentations_collection.find_one({"_id": source_id})
                 if shared_doc:
                     try:
                         from services.authorization_service import get_authorization_service
                         auth_service = get_authorization_service()
                         access_result = await auth_service.check_access(
                             user_id=user_id, resource_id=source_id,
                             resource_type="presentation", required_permission="read"
                         )
                         if access_result.get("allowed"):
                             source_doc = shared_doc
                     except Exception as auth_err:
                         logger.warning(f"⚠️ Error checking shared access for presentation: {auth_err}")
             if source_doc:
                 title = source_doc.get("title", title)

        elif content_type == "printable":
             source_doc = printables_collection.find_one({
                 "_id": source_id,
                 "user_id": user_id
             })
             if not source_doc:
                 shared_doc = printables_collection.find_one({"_id": source_id})
                 if shared_doc:
                     try:
                         from services.authorization_service import get_authorization_service
                         auth_service = get_authorization_service()
                         access_result = await auth_service.check_access(
                             user_id=user_id, resource_id=source_id,
                             resource_type="printable", required_permission="read"
                         )
                         if access_result.get("allowed"):
                             source_doc = shared_doc
                     except Exception as auth_err:
                         logger.warning(f"⚠️ Error checking shared access for printable: {auth_err}")
             if source_doc:
                 title = source_doc.get("title", title)
        
        if not source_doc:
            raise HTTPException(
                status_code=404, 
                detail=f"{content_type.capitalize()} not found or access denied"
            )
        
        # Generate unique share token
        share_token = generate_share_token()
        
        # Ensure token is unique
        while public_shares_collection.find_one({"share_token": share_token}):
            share_token = generate_share_token()
        
        # Look up creator's user type for tiered branding
        creator_user_type = "free"
        try:
            creator_user = users_collection.find_one({"email": user_id}, {"userType": 1})
            if creator_user:
                creator_user_type = creator_user.get("userType", "free")
        except Exception as ut_err:
            logger.warning(f"Could not look up creator user type: {ut_err}")

        # Create share document
        share_doc = {
            "share_token": share_token,
            "user_id": user_id,
            "content_type": content_type,
            "source_id": source_id,
            "title": title,
            "permission": req_permission,
            "access_type": req_access_type,
            "allowed_emails": req_allowed_emails,
            "creator_user_type": creator_user_type,
            "created_at": datetime.utcnow(),
            "last_accessed_at": None,
            "access_count": 0
        }
        
        public_shares_collection.insert_one(share_doc)
        
        logger.info(f"✅ [SHARE] Created share: {share_token} for {content_type}/{source_id}")
        
        # Set OG image: reuse saved thumbnail or Citra logo (no Playwright)
        _set_og_image_for_share(share_token)
        
        return {
            "success": True,
            "share_token": share_token,
            "share_url": get_public_share_url(share_token),
            "content_type": content_type,
            "source_id": source_id,
            "title": title,
            "created_at": share_doc["created_at"].isoformat(),
            "permission": share_doc["permission"],
            "access_type": share_doc["access_type"],
            "allowed_emails": share_doc["allowed_emails"],
            "embed_code": f'<iframe src="{get_public_share_url(share_token)}?embed=true" width="100%" height="600" frameborder="0" allowfullscreen style="border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);"></iframe>',
            "is_existing": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [SHARE] Failed to create share: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/share/my-shares")
async def list_my_shares(
    request: Request,
    content_type: Optional[str] = Query(None, description="Filter by type: diagram, report, chat, presentation, printable")
):
    """List all shares created by the authenticated user"""
    try:
        user_id = getattr(request.state, 'user_id', None)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        query = {"user_id": user_id}
        if content_type:
            query["content_type"] = content_type
        
        shares = list(public_shares_collection.find(query).sort("created_at", -1))
        
        result = []
        for share in shares:
            result.append({
                "share_token": share["share_token"],
                "share_url": get_public_share_url(share["share_token"]),
                "content_type": share["content_type"],
                "source_id": share["source_id"],
                "title": share.get("title", "Untitled"),
                "created_at": share["created_at"].isoformat() if isinstance(share["created_at"], datetime) else share["created_at"],
                "last_accessed_at": share["last_accessed_at"].isoformat() if share.get("last_accessed_at") and isinstance(share["last_accessed_at"], datetime) else share.get("last_accessed_at"),
                "access_count": share.get("access_count", 0),
                "permission": share.get("permission", "read")
            })
        
        return {
            "success": True,
            "shares": result,
            "count": len(result)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [SHARE] Failed to list shares: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/share/by-source/{content_type}/{source_id}")
async def get_share_by_source(
    content_type: Literal["diagram", "report", "chat", "presentation", "printable"],
    source_id: str,
    request: Request
):
    """Get share info for a specific source if it exists"""
    try:
        user_id = getattr(request.state, 'user_id', None)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        share = public_shares_collection.find_one({
            "user_id": user_id,
            "content_type": content_type,
            "source_id": source_id
        })
        
        if not share:
            return {
                "success": True,
                "exists": False,
                "share": None
            }
        
        return {
            "success": True,
            "exists": True,
            "share": {
                "share_token": share["share_token"],
                "share_url": get_public_share_url(share["share_token"]),
                "content_type": share["content_type"],
                "source_id": share["source_id"],
                "title": share.get("title", "Untitled"),
                "created_at": share["created_at"].isoformat() if isinstance(share["created_at"], datetime) else share["created_at"],
                "access_count": share.get("access_count", 0),
                "permission": share.get("permission", "read"),
                "embed_code": f'<iframe src="{get_public_share_url(share["share_token"])}?embed=true" width="100%" height="600" frameborder="0" allowfullscreen style="border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);"></iframe>'
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [SHARE] Failed to get share: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/share/{share_token}")
async def revoke_share(share_token: str, request: Request):
    """Revoke (delete) a share link"""
    try:
        user_id = getattr(request.state, 'user_id', None)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = public_shares_collection.delete_one({
            "share_token": share_token,
            "user_id": user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Share not found or access denied")
        
        logger.info(f"✅ [SHARE] Revoked share: {share_token}")
        
        return {
            "success": True,
            "message": "Share link revoked successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [SHARE] Failed to revoke share: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# PUBLIC VIEW ENDPOINT (No Authentication Required)
# ============================================================================

def get_edit_button_html(content_type: str, source_id: str, permission: str, share_token: str = None) -> str:
    """Generate Edit button HTML for editable shared content."""
    if permission != "edit" or content_type == "chat" or not share_token:
        return ""
    
    # Deep link to website with collaborate params
    edit_url = f"{WEBSITE_URL}?collaborate_type={content_type}&collaborate_id={source_id}&collaborate_token={share_token}"
    
    return f'''
    <style>
        .edit-button {{
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            background: #8b5cf6;
            color: #fff;
            padding: 10px 20px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            display: flex;
            align-items: center;
            gap: 8px;
            font-family: system-ui, -apple-system, sans-serif;
            transition: transform 0.2s, background 0.2s;
        }}
        .edit-button:hover {{
            transform: translateY(-2px);
            background: #7c3aed;
        }}
        @media (max-width: 768px) {{
            .edit-button {{
                padding: 8px 14px;
                font-size: 13px;
                top: 12px;
                right: 12px;
            }}
            .edit-button svg {{
                width: 14px;
                height: 14px;
            }}
        }}
    </style>
    <a href="{edit_url}" target="_blank" class="edit-button">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
        </svg>
        Edit {content_type.capitalize()}
    </a>
    '''


def build_og_meta_tags(title: str, content_type: str, share_token: str, description: str = "", og_image_url: str = None) -> str:
    """Build Open Graph + Twitter Card meta tags for rich social previews."""
    safe_title = html.escape(title or "Shared Content")
    type_label = content_type.capitalize() if content_type else "Content"
    safe_desc = html.escape(description) if description else f"A {type_label.lower()} created with Citra AI"
    share_url = get_public_share_url(share_token)

    tags = f'''
    <!-- Open Graph -->
    <meta property="og:type" content="article" />
    <meta property="og:title" content="{safe_title}" />
    <meta property="og:description" content="{safe_desc}" />
    <meta property="og:url" content="{html.escape(share_url)}" />
    <meta property="og:site_name" content="Citra AI" />
    <!-- Twitter Card -->
    <meta name="twitter:card" content="{"summary_large_image" if og_image_url else "summary"}" />
    <meta name="twitter:title" content="{safe_title}" />
    <meta name="twitter:description" content="{safe_desc}" />
    '''

    if og_image_url:
        escaped_img = html.escape(og_image_url)
        tags += f'''    <meta property="og:image" content="{escaped_img}" />
    <meta property="og:image:width" content="1200" />
    <meta property="og:image:height" content="630" />
    <meta name="twitter:image" content="{escaped_img}" />
    '''

    return tags


def generate_base_html(title: str, content: str, extra_head: str = "", is_embed: bool = False, creator_user_type: str = "free", content_type: str = "", source_id: str = "", branding: dict = None) -> str:
    """Generate base HTML structure with Citra AI branding or custom user branding.
    Paid creators get a slim 'Powered by' bar or full white-label if configured.
    Free creators get the full header with logo + Read Only badge."""
    
    embed_css = ""
    if is_embed:
        embed_css = """
        <style>
            .header, .header-slim, .footer, .badge, .title, #upsell-popup, .edit-button { display: none !important; }
            .container { 
                max-width: 100% !important; 
                margin: 0 !important; 
                padding: 0 !important; 
            }
            .content-card { 
                border: none !important; 
                background: transparent !important; 
                padding: 0 !important; 
                margin: 0 !important; 
                box-shadow: none !important;
            }
            body {
                background: transparent !important; /* Allow embedding site to show through or container to handle it */
                min-height: auto !important;
            }
            /* Ensure content takes full width */
            .slides-container, .printable-container, .mermaid, #cy, .chat-container {
                width: 100% !important;
                border-radius: 0 !important;
            }
        </style>
        """
    
    is_paid = creator_user_type == "paid"
    
    branding = branding or {}
    has_custom = branding.get("enabled", False)
    logo_src = branding.get("logo_url") if has_custom and branding.get("logo_url") else get_citra_logo_src()
    company_name = branding.get("company_name") if has_custom and branding.get("company_name") else "Citra AI"
    show_powered_by = branding.get("show_powered_by", True) if has_custom else True
    primary_color = branding.get("primary_color") if has_custom and branding.get("primary_color") else "#60a5fa"
    
    custom_colors_css = ""
    if has_custom and primary_color:
        custom_colors_css = f"""
        <style>
            .header a, .header-slim a, .logo, .footer a {{ color: {primary_color} !important; }}
            .badge {{ color: {primary_color} !important; background: {primary_color}33 !important; }}
        </style>
        """
        extra_head += custom_colors_css
    
    
    # Build the download/edit icons + popups (only if content_type and source_id are provided)
    download_btn_html = ""
    edit_btn_html = ""
    download_popup_html = ""
    edit_popup_html = ""
    if content_type and source_id:
        citra_url = f"{WEBSITE_URL}/{html.escape(content_type)}/{html.escape(source_id)}"
        # Format labels based on content type
        if content_type == "presentation":
            format_label = "PPT, PDF"
        elif content_type == "printable":
            format_label = "PDF, Word"
        else:
            format_label = "PDF, Word"
        
        _icon_btn_style = '''
            background: transparent;
            border: 1px solid rgba(255,255,255,0.15);
            color: #94a3b8;
            cursor: pointer;
            padding: 6px 8px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;
            transition: all 0.2s;
        '''
        _hover_on = "this.style.color=\\'#e2e8f0\\';this.style.borderColor=\\'rgba(255,255,255,0.3)\\'"
        _hover_off = "this.style.color=\\'#94a3b8\\';this.style.borderColor=\\'rgba(255,255,255,0.15)\\'"

        edit_btn_html = f'''
        <button id="edit-hint-btn" onclick="toggleEditPopup()" style="{_icon_btn_style}"
           onmouseover="{_hover_on}" onmouseout="{_hover_off}">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
            </svg>
        </button>'''

        download_btn_html = f'''
        <button id="download-hint-btn" onclick="toggleDownloadPopup()" style="{_icon_btn_style}"
           onmouseover="{_hover_on}" onmouseout="{_hover_off}">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
        </button>'''

        _popup_overlay = '''
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            z-index: 100000;
        '''
        _popup_backdrop = '''
            position: absolute; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.5);
        '''
        _popup_card = """
            position: absolute;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid rgba(148,163,184,0.15);
            border-radius: 16px;
            padding: 32px;
            max-width: 420px;
            width: calc(100% - 32px);
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.6);
            font-family: 'Segoe UI', system-ui, sans-serif;
            text-align: center;
        """
        _popup_close = '''
            position: absolute; top: 12px; right: 12px;
            background: transparent; border: none;
            color: #94a3b8; font-size: 24px; cursor: pointer;
            padding: 4px 8px; line-height: 1;
        '''
        _popup_icon_circle = '''
            width: 56px; height: 56px;
            background: rgba(124,58,237,0.15);
            border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            margin: 0 auto 16px;
        '''
        _popup_cta = """
            display: inline-block;
            background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
            color: #ffffff;
            text-decoration: none;
            padding: 12px 28px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
            transition: transform 0.2s, box-shadow 0.2s;
            box-shadow: 0 4px 14px 0 rgba(124,58,237,0.4);
        """
        _cta_hover_on = "this.style.transform=\\'translateY(-2px)\\'"
        _cta_hover_off = "this.style.transform=\\'translateY(0)\\'"

        download_popup_html = f'''
    <div id="download-hint-popup" style="{_popup_overlay}">
        <div onclick="toggleDownloadPopup()" style="{_popup_backdrop}"></div>
        <div style="{_popup_card}">
            <button onclick="toggleDownloadPopup()" style="{_popup_close}">&times;</button>
            <div style="{_popup_icon_circle}">
                <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
            </div>
            <h3 style="color:#f8fafc;font-size:18px;font-weight:600;margin:0 0 12px 0;">Download this {html.escape(content_type)}</h3>
            <p style="color:#cbd5e1;font-size:14px;line-height:1.6;margin:0 0 24px 0;">If you created this, log in to Citra AI to download it as <strong style="color:#e2e8f0">{format_label}</strong> format.</p>
            <a href="{citra_url}" target="_blank" rel="noopener" style="{_popup_cta}"
               onmouseover="{_cta_hover_on}" onmouseout="{_cta_hover_off}">Visit Citra &rarr;</a>
        </div>
    </div>'''

        edit_popup_html = f'''
    <div id="edit-hint-popup" style="{_popup_overlay}">
        <div onclick="toggleEditPopup()" style="{_popup_backdrop}"></div>
        <div style="{_popup_card}">
            <button onclick="toggleEditPopup()" style="{_popup_close}">&times;</button>
            <div style="{_popup_icon_circle}">
                <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                </svg>
            </div>
            <h3 style="color:#f8fafc;font-size:18px;font-weight:600;margin:0 0 12px 0;">Edit this {html.escape(content_type)}</h3>
            <p style="color:#cbd5e1;font-size:14px;line-height:1.6;margin:0 0 24px 0;">If you created this, log in to Citra AI to edit and customize it further.</p>
            <a href="{citra_url}" target="_blank" rel="noopener" style="{_popup_cta}"
               onmouseover="{_cta_hover_on}" onmouseout="{_cta_hover_off}">Visit Citra &rarr;</a>
        </div>
    </div>
    <script>
    function toggleDownloadPopup() {{
        var p = document.getElementById('download-hint-popup');
        if (p) p.style.display = p.style.display === 'none' ? 'block' : 'none';
    }}
    function toggleEditPopup() {{
        var p = document.getElementById('edit-hint-popup');
        if (p) p.style.display = p.style.display === 'none' ? 'block' : 'none';
    }}
    </script>
    '''
    
    # Custom Branding overrides legacy free/paid UI blocks
    if has_custom:
        contact_email = branding.get("contact_email") or ""
        contact_phone = branding.get("contact_phone") or ""
        contact_address = branding.get("contact_address") or ""
        website_url = branding.get("website_url") or ""
        
        # Build the exact UI layout from the CustomBrandingScreen preview
        logo_el = f'<img src="{logo_src}" style="max-width: 100px; max-height: 40px; object-fit: contain;" alt="{html.escape(company_name)} logo" />' if branding.get("logo_url") else f'<div style="width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; background-color: {primary_color}; color: #fff; font-size: 18px; font-weight: bold;">{html.escape(company_name[0].upper() if company_name else "?")}</div>'
        
        header_html = f"""
    <div class="custom-branding-header" style="background-color: {primary_color}10; border: 1px solid {primary_color}; border-radius: 8px; padding: 16px; margin: 16px auto; max-width: 1200px; display: flex; align-items: center; flex-wrap: wrap; gap: 12px;">
        <div style="display: flex; align-items: center; gap: 12px; flex: 1;">
            {logo_el}
            <div style="font-size: 14px; font-weight: 500; color: #e4e4e7;">Shared by {html.escape(company_name)}</div>
        </div>
        <div style="display:flex; align-items:center; gap:10px;">
            {edit_btn_html}
            {download_btn_html}
        </div>
    </div>
    """
        
        # Build the exact Footer UI layout
        footer_info = []
        if contact_email:
            footer_info.append(f'<div style="color: #a1a1aa; font-size: 12px; margin-bottom: 2px;">{html.escape(contact_email)}</div>')
        
        phone_address = " | ".join(filter(None, [contact_phone, contact_address]))
        if phone_address:
            footer_info.append(f'<div style="color: #a1a1aa; font-size: 12px; margin-bottom: 2px;">{html.escape(phone_address)}</div>')
            
        website_link = f'<a href="{html.escape(website_url)}" target="_blank" style="color: {primary_color}; font-size: 12px; text-decoration: none; margin-top: 2px; display: block;">{html.escape(website_url)}</a>' if website_url else ""
        
        footer_info_html = "".join(footer_info)
        
        footer_logo_el = f'<img src="{logo_src}" style="max-width: 50px; max-height: 20px; object-fit: contain; margin-top: 2px;" alt="{html.escape(company_name)} logo" />' if branding.get("logo_url") else ""
        
        footer_html = f"""
    <div class="custom-branding-footer" style="background-color: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 16px; margin: 16px auto 32px; max-width: 1200px; display: flex; align-items: flex-start; flex-wrap: wrap; gap: 12px;">
        {footer_logo_el}
        <div style="flex: 1; min-width: 200px;">
            <div style="font-size: 14px; font-weight: 600; color: #e4e4e7; margin-bottom: 2px;">{html.escape(company_name)}</div>
            {footer_info_html}
            {website_link}
        </div>
        <div style="font-size: 10px; color: #a1a1aa; white-space: nowrap;">{"Powered by Citra AI" if show_powered_by else ""}</div>
    </div>
    """

    # Paid creators: slim single-line bar; Free creators: full header with logo + badge
    elif is_paid:
        
        powered_by_html = f'<span>Powered by <a href="{html.escape(branding.get("website_url") or "https://citra-ai.com")}" target="_blank">{html.escape(company_name or "Citra AI")}</a></span>' if show_powered_by else "<span></span>"
        
        header_html = f"""
    <div class="header-slim">
        {powered_by_html}
        <div style="display:flex;align-items:center;gap:8px;">
            {edit_btn_html}
            {download_btn_html}
        </div>
    </div>"""
        footer_html = ""
    else:
        header_html = f"""
    <div class="header">
        <div class="logo">
            <img src="{logo_src}" alt="{html.escape(company_name)} logo" />
            {html.escape(company_name)}
        </div>
        <div style="display:flex;align-items:center;gap:10px;">
            {edit_btn_html}
            {download_btn_html}
            <div class="badge">Read Only</div>
        </div>
    </div>"""
        footer_text = f'Shared via <a href="{html.escape(branding.get("website_url") or "https://citra-ai.com")}" target="_blank">{html.escape(company_name or "Citra AI")}</a>' if show_powered_by else ""
        footer_html = f"""
    <div class="footer">
        {footer_text}
    </div>""" if footer_text else ""
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title or 'Untitled')} - Citra AI</title>
    <link rel="icon" href="https://citra-ai.com/favicon.ico" type="image/x-icon">
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e4e4e7;
            line-height: 1.6;
        }}
        .header {{
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding: 1rem 2rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .header-slim {{
            text-align: center;
            padding: 0.35rem 1rem;
            font-size: 0.75rem;
            color: #71717a;
            background: rgba(255,255,255,0.03);
            border-bottom: 1px solid rgba(255,255,255,0.06);
        }}
        .header-slim a {{
            color: #60a5fa;
            text-decoration: none;
        }}
        .header-slim a:hover {{
            text-decoration: underline;
        }}
        .logo {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 1.25rem;
            font-weight: 600;
            color: #60a5fa;
        }}
        .logo img {{
            width: 32px;
            height: 32px;
            object-fit: contain;
        }}
        .badge {{
            background: rgba(96, 165, 250, 0.2);
            color: #60a5fa;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 500;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }}
        .content-card {{
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 2rem;
            margin-top: 1rem;
        }}
        .title {{
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 1.5rem;
            color: #f4f4f5;
        }}
        .footer {{
            text-align: center;
            padding: 2rem;
            color: #71717a;
            font-size: 0.875rem;
        }}
        .footer a {{
            color: #60a5fa;
            text-decoration: none;
        }}
        .footer a:hover {{
            text-decoration: underline;
        }}

        /* Mobile responsive */
        @media (max-width: 768px) {{
            .header {{
                padding: 0.75rem 1rem;
            }}
            .logo {{
                font-size: 1rem;
            }}
            .logo img {{
                width: 24px;
                height: 24px;
            }}
            .badge {{
                font-size: 0.65rem;
                padding: 0.2rem 0.5rem;
            }}
            .container {{
                padding: 0.75rem;
            }}
            .content-card {{
                padding: 1rem;
                border-radius: 8px;
                margin-top: 0.5rem;
            }}
            .title {{
                font-size: 1.15rem;
                margin-bottom: 1rem;
            }}
            .footer {{
                padding: 1rem;
                font-size: 0.75rem;
            }}
        }}
    </style>
    {extra_head}
    {embed_css}
</head>
<body>
    {header_html}
    <div class="container">
        <div class="content-card">
            {content}
        </div>
    </div>
    {footer_html}
    {download_popup_html}
    {edit_popup_html}
</body>
</html>"""


def generate_error_html(title: str, message: str) -> str:
    """Generate error page HTML"""
    content = f"""
    <div style="text-align: center; padding: 3rem;">
        <svg style="width: 64px; height: 64px; color: #ef4444; margin-bottom: 1rem;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <line x1="15" y1="9" x2="9" y2="15"/>
            <line x1="9" y1="9" x2="15" y2="15"/>
        </svg>
        <h2 style="color: #ef4444; margin-bottom: 0.5rem;">{html.escape(title or 'Error')}</h2>
        <p style="color: #a1a1aa;">{html.escape(message or '')}</p>
        <a href="https://citra-ai.com" style="display: inline-block; margin-top: 1.5rem; color: #60a5fa; text-decoration: none;">
            Go to Citra AI →
        </a>
    </div>
    """
    return generate_base_html(title, content)


@router.get("/public/{share_token}", response_class=HTMLResponse)
async def view_public_share(share_token: str, embed: bool = False):
    """
    Public endpoint - renders shared content as HTML page.
    No authentication required.
    """
    try:
        # Find share record
        share = public_shares_collection.find_one({"share_token": share_token})
        
        if not share:
            return generate_error_html("Share Not Found", "This share link is invalid or has been revoked.")
        
        # Enforce access restrictions — restricted shares cannot be viewed via
        # the public HTML endpoint; they must be opened through the authenticated app.
        access_type = share.get("access_type", "public")
        allowed_emails = share.get("allowed_emails") or []
        if access_type == "restricted" and allowed_emails:
            return generate_error_html(
                "Restricted Access",
                "This content is restricted to specific users. Please open it from within the Citra AI app."
            )
        
        # Update access stats
        public_shares_collection.update_one(
            {"share_token": share_token},
            {
                "$set": {"last_accessed_at": datetime.utcnow()},
                "$inc": {"access_count": 1}
            }
        )
        
        content_type = share["content_type"]
        source_id = share["source_id"]
        title = share.get("title") or "Shared Content"
        creator_user_type = share.get("creator_user_type") or "free"
        
        # Ensure latest chat data is persisted before rendering public view
        if content_type == "chat":
            try:
                from query import wait_for_chat_persistence
                wait_for_chat_persistence(source_id)
            except ImportError:
                logger.warning("Could not import wait_for_chat_persistence from query")
        
        permission = share.get("permission", "read")
        
        # Custom Branding removed (custom_domain_api.py deleted, feature out of
        # scope). branding stays None — every render function below already
        # treats a missing branding value as "use default Citra AI branding."
        user_id = share.get("user_id")
        branding = None
        
        # Build OG meta tags for social previews
        og_image_url = share.get("og_image_url")  # Direct URL (e.g., Citra logo)
        if not og_image_url:
            og_image_s3_key = share.get("og_image_s3_key")
            if og_image_s3_key:
                try:
                    from bucket import generate_download_url
                    og_image_url = generate_download_url(og_image_s3_key, expiry_seconds=604800)  # 7 days
                except Exception as e:
                    logger.warning(f"[OG] Could not generate presigned URL for {og_image_s3_key}: {e}")
        og_tags = build_og_meta_tags(title, content_type, share_token, og_image_url=og_image_url)
        
        # Fetch and render based on content type
        if content_type == "diagram":
            rendered = await render_diagram_html(source_id, title, permission, share_token=share_token, is_embed=embed, creator_user_type=creator_user_type, branding=branding)
        elif content_type == "report":
            rendered = await render_report_html(source_id, title, permission, share_token=share_token, is_embed=embed, creator_user_type=creator_user_type, branding=branding)
        elif content_type == "chat":
            rendered = await render_chat_html(source_id, title, permission, is_embed=embed, creator_user_type=creator_user_type, branding=branding)
        elif content_type == "presentation":
            rendered = await render_presentation_html(source_id, title, permission, share_token=share_token, is_embed=embed, creator_user_type=creator_user_type, branding=branding)
        elif content_type == "printable":
            rendered = await render_printable_html(source_id, title, permission, share_token=share_token, is_embed=embed, creator_user_type=creator_user_type, branding=branding)
        else:
            return generate_error_html("Unknown Type", "This content type is not supported.")
        
        # Inject OG tags into <head> of the rendered HTML
        if og_tags and isinstance(rendered, str):
            rendered = rendered.replace('</head>', og_tags + '\n</head>', 1)
        
        return rendered
            
    except Exception as e:
        logger.error(f"❌ [SHARE] Failed to render public share: {e}")
        return generate_error_html("Error", "An error occurred while loading this content.")


# ============================================================================
# HTML GENERATION FUNCTIONS
# ============================================================================

async def render_diagram_html(source_id: str, title: str, permission: str = "read", share_token: str = None, is_embed: bool = False, creator_user_type: str = "free", branding: dict = None) -> str:
    """Render diagram as HTML with Mermaid.js or Cytoscape.js based on render_type"""
    try:
        diagram = diagrams_collection.find_one({"_id": ObjectId(source_id)})
        
        if not diagram:
            return generate_error_html("Diagram Not Found", "The original diagram has been deleted.")
        
        render_type = diagram.get("render_type", "mermaid")
        diagram_type = diagram.get("diagram_type", "flowchart")
        description = diagram.get("diagram_description", "")
        
        # Route to appropriate renderer
        if render_type == "cytoscape":
            return await render_cytoscape_diagram(diagram, title, diagram_type, description, permission, share_token, is_embed, creator_user_type, branding)
        else:
            return await render_mermaid_diagram(diagram, title, diagram_type, description, permission, share_token, is_embed, creator_user_type, branding)
        
    except Exception as e:
        logger.error(f"❌ [SHARE] Failed to render diagram: {e}")
        return generate_error_html("Error", "Failed to load diagram.")


async def render_mermaid_diagram(diagram: dict, title: str, diagram_type: str, description: str, permission: str = "read", share_token: str = None, is_embed: bool = False, creator_user_type: str = "free", branding: dict = None) -> str:
    """Render Mermaid diagram as HTML"""
    mermaid_code = diagram.get("mermaid_code", "")
    
    # Escape mermaid code for embedding in HTML
    escaped_code = html.escape(mermaid_code)
    
    extra_head = """
    <script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script>
    <style>
        .mermaid {{
            display: flex;
            justify-content: center;
            background: rgba(255,255,255,0.02);
            border-radius: 8px;
            padding: 2rem;
            overflow-x: auto;
        }}
        .mermaid svg {{
            max-width: 100%;
            height: auto;
        }}
        .diagram-meta {{
            margin-bottom: 1rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        .diagram-type {{
            display: inline-block;
            background: rgba(96, 165, 250, 0.2);
            color: #60a5fa;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            text-transform: uppercase;
        }}
        .diagram-description {{
            margin-top: 0.5rem;
            color: #a1a1aa;
            font-size: 0.875rem;
        }}

        /* Mobile responsive - Mermaid */
        @media (max-width: 768px) {{
            .mermaid {{
                padding: 1rem;
            }}
            .diagram-description {{
                font-size: 0.8rem;
            }}
        }}
    </style>
    """
    
    content = f"""
    <div class="diagram-meta">
        <span class="diagram-type">{html.escape(diagram_type)}</span>
        {f'<p class="diagram-description">{html.escape(description)}</p>' if description else ''}
    </div>
    <div class="mermaid">
{escaped_code}
    </div>
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'dark',
            themeVariables: {{
                primaryColor: '#3b82f6',
                primaryTextColor: '#f4f4f5',
                primaryBorderColor: '#60a5fa',
                lineColor: '#60a5fa',
                secondaryColor: '#1e3a5f',
                tertiaryColor: '#1a1a2e',
                background: '#1a1a2e',
                mainBkg: '#1e3a5f',
                nodeBorder: '#60a5fa',
                clusterBkg: '#16213e',
                titleColor: '#f4f4f5',
                edgeLabelBackground: '#1a1a2e'
            }},
            flowchart: {{
                curve: 'basis',
                padding: 20
            }},
            gantt: {{
                titleTopMargin: 25,
                barHeight: 30,
                barGap: 4,
                topPadding: 50,
                sidePadding: 75
            }}
        }});
    </script>
    """
    
    # Add upsell popup for new user acquisition
    upsell_popup = get_upsell_popup_script('diagram')

    # Add Edit Button
    edit_button = get_edit_button_html('diagram', str(diagram["_id"]), permission, share_token)
    
    return generate_base_html(title, content + upsell_popup + edit_button, extra_head, is_embed, creator_user_type, content_type="diagram", source_id=str(diagram.get("_id", "")), branding=branding)


async def render_cytoscape_diagram(diagram: dict, title: str, diagram_type: str, description: str, permission: str = "read", share_token: str = None, is_embed: bool = False, creator_user_type: str = "free", branding: dict = None) -> str:
    """Render Cytoscape diagram as HTML"""
    import json
    
    cytoscape_data = diagram.get("cytoscape_data", {})
    
    # Ensure we have valid data
    if not cytoscape_data or not cytoscape_data.get("nodes"):
        return generate_error_html("Invalid Diagram", "This diagram has no valid data.")
    
    # Escape JSON for embedding
    cytoscape_json = json.dumps(cytoscape_data)
    
    # Dynamic color palette - colors assigned in order as types appear
    color_palette = [
        "#FF0055", "#0099FF", "#00CC66", "#9D00FF", "#FF6B00",
        "#00D4AA", "#3B82F6", "#8B5CF6", "#10B981", "#F97316",
        "#EF4444", "#EC4899", "#14B8A6", "#A855F7", "#F59E0B",
        "#DC2626", "#6366F1", "#0891B2", "#0EA5E9", "#7C3AED",
        "#2563EB", "#059669", "#06B6D4", "#22C55E", "#EAB308"
    ]
    color_palette_json = json.dumps(color_palette)
    default_color = "#6B7280"
    
    extra_head = """
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js"></script>
    <script src="https://unpkg.com/layout-base/layout-base.js"></script>
    <script src="https://unpkg.com/cose-base/cose-base.js"></script>
    <script src="https://unpkg.com/cytoscape-fcose@2.2.0/cytoscape-fcose.js"></script>
    <style>
        .diagram-meta {
            margin-bottom: 1rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .diagram-type {
            display: inline-block;
            background: rgba(139, 92, 246, 0.2);
            color: #8B5CF6;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            text-transform: uppercase;
        }
        .diagram-description {
            margin-top: 0.5rem;
            color: #a1a1aa;
            font-size: 0.875rem;
        }
        #cy {
            width: 100%;
            height: 500px;
            background: rgba(255,255,255,0.02);
            border-radius: 8px;
        }

        /* Mobile responsive - Cytoscape */
        @media (max-width: 768px) {
            #cy {
                height: 350px;
            }
            .diagram-description {
                font-size: 0.8rem;
            }
        }
    </style>
    """
    
    content = f"""
    <div class="diagram-meta">
        <span class="diagram-type">Network Graph</span>
        {f'<p class="diagram-description">{html.escape(description)}</p>' if description else ''}
    </div>
    <div id="cy"></div>
    <script>
        (function() {{
            const data = {cytoscape_json};
            const colorPalette = {color_palette_json};
            const defaultColor = "{default_color}";
            
            // Dynamic color assignment
            const typeColorMap = {{}};
            let colorIndex = 0;
            
            function getNodeColor(type) {{
                if (!type || type === 'default') return defaultColor;
                const normalizedType = type.toLowerCase();
                if (typeColorMap[normalizedType]) return typeColorMap[normalizedType];
                const color = colorPalette[colorIndex % colorPalette.length];
                typeColorMap[normalizedType] = color;
                colorIndex++;
                return color;
            }}
            
            // Helper to calculate node dimensions based on label
            function calculateNodeSize(label) {{
                const text = label || '';
                const lines = text.split('\\n');
                const maxLineLength = Math.max(...lines.map(l => l.length));
                const lineCount = lines.length;
                const width = Math.min(180, Math.max(80, maxLineLength * 8 + 24));
                const height = Math.max(40, lineCount * 18 + 16);
                return {{ width, height }};
            }}
            
            // Transform data to Cytoscape format
            const elements = [];
            
            // Add nodes with dynamic sizing
            data.nodes.forEach(node => {{
                const nodeType = node.type || 'default';
                const label = node.label || node.id;
                const size = calculateNodeSize(label);
                elements.push({{
                    data: {{
                        id: node.id,
                        label: label,
                        type: nodeType,
                        nodeColor: getNodeColor(nodeType),
                        nodeWidth: size.width,
                        nodeHeight: size.height
                    }}
                }});
            }});
            
            // Add edges
            if (data.edges) {{
                data.edges.forEach((edge, index) => {{
                    elements.push({{
                        data: {{
                            id: edge.id || 'edge-' + index,
                            source: edge.source,
                            target: edge.target,
                            label: edge.label || ''
                        }}
                    }});
                }});
            }}
            
            // Initialize Cytoscape
            const cy = cytoscape({{
                container: document.getElementById('cy'),
                elements: elements,
                style: [
                    {{
                        selector: 'node',
                        style: {{
                            'background-color': 'data(nodeColor)',
                            'background-opacity': 0.95,
                            'width': 'data(nodeWidth)',
                            'height': 'data(nodeHeight)',
                            'shape': 'roundrectangle',
                            'label': 'data(label)',
                            'text-valign': 'center',
                            'text-halign': 'center',
                            'font-size': '11px',
                            'color': '#FFFFFF',
                            'text-wrap': 'wrap',
                            'text-max-width': '70px',
                            'border-width': 2,
                            'border-color': '#fff'
                        }}
                    }},
                    {{
                        selector: 'node[type = "central"]',
                        style: {{
                            'shape': 'ellipse',
                            'width': 100,
                            'height': 60,
                            'font-size': '14px',
                            'font-weight': 'bold'
                        }}
                    }},
                    {{
                        selector: 'edge',
                        style: {{
                            'width': 2,
                            'line-color': '#60a5fa',
                            'target-arrow-color': '#60a5fa',
                            'target-arrow-shape': 'triangle',
                            'curve-style': 'bezier',
                            'label': 'data(label)',
                            'font-size': '10px',
                            'text-rotation': 'autorotate',
                            'text-background-color': '#1a1a2e',
                            'text-background-opacity': 0.9,
                            'text-background-padding': '2px',
                            'color': '#e4e4e7'
                        }}
                    }}
                ],
                layout: {{
                    name: 'fcose',
                    animate: false,
                    fit: true,
                    padding: 50,
                    nodeRepulsion: 5000,
                    idealEdgeLength: 150,
                    nodeDimensionsIncludeLabels: true
                }},
                minZoom: 0.2,
                maxZoom: 3
            }});
        }})();
    </script>
    """
    
    # Add upsell popup for new user acquisition
    upsell_popup = get_upsell_popup_script('diagram')

    # Add Edit Button
    edit_button = get_edit_button_html('diagram', str(diagram["_id"]), permission, share_token)
    
    return generate_base_html(title, content + upsell_popup + edit_button, extra_head, is_embed, creator_user_type, content_type="diagram", source_id=str(diagram.get("_id", "")), branding=branding)


async def render_report_html(source_id: str, title: str, permission: str = "read", share_token: str = None, is_embed: bool = False, creator_user_type: str = "free", branding: dict = None) -> str:
    """Render report as HTML"""
    try:
        report = reports_collection.find_one({"_id": ObjectId(source_id)})
        
        if not report:
            return generate_error_html("Report Not Found", "The original report has been deleted.")
        
        # Inject Presigned URLs
        if "pages" in report:
            report["pages"] = image_processor.inject_presigned_urls_report(report["pages"])
        
        pages = report.get("pages", [])
        
        # Filter out hidden pages for public share
        pages = [p for p in pages if not p.get("hidden", False)]
        
        extra_head = """
        <style>
            .report-section {
                margin-bottom: 2rem;
                padding-bottom: 2rem;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            .report-section:last-child {
                border-bottom: none;
                margin-bottom: 0;
                padding-bottom: 0;
            }
            .section-title {
                font-size: 1.25rem;
                font-weight: 600;
                color: #f4f4f5;
                margin-bottom: 1rem;
            }
            .section-content {
                color: #d4d4d8;
            }
            .section-content p {
                margin-bottom: 1rem;
            }
            .section-content ul, .section-content ol {
                margin-left: 1.5rem;
                margin-bottom: 1rem;
            }
            .section-content li {
                margin-bottom: 0.5rem;
            }
            .section-content h1, .section-content h2, .section-content h3 {
                color: #f4f4f5;
                margin-top: 1.5rem;
                margin-bottom: 0.75rem;
            }
            .section-content a {
                color: #60a5fa;
            }
            .section-content blockquote {
                border-left: 3px solid #60a5fa;
                padding-left: 1rem;
                margin: 1rem 0;
                color: #a1a1aa;
            }
            .section-content code {
                background: rgba(255,255,255,0.1);
                padding: 0.125rem 0.375rem;
                border-radius: 4px;
                font-family: monospace;
            }
            .section-content pre {
                background: rgba(0,0,0,0.3);
                padding: 1rem;
                border-radius: 8px;
                overflow-x: auto;
                margin: 1rem 0;
            }
            .section-content table {
                width: 100%;
                border-collapse: collapse;
                margin: 1rem 0;
            }
            .section-content th, .section-content td {
                border: 1px solid rgba(255,255,255,0.1);
                padding: 0.75rem;
                text-align: left;
            }
            .section-content th {
                background: rgba(255,255,255,0.05);
            }
            .section-content img {
                max-width: 100%;
                height: auto;
                display: block;
                margin: 10px auto;
            }
            
            #print-fab {
                position: fixed;
                bottom: 24px;
                right: 24px;
                background: #f4f4f5;
                color: #18181b;
                border: none;
                border-radius: 50px;
                padding: 12px 24px;
                font-size: 16px;
                font-weight: 600;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                display: flex;
                align-items: center;
                gap: 8px;
                cursor: pointer;
                z-index: 9990;
                transition: transform 0.2s, background 0.2s;
            }
            #print-fab:hover { 
                transform: translateY(-2px);
                background: #fff;
            }
            
            @media print {
                body { background: white; color: black; }
                .container { max-width: 100%; margin: 0; padding: 0; }
                .content-card { 
                    background: transparent; 
                    border: none; 
                    padding: 0; 
                    margin: 0;
                    color: black;
                }
                .header, .footer, .edit-button, #upsell-popup, #print-fab { display: none !important; }
                .section-title, .title { color: black; }
                .section-content { color: #333; }
                .section-content h1, .section-content h2, .section-content h3 { color: black; }
                .section-content code { background: #f4f4f5; color: black; border: 1px solid #ddd; }
                .section-content pre { background: #f4f4f5; color: black; border: 1px solid #ddd; }
                .section-content th, .section-content td { border-color: #ddd; }
                .section-content th { background: #f4f4f5; }
                .section-content img { max-width: 100%; height: auto; display: block; margin: 10px auto; }
                a { text-decoration: underline; color: #2563eb; }
            }

            /* Mobile responsive - Report */
            @media (max-width: 768px) {
                .report-section {
                    margin-bottom: 1.25rem;
                    padding-bottom: 1.25rem;
                }
                .section-title {
                    font-size: 1.1rem;
                }
                .section-content img {
                    max-width: 100% !important;
                    height: auto !important;
                }
                .section-content table {
                    display: block;
                    overflow-x: auto;
                    -webkit-overflow-scrolling: touch;
                }
                .section-content pre {
                    font-size: 0.8rem;
                    padding: 0.75rem;
                }
                .section-content th, .section-content td {
                    padding: 0.5rem;
                    font-size: 0.875rem;
                }
                #print-fab {
                    padding: 10px 16px;
                    font-size: 14px;
                    bottom: 16px;
                    right: 16px;
                }
            }
        </style>
        """
        
        # Build content from pages
        pages_html = ""

        # Sort pages by order
        sorted_pages = sorted(pages, key=lambda p: p.get("order", 0))

        # ── Letterhead / header / footer chrome (mirrors generateReportHTML.js) ──
        _meta = report.get("metadata") or {}
        _lh = _meta.get("letterheadConfig") or {}
        _hdr = _meta.get("headerConfig") or {}
        _ftr = _meta.get("footerConfig") or {}
        _total_pages = len(sorted_pages)
        _report_title = report.get("title", "")

        def _resolve_ph(text, page_num):
            from datetime import date as _date
            return (text or "") \
                .replace("{date}", _date.today().strftime("%m/%d/%Y")) \
                .replace("{page}", str(page_num)) \
                .replace("{total}", str(_total_pages)) \
                .replace("{title}", _report_title) \
                .replace("{author}", _meta.get("author") or "")

        _lh_html = ""
        if _lh.get("enabled"):
            _contact = html.escape(" • ".join(x for x in [_lh.get("phone"), _lh.get("email"), _lh.get("website")] if x))
            _addr = html.escape(_lh.get("address") or "").replace("\n", "<br/>")
            _logo = f'<img src="{html.escape(_lh.get("logoUrl") or "")}" style="max-height:64px;max-width:160px;object-fit:contain;" alt=""/>' if _lh.get("logoUrl") else ''
            _name = f'<div style="font-size:1.35em;font-weight:700;color:#1f2937;">{html.escape(_lh.get("companyName") or "")}</div>' if _lh.get("companyName") else ''
            _addr_div = f'<div style="font-size:0.85em;color:#4b5563;line-height:1.45;">{_addr}</div>' if _addr else ''
            _contact_div = f'<div style="font-size:0.85em;color:#4b5563;">{_contact}</div>' if _contact else ''
            _rule = '<div style="height:2px;background:#1f2937;margin:10px 0 24px 0;"></div>' if _lh.get("showRule", True) else ''
            _lh_html = (
                f'<div style="display:flex;align-items:center;gap:18px;margin-bottom:6px;">{_logo}'
                f'<div style="flex:1;">{_name}{_addr_div}{_contact_div}</div></div>{_rule}'
            )

        def _hf_bar(cfg, page_num, top):
            border = ("border-bottom:1px solid #e5e7eb;padding-bottom:6px;margin-bottom:18px;" if top
                      else "border-top:1px solid #e5e7eb;padding-top:6px;margin-top:24px;")
            logo = (
                f'<img src="{html.escape(cfg.get("logoUrl") or "")}" style="max-height:20px;max-width:80px;'
                f'object-fit:contain;margin-right:6px;" alt=""/>'
                if cfg.get("showLogo") and cfg.get("logoUrl") else ""
            )
            return (
                f'<div style="display:flex;align-items:center;font-size:0.78em;color:#6b7280;{border}">'
                f'<span style="flex:1;text-align:left;display:flex;align-items:center;">{logo}'
                f'{html.escape(_resolve_ph(cfg.get("leftContent"), page_num))}</span>'
                f'<span style="flex:1;text-align:center;">{html.escape(_resolve_ph(cfg.get("centerContent"), page_num))}</span>'
                f'<span style="flex:1;text-align:right;">{html.escape(_resolve_ph(cfg.get("rightContent"), page_num))}</span>'
                f'</div>'
            )

        for _idx, page in enumerate(sorted_pages):
            page_title = page.get("title", "Untitled Section")
            page_content = page.get("content", "")
            _page_num = _idx + 1
            _is_first = _idx == 0
            _show_lh = _lh_html and (_is_first or _lh.get("allPages"))
            _show_hdr = _hdr.get("enabled") and (not _is_first or _hdr.get("showOnFirstPage"))
            _show_ftr = _ftr.get("enabled") and (not _is_first or _ftr.get("showOnFirstPage", True))

            pages_html += f"""
            <div class="report-section">
                {_lh_html if _show_lh else ''}
                {_hf_bar(_hdr, _page_num, True) if _show_hdr else ''}
                <h2 class="section-title">{html.escape(page_title)}</h2>
                <div class="section-content">{page_content}</div>
                {_hf_bar(_ftr, _page_num, False) if _show_ftr else ''}
            </div>
            """
        
        if not pages_html:
            pages_html = "<p style='color: #71717a; text-align: center;'>This report is empty.</p>"
        
        # Add upsell popup for new user acquisition
        upsell_popup = get_upsell_popup_script('report')
        
        # Add Edit Button
        edit_button = get_edit_button_html('report', str(report["_id"]), permission, share_token)
        
        # Print Button
        print_fab = """
        <button id="print-fab" onclick="window.print()">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="6 9 6 2 18 2 18 9"></polyline>
                <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path>
                <rect x="6" y="14" width="12" height="8"></rect>
            </svg>
            Print
        </button>
        """
        
        return generate_base_html(title, pages_html + upsell_popup + edit_button + print_fab, extra_head, is_embed, creator_user_type, content_type='report', source_id=source_id, branding=branding)
        
    except Exception as e:
        logger.error(f"❌ [SHARE] Failed to render report: {e}")
        return generate_error_html("Error", "Failed to load report.")


async def render_chat_html(source_id: str, title: str, permission: str = "read", is_embed: bool = False, creator_user_type: str = "free", branding: dict = None) -> str:
    """Render chat conversation as HTML"""
    try:
        # Get chat session
        chat_session = chat_sessions_collection.find_one({"_id": source_id})
        
        if not chat_session:
            return generate_error_html("Chat Not Found", "The original chat has been deleted.")
        
        # Get message pairs
        messages = list(message_pairs_collection.find({
            "chat_session_id": source_id
        }).sort("userMessage.createdAt", 1))
        
        extra_head = """
        <style>
            .chat-container {
                display: flex;
                flex-direction: column;
                gap: 1rem;
            }
            .message {
                max-width: 85%;
                padding: 1rem;
                border-radius: 12px;
            }
            .message-user {
                align-self: flex-end;
                background: #3b82f6;
                color: white;
                border-bottom-right-radius: 4px;
            }
            .message-ai {
                align-self: flex-start;
                background: rgba(255,255,255,0.1);
                border-bottom-left-radius: 4px;
            }
            .message-label {
                font-size: 0.75rem;
                opacity: 0.7;
                margin-bottom: 0.25rem;
            }
            .message-content {
                white-space: pre-wrap;
                word-wrap: break-word;
            }
            .message-content p {
                margin-bottom: 0.75rem;
            }
            .message-content p:last-child {
                margin-bottom: 0;
            }
            .message-content code {
                background: rgba(0,0,0,0.2);
                padding: 0.125rem 0.375rem;
                border-radius: 4px;
                font-family: monospace;
                font-size: 0.875rem;
            }
            .message-content pre {
                background: rgba(0,0,0,0.3);
                padding: 1rem;
                border-radius: 8px;
                overflow-x: auto;
                margin: 0.5rem 0;
            }
            .message-content ul, .message-content ol {
                margin-left: 1.25rem;
                margin-bottom: 0.75rem;
            }
            .message-content li {
                margin-bottom: 0.25rem;
            }
            .message-time {
                font-size: 0.7rem;
                opacity: 0.5;
                margin-top: 0.5rem;
            }
            .empty-chat {
                text-align: center;
                padding: 3rem;
                color: #71717a;
            }

            /* Mobile responsive - Chat */
            @media (max-width: 768px) {
                .message {
                    max-width: 92%;
                    padding: 0.75rem;
                    font-size: 0.925rem;
                }
                .message-content pre {
                    font-size: 0.8rem;
                    padding: 0.75rem;
                }
                .empty-chat {
                    padding: 2rem;
                }
            }
        </style>
        """
        
        # Build chat messages HTML
        chat_html = '<div class="chat-container">'
        
        if not messages:
            chat_html += '<div class="empty-chat">No messages in this conversation.</div>'
        else:
            for msg in messages:
                # Use same field names as the API returns (userMessage and botReply)
                user_msg = msg.get("userMessage", {})
                bot_msg = msg.get("botReply", {})
                
                # User message
                if user_msg.get("content"):
                    user_content = html.escape(user_msg.get("content", ""))
                    user_time = user_msg.get("createdAt", "")
                    chat_html += f"""
                    <div class="message message-user">
                        <div class="message-label">You</div>
                        <div class="message-content">{user_content}</div>
                        {f'<div class="message-time">{user_time}</div>' if user_time else ''}
                    </div>
                    """
                
                # Bot response (field is botReply, not aiResponse)
                if bot_msg.get("content"):
                    bot_content = bot_msg.get("content", "")
                    # Basic markdown-like processing for bot responses
                    bot_content = process_markdown_basic(bot_content)
                    bot_time = bot_msg.get("createdAt", "")
                    chat_html += f"""
                    <div class="message message-ai">
                        <div class="message-label">Citra AI</div>
                        <div class="message-content">{bot_content}</div>
                        {f'<div class="message-time">{bot_time}</div>' if bot_time else ''}
                    </div>
                    """
        
        chat_html += '</div>'
        
        return generate_base_html(title, chat_html, extra_head, is_embed, creator_user_type, content_type='chat', source_id=source_id, branding=branding)
        
    except Exception as e:
        logger.error(f"❌ [SHARE] Failed to render chat: {e}")
        return generate_error_html("Error", "Failed to load chat.")


def _render_rich_text(content: str, styles: dict, base_font_size: float) -> str:
    """Render text with character-level Fabric.js styles.
    
    Fabric.js styles dict format:
    {
        "0": {  // line index
            "0": { "fontWeight": "bold", "fill": "#ff0000", ... },  // char index
            "1": { "fontStyle": "italic" },
            ...
        },
        ...
    }
    """
    if not content or not styles:
        return html.escape(str(content or ""))
    
    try:
        lines = content.split('\n')
        result_parts = []
        
        for line_idx, line in enumerate(lines):
            line_styles = styles.get(str(line_idx), {})
            
            if not line_styles:
                # No character-level styles for this line
                result_parts.append(html.escape(line))
            else:
                # Build styled spans for this line
                line_parts = []
                i = 0
                while i < len(line):
                    char_style = line_styles.get(str(i), {})
                    if not isinstance(char_style, dict):
                        char_style = {}
                    
                    # Collect consecutive chars with same style
                    j = i + 1
                    while j < len(line):
                        next_style = line_styles.get(str(j), {})
                        if not isinstance(next_style, dict):
                            next_style = {}
                        if next_style == char_style:
                            j += 1
                        else:
                            break
                    
                    segment = html.escape(line[i:j])
                    
                    if char_style:
                        css_parts = []
                        if char_style.get('fontWeight') == 'bold' or char_style.get('bold'):
                            css_parts.append('font-weight: bold')
                        if char_style.get('fontStyle') == 'italic' or char_style.get('italic'):
                            css_parts.append('font-style: italic')
                        if char_style.get('underline') or char_style.get('textDecoration') == 'underline':
                            css_parts.append('text-decoration: underline')
                        if char_style.get('linethrough') or char_style.get('textDecoration') == 'line-through':
                            css_parts.append('text-decoration: line-through')
                        fill = char_style.get('fill') or char_style.get('color')
                        if fill:
                            css_parts.append(f'color: {fill}')
                        if char_style.get('fontSize'):
                            try:
                                cs_font = float(char_style['fontSize'])
                                css_parts.append(f'font-size: {cs_font / base_font_size:.2f}em')
                            except (ValueError, TypeError):
                                pass
                        if char_style.get('fontFamily'):
                            css_parts.append(f"font-family: {char_style['fontFamily']}")
                        
                        if css_parts:
                            segment = f'<span style="{"; ".join(css_parts)}">{segment}</span>'
                    
                    line_parts.append(segment)
                    i = j
                
                result_parts.append(''.join(line_parts))
            
            if line_idx < len(lines) - 1:
                result_parts.append('<br/>')
        
        return ''.join(result_parts)
    except Exception as e:
        logger.warning(f"⚠️ [SHARE] Rich text rendering failed, falling back to plain text: {e}")
        return html.escape(str(content or ""))


async def render_printable_html(source_id: str, title: str, permission: str = "read", share_token: str = None, is_embed: bool = False, creator_user_type: str = "free", branding: dict = None) -> str:
    """Render printable as HTML pages (A4 layout)"""
    try:
        printable = printables_collection.find_one({"_id": source_id})
        
        if not printable:
            # Try ObjectId if string lookup fails (legacy support)
            try:
                printable = printables_collection.find_one({"_id": ObjectId(source_id)})
            except (ValueError, TypeError):  # best-effort: source_id not a valid ObjectId, legacy lookup skipped
                pass
                
        if not printable:
             return generate_error_html("Printable Not Found", "The original document has been deleted.")
        
        # Inject presigned URLs for images
        if "PAGES" in printable:
            printable["PAGES"] = image_processor.inject_presigned_urls_presentation(printable["PAGES"])
        
        pages = printable.get("PAGES", [])
        
        # Filter out hidden pages for public share
        pages = [p for p in pages if not p.get("hidden", False)]
        
        # Consistent Canvas Size for A4 (794x1123 px at 96 DPI)
        CANVAS_WIDTH = 794.0
        CANVAS_HEIGHT = 1123.0
        
        global_style = printable.get("style") or {}
        global_bg = global_style.get("PAGEBackground", "#ffffff") or "#ffffff"
        
        extra_head = """
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js"></script>
        <style>
            .printable-container {
                display: flex;
                flex-direction: column;
                gap: 2rem;
                align-items: center;
                padding: 2rem 0;
                background: #52525b; /* Dark neutral background for contrast */
            }
            .page-wrapper {
                width: 100%;
                max-width: 210mm; /* True A4 width */
                min-height: 297mm; /* True A4 height */
                background: white;
                box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
                position: relative;
                overflow: hidden;
                aspect-ratio: 210 / 297;
                box-sizing: border-box;
                container-type: inline-size; /* Enable cqw units for responsive text scaling */
            }
            /* Print overrides */
            @media print {
                body { background: white; }
                .printable-container { padding: 0; background: white; gap: 0; display: block; }
                .page-wrapper { 
                    box-shadow: none; 
                    margin: 0; 
                    page-break-after: always;
                    width: 100%;
                    min-height: 100vh; 
                }
                .header, .footer, .edit-button, #upsell-popup { display: none !important; }
            }
            
            .page-element {
                position: absolute;
                box-sizing: border-box;
            }
            .page-text {
                font-family: 'Inter', system-ui, sans-serif;
                white-space: pre-wrap;
                line-height: 1.5;
            }
            .page-image {
                object-fit: cover;
            }
            .page-svg-diagram {
                overflow: hidden;
            }
            .page-svg-diagram svg {
                width: 100%;
                height: 100%;
                display: block;
            }
            .page-number {
                position: absolute;
                bottom: 20px;
                right: 30px;
                font-size: 10px;
                color: #9ca3af;
                z-index: 999;
            }
            
            /* Focus Mode Overlay Styles */
            #focus-overlay {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                background: #18181b;
                z-index: 100000;
                align-items: center;
                justify-content: center;
            }
            #focus-content {
                width: 100%;
                height: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                position: relative;
                overflow: hidden;
            }
            .focus-page {
                display: none;
                height: 100vh;
                width: auto;
                aspect-ratio: 210/297;
                background: white;
                box-shadow: 0 0 50px rgba(0,0,0,0.5);
                container-type: inline-size;
                min-height: unset; /* Override .page-wrapper min-height */
                max-width: unset; /* Override .page-wrapper max-width */
            }
            .focus-page.active {
                display: block;
            }
            
            /* Scale content to fit in focus page */
            .focus-page .page-element {
                /* content is already % based, so it scales with container! */
            }
            
            .focus-controls {
                position: absolute;
                top: 50%;
                left: 0;
                width: 100%;
                transform: translateY(-50%);
                display: flex;
                justify-content: space-between;
                padding: 0 40px;
                box-sizing: border-box;
                z-index: 100002;
                opacity: 0;
                transition: opacity 0.3s;
                pointer-events: none; /* Let clicks pass through container */
            }
            #focus-overlay:hover .focus-controls {
                opacity: 1;
            }
            .control-btn {
                pointer-events: auto;
                background: rgb(19, 24, 43);
                border: gray solid 1px;
                color: white;
                padding: 10px;
                border-radius: 50%;
                cursor: pointer;
                width: 44px;
                height: 44px;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: background 0.2s;
            }
            .control-btn:hover {
                background: rgba(0, 0, 0, 0.6);
            }
            .close-btn {
                position: absolute;
                top: 20px;
                right: 20px;
                z-index: 100002;
                background: transparent;
                border: none;
                color: rgba(255, 255, 255, 0.6);
                cursor: pointer;
            }
             .close-btn:hover { color: white; }
             
             #present-fab {
                position: fixed;
                bottom: 24px;
                right: 24px;
                background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                color: white;
                border: none;
                border-radius: 50px;
                padding: 12px 24px;
                font-size: 16px;
                font-weight: 600;
                box-shadow: 0 10px 25px -5px rgba(16, 185, 129, 0.5);
                display: flex;
                align-items: center;
                gap: 8px;
                cursor: pointer;
                z-index: 9990;
                transition: transform 0.2s;
             }
             #present-fab:hover { transform: translateY(-2px); }
             
             /* Hide FAB in fullscreen */
             :fullscreen #present-fab { display: none; }
             
             @media print {
                 #present-fab, #focus-overlay { display: none !important; }
             }

             /* Mobile responsive - Printable */
             @media (max-width: 768px) {
                .container {
                    padding: 0.5rem !important;
                }
                .content-card {
                    padding: 0 !important;
                    border: none !important;
                    background: transparent !important;
                    box-shadow: none !important;
                }
                .title {
                    padding: 0 0.5rem !important;
                    font-size: 1.1rem !important;
                    margin-bottom: 0.75rem !important;
                }
                .printable-container {
                    padding: 0.5rem 0 !important;
                    gap: 1rem !important;
                }
                .page-wrapper {
                    min-height: auto !important;
                    border-radius: 4px;
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
                }
                #present-fab {
                    padding: 10px 16px !important;
                    font-size: 14px !important;
                    bottom: 16px !important;
                    right: 16px !important;
                }
                .focus-controls {
                    opacity: 1 !important;
                    padding: 0 10px !important;
                }
             }
        </style>
        <script>
            let currentPageIdx = 0;
            let totalPages = 0;
            
            function startFocusMode() {
                const overlay = document.getElementById('focus-overlay');
                const container = document.getElementById('focus-content');
                container.innerHTML = ''; 
                
                // Clone pages
                const pages = document.querySelectorAll('.page-wrapper');
                totalPages = pages.length;
                currentPageIdx = 0;
                
                pages.forEach((page, index) => {
                    const clone = page.cloneNode(true);
                    clone.classList.add('focus-page');
                    clone.style.width = ''; 
                    clone.style.minHeight = '';
                    
                    if (index === 0) clone.classList.add('active');
                    container.appendChild(clone);
                    
                    // Re-render charts
                    const clonedCanvases = clone.querySelectorAll('canvas[data-chart-id]');
                    clonedCanvases.forEach(canvas => {
                        const chartId = canvas.getAttribute('data-chart-id');
                        if (window.chartConfigs && window.chartConfigs[chartId]) {
                            new Chart(canvas, window.chartConfigs[chartId]);
                        }
                    });
                });
                
                overlay.style.display = 'flex';
                
                if (document.documentElement.requestFullscreen) {
                    document.documentElement.requestFullscreen();
                }
                
                document.addEventListener('keydown', handleKeyNav);
            }
            
            function endFocusMode() {
                const overlay = document.getElementById('focus-overlay');
                overlay.style.display = 'none';
                if (document.exitFullscreen && document.fullscreenElement) {
                    document.exitFullscreen();
                }
                document.removeEventListener('keydown', handleKeyNav);
            }
            
            function showPage(index) {
                const pages = document.querySelectorAll('.focus-page');
                if (index < 0) index = 0;
                if (index >= pages.length) index = pages.length - 1;
                
                currentPageIdx = index;
                
                pages.forEach((p, i) => {
                    if (i === currentPageIdx) p.classList.add('active');
                    else p.classList.remove('active');
                });
            }
            
            function nextPage() {
                if (currentPageIdx < totalPages - 1) showPage(currentPageIdx + 1);
            }
            
            function prevPage() {
                if (currentPageIdx > 0) showPage(currentPageIdx - 1);
            }
            
            function handleKeyNav(e) {
                if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === 'Space') nextPage();
                if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') prevPage();
                if (e.key === 'Escape') endFocusMode();
            }
            
            document.addEventListener('fullscreenchange', () => {
                if (!document.fullscreenElement) {
                     const overlay = document.getElementById('focus-overlay');
                     overlay.style.display = 'none';
                }
            });
        </script>
        """

        pages_html = '<div class="printable-container">'
        
        for index, page in enumerate(pages):
            elements = page.get("elements", [])
            # Sort by zIndex
            elements.sort(key=lambda x: x.get('zIndex', 0))
            
            # Page Background
            bg_color = page.get("backgroundColor") or global_bg
            page_style = f"background-color: {bg_color};"
            
            elements_html = ""
            
            for el in elements:
              try:
                # Coordinate mapping (pixels) - ensure numeric types
                try:
                    x = float(el.get('x', 0) or 0)
                except (ValueError, TypeError):
                    x = 0.0
                try:
                    y = float(el.get('y', 0) or 0)
                except (ValueError, TypeError):
                    y = 0.0
                try:
                    w = float(el.get('width', 0) or 0)
                except (ValueError, TypeError):
                    w = 0.0
                try:
                    h = float(el.get('height', 0) or 0)
                except (ValueError, TypeError):
                    h = 0.0
                
                # Handle scaleX/scaleY for complex shapes (polygon, star, arrow, etc.)
                try:
                    scale_x = float(el.get('scaleX', 1) or 1)
                except (ValueError, TypeError):
                    scale_x = 1.0
                try:
                    scale_y = float(el.get('scaleY', 1) or 1)
                except (ValueError, TypeError):
                    scale_y = 1.0
                
                effective_w = w * scale_x
                effective_h = h * scale_y
                
                # Use % based on the 794x1123 canvas to scale perfectly within the 210mm div
                left_pct = (x / CANVAS_WIDTH) * 100
                top_pct = (y / CANVAS_HEIGHT) * 100
                width_pct = (effective_w / CANVAS_WIDTH) * 100
                height_pct = (effective_h / CANVAS_HEIGHT) * 100
                
                style = f"left: {left_pct}%; top: {top_pct}%; width: {width_pct}%; height: {height_pct}%; z-index: {el.get('zIndex', 0) or 0}; opacity: {el.get('opacity', 1) or 1};"
                
                if el.get('rotation'):
                    style += f" transform: rotate({el['rotation']}deg); transform-origin: top left;"

                if el.get("type") == "text":
                    content = el.get("content") or el.get("text") or ""
                    if not isinstance(content, str):
                        content = str(content)
                    fontSize = el.get("fontSize") or 12
                    if isinstance(fontSize, str):
                        try:
                            fontSize = float(fontSize.replace('px', '').replace('pt', '').strip())
                        except (ValueError, AttributeError):
                            fontSize = 12
                    
                    color = el.get("color") or el.get("fill") or "#000000"
                    textAlign = el.get('textAlign') or 'left'
                    fontWeight = el.get('fontWeight') or 'normal'
                    fontFamily = el.get('fontFamily') or 'Inter, system-ui, sans-serif'
                    fontStyle = el.get('fontStyle') or 'normal'
                    textDecoration = el.get('textDecoration') or 'none'
                    letterSpacing = el.get('letterSpacing') or 0
                    lineHeight = el.get('lineHeight') or 1.5
                    
                    # Ensure numeric types
                    try:
                        letterSpacing = float(letterSpacing) if letterSpacing else 0
                    except (ValueError, TypeError):
                        letterSpacing = 0
                    try:
                        lineHeight = float(lineHeight) if lineHeight else 1.5
                    except (ValueError, TypeError):
                        lineHeight = 1.5
                    
                    # Font scaling: Use container query width units for responsiveness
                    # cqw = 1% of container's inline size (width)
                    # page-wrapper has container-type: inline-size, so cqw scales with page width
                    # This ensures text scales proportionally on mobile screens
                    font_cqw = (float(fontSize) / CANVAS_WIDTH) * 100
                    
                    style += f" font-size: {font_cqw:.2f}cqw; color: {color}; text-align: {textAlign}; font-weight: {fontWeight};"
                    style += f" font-family: {fontFamily}; font-style: {fontStyle}; text-decoration: {textDecoration};"
                    if letterSpacing:
                        letter_spacing_cqw = (letterSpacing / CANVAS_WIDTH) * 100
                        style += f" letter-spacing: {letter_spacing_cqw:.2f}cqw;"
                    style += f" line-height: {lineHeight};"
                    
                    # Render rich text with character-level styles if available
                    if el.get('styles') and isinstance(el.get('styles'), dict):
                        elements_html += f'<div class="page-element page-text" style="{style}">{_render_rich_text(content, el["styles"], fontSize)}</div>'
                    else:
                        elements_html += f'<div class="page-element page-text" style="{style}">{html.escape(content or "")}</div>'
                    
                elif el.get("type") == "image":
                    src = el.get("src") or ""
                    elements_html += f'<img class="page-element page-image" src="{src}" style="{style}" loading="lazy" />'

                elif el.get("type") == "svg_diagram":
                    # Full-slot inline SVG diagram (org charts, process flows, infographics).
                    # The raw SVG markup lives in `svgContent` (already sanitized on save).
                    # Embed it inline and resolve `currentColor` to the element accent so
                    # themed colors render — mirrors PrintableCanvas's svg_diagram path.
                    raw_svg = el.get("svgContent") or ""
                    if isinstance(raw_svg, str) and raw_svg.strip():
                        accent = el.get("fillColor") or el.get("fill") or el.get("color") or "#3B82F6"
                        themed_svg = raw_svg.replace("currentColor", accent)
                        elements_html += f'<div class="page-element page-svg-diagram" style="{style}">{themed_svg}</div>'

                elif el.get("type") == "shape":
                     fill = el.get("fill") or "#cccccc"
                     stroke = el.get("stroke") or "transparent"
                     strokeWidth = el.get("strokeWidth") or 0
                     borderRadius = el.get("borderRadius") or 0
                     try:
                         borderRadius = float(borderRadius)
                     except (ValueError, TypeError):
                         borderRadius = 0
                     try:
                         strokeWidth = float(strokeWidth)
                     except (ValueError, TypeError):
                         strokeWidth = 0
                     shape_type = el.get('shapeType', 'rectangle')
                     stroke_color = stroke if stroke and stroke != 'transparent' and stroke != 'none' else "none"
                     
                     # Use inline SVG for accurate shape rendering matching Fabric.js
                     svg_content = ""
                     stroke_attr = f'stroke="{stroke_color}" stroke-width="{strokeWidth}"' if stroke_color != "none" and strokeWidth else 'stroke="none"'
                     
                     if shape_type == 'circle':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><ellipse cx="50" cy="50" rx="48" ry="48" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'ellipse':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><ellipse cx="50" cy="50" rx="48" ry="48" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'triangle':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="50,2 98,98 2,98" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'triangle_right':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="2,2 98,50 2,98" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'diamond':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="50,2 98,50 50,98 2,50" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'star':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="50,2 61,38 98,38 68,60 79,96 50,74 21,96 32,60 2,38 39,38" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type in ('pentagon_arrow', 'chevron'):
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="0,0 75,0 100,50 75,100 0,100" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'parallelogram':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="20,2 98,2 80,98 2,98" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'trapezoid':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="20,2 80,2 98,98 2,98" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'line':
                         line_stroke = stroke_color if stroke_color != "none" else fill
                         sw = strokeWidth if strokeWidth else 2
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><line x1="0" y1="50" x2="100" y2="50" stroke="{line_stroke}" stroke-width="{sw}" /></svg>'
                     elif shape_type in ('block_arrow',):
                         direction = el.get('direction', 'right')
                         if direction == 'right':
                             svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="0,25 65,25 65,5 100,50 65,95 65,75 0,75" fill="{fill}" {stroke_attr} /></svg>'
                         elif direction == 'left':
                             svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="100,25 35,25 35,5 0,50 35,95 35,75 100,75" fill="{fill}" {stroke_attr} /></svg>'
                         elif direction == 'up':
                             svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="25,100 25,35 5,35 50,0 95,35 75,35 75,100" fill="{fill}" {stroke_attr} /></svg>'
                         elif direction == 'down':
                             svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="25,0 25,65 5,65 50,100 95,65 75,65 75,0" fill="{fill}" {stroke_attr} /></svg>'
                         else:
                             svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="0,25 65,25 65,5 100,50 65,95 65,75 0,75" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type in ('callout_rect', 'callout_rounded', 'callout_cloud'):
                         rx_val = '10' if 'rounded' in shape_type else '0'
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><rect x="2" y="2" width="96" height="70" rx="{rx_val}" fill="{fill}" {stroke_attr} /><polygon points="20,72 30,72 25,98" fill="{fill}" /></svg>'
                     elif shape_type == 'arrow':
                         line_stroke = stroke_color if stroke_color != "none" else fill
                         sw = strokeWidth if strokeWidth else 2
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><line x1="2" y1="50" x2="85" y2="50" stroke="{line_stroke}" stroke-width="{sw}" /><polygon points="80,30 100,50 80,70" fill="{line_stroke}" /></svg>'
                     
                     if svg_content:
                         style += " overflow: hidden;"
                         elements_html += f'<div class="page-element" style="{style}">{svg_content}</div>'
                     else:
                         # Fallback: rectangle or rectangle_rounded (CSS-based)
                         if borderRadius:
                             border_radius_cqw = (borderRadius / CANVAS_WIDTH) * 100
                             style += f" border-radius: {border_radius_cqw:.2f}cqw;"
                         style += f" background-color: {fill};"
                         if stroke_color != "none" and strokeWidth:
                             stroke_width_cqw = (strokeWidth / CANVAS_WIDTH) * 100
                             style += f" border: {stroke_width_cqw:.2f}cqw solid {stroke_color};"
                         elements_html += f'<div class="page-element" style="{style}"></div>'
                     
                elif el.get("type") == "icon":
                     icon_color = el.get("fill") or el.get("color") or "#000000"
                     icon_name = el.get("iconName") or el.get("resolvedIconName") or el.get("name") or el.get("icon") or ""
                     src = el.get("svgSrc") or el.get("src") or ""
                     
                     # If width/height are 0 or missing, fallback to 'size' prop
                     if effective_w == 0 or effective_h == 0:
                         try:
                             size = float(el.get("size", 24) or 24)
                         except (ValueError, TypeError):
                             size = 24.0
                         w_pct = (size / CANVAS_WIDTH) * 100
                         h_pct = (size / CANVAS_HEIGHT) * 100
                         style = style.replace(f"width: {width_pct}%;", f"width: {w_pct}%;").replace(f"height: {height_pct}%;", f"height: {h_pct}%;")
                     
                     # Build the icon - prefer Iconify CDN (CORS-safe) over S3 presigned URL
                     # mask-image requires CORS headers; S3 presigned URLs don't include api.citra-ai.com in CORS
                     if icon_name:
                         # Priority 1: Iconify CDN (CORS-safe, works with mask-image for coloring)
                         clean_name = icon_name.split(':')[-1] if ':' in icon_name else icon_name
                         icon_prefix = icon_name.split(':')[0] if ':' in icon_name else 'lucide'
                         encoded_color = icon_color.replace('#', '%23')
                         icon_src = f"https://api.iconify.design/{icon_prefix}/{clean_name}.svg?color={encoded_color}"
                         style += f" background-color: {icon_color}; -webkit-mask-image: url('{icon_src}'); mask-image: url('{icon_src}'); -webkit-mask-size: contain; mask-size: contain; -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat; -webkit-mask-position: center; mask-position: center;"
                         elements_html += f'<div class="page-element" style="{style}"></div>'
                     elif src:
                         # Priority 2: S3 presigned URL via <img> tag (avoids CORS issues with mask-image)
                         elements_html += f'<div class="page-element" style="{style}"><img src="{src}" style="width:100%;height:100%;object-fit:contain;" alt="icon" /></div>'
                     else:
                         elements_html += f'<div class="page-element" style="{style}"></div>'
                
                elif el.get("type") == "table":
                     # Render table element
                     table_data = el.get("tableData") or []
                     header_bg = el.get("headerBackground") or "#f3f4f6"
                     cell_bg = el.get("cellBackground") or "#ffffff"
                     border_color = el.get("borderColor") or "#e5e7eb"
                     table_font_size = el.get("fontSize") or 12
                     try:
                         table_font_size = float(table_font_size)
                     except (ValueError, TypeError):
                         table_font_size = 12
                     table_font_cqw = (table_font_size / CANVAS_WIDTH) * 100
                     
                     table_html = f'<table style="width: 100%; height: 100%; border-collapse: collapse; font-size: {table_font_cqw:.2f}cqw;">'
                     for row_idx, row in enumerate(table_data):
                         table_html += '<tr>'
                         for cell in row:
                             cell_style = f"border: 1px solid {border_color}; padding: 4px;"
                             if row_idx == 0:
                                 cell_style += f" background-color: {header_bg}; font-weight: bold;"
                             else:
                                 cell_style += f" background-color: {cell_bg};"
                             cell_value = html.escape(str(cell)) if cell else ""
                             table_html += f'<td style="{cell_style}">{cell_value}</td>'
                         table_html += '</tr>'
                     table_html += '</table>'
                     
                     elements_html += f'<div class="page-element" style="{style}">{table_html}</div>'
                
                elif el.get("type") == "video":
                     # Video elements - render with presigned S3 URLs or data URLs
                     src = el.get("src") or el.get("thumbnail") or ""
                     if src and (src.startswith("data:") or src.startswith("http")):
                         # Presigned S3 URL or data URL - show a video tag
                         elements_html += f'<video class="page-element" src="{src}" style="{style}" controls autoplay loop muted playsinline></video>'
                     else:
                         # Show placeholder for missing/blob URLs
                         elements_html += f'<div class="page-element" style="{style} background: #1a1a2e; display: flex; align-items: center; justify-content: center; color: white;">Video</div>'
                
                elif el.get("type") == "animation":
                     # Animation elements - render as looping autoplay video (same as presentation animations)
                     src = el.get("videoSrc", "")
                     if src and not src.startswith("blob:"):
                         elements_html += f'''<video class="page-element" src="{src}" style="{style} object-fit: contain;" 
                             autoplay loop muted playsinline></video>'''
                     else:
                         elements_html += f'<div class="page-element" style="{style} background: #1a1a2e; display: flex; align-items: center; justify-content: center; color: white; font-size: 14px;">Animation</div>'

                elif el.get("type") == "chart":
                    # Chart rendering using Chart.js
                    import json
                    chart_config = el.get("chartConfig", {})
                    chart_id = f"chart_{el.get('id', 'x')}_{index}".replace('-', '_')
                    
                    # Support both 'type' (standard Chart.js) and legacy 'chartType'
                    chart_type = chart_config.get("type", chart_config.get("chartType", "bar"))
                    chart_data = chart_config.get("data", {})
                    chart_options = chart_config.get("options", {})
                    
                    full_config = {
                        "type": chart_type,
                        "data": chart_data,
                        "options": {
                            **chart_options,
                            "responsive": True,
                            "maintainAspectRatio": False
                        }
                    }
                    config_json = json.dumps(full_config)
                    
                    elements_html += f'''
                    <div class="page-element" style="{style}">
                        <canvas id="{chart_id}" data-chart-id="{chart_id}" style="width: 100%; height: 100%;"></canvas>
                        <script>
                            window.chartConfigs = window.chartConfigs || {{}};
                            window.chartConfigs['{chart_id}'] = {config_json};
                            
                            (function() {{
                                setTimeout(() => {{
                                    var ctx = document.getElementById('{chart_id}');
                                    if (ctx) {{
                                        new Chart(ctx, window.chartConfigs['{chart_id}']);
                                    }}
                                }}, 100);
                            }})();
                        </script>
                    </div>
                    '''

              except Exception as el_err:
                  logger.warning(f"⚠️ [SHARE] Skipping element {el.get('id', 'unknown')} (type={el.get('type', 'unknown')}) in printable {source_id}: {el_err}")
                  continue

            pages_html += f"""
            <div class="page-wrapper" style="{page_style}">
                {elements_html}
                <div class="page-number">Page {index + 1}</div>
            </div>
            """
            
        pages_html += '</div>'
        
        # Upsell and Edit Button
        upsell_popup = get_upsell_popup_script('report') # Reuse report upsell for now
        edit_button = get_edit_button_html('printable', source_id, permission, share_token)
        
        # Focus Mode Button and Overlay
        present_fab = """
        <button id="present-fab" onclick="startFocusMode()">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M15 14l5-5-5-5"></path>
                <path d="M4 20v-7a4 4 0 0 1 4-4h12"></path>
            </svg>
            Focus Mode
        </button>
        
        <div id="focus-overlay">
            <button class="close-btn" onclick="endFocusMode()">
                <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
            <div id="focus-content">
                <!-- Pages will be cloned here -->
            </div>
            <div class="focus-controls">
                <button class="control-btn" onclick="prevPage()">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="15 18 9 12 15 6"></polyline>
                    </svg>
                </button>
                <button class="control-btn" onclick="nextPage()">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="9 18 15 12 9 6"></polyline>
                    </svg>
                </button>
            </div>
        </div>
        """
        
        # Inject analytics tracking script if analytics is enabled
        analytics_enabled = printable.get("analytics_enabled", True)  # Default to enabled
        tracking_script = ""
        
        if analytics_enabled:
            tracking_script = f'''
            <script>
            (function() {{
                const contentId = "{source_id}";
                const viewerId = localStorage.getItem('ma_viewer_id') || crypto.randomUUID();
                localStorage.setItem('ma_viewer_id', viewerId);
                const sessionId = viewerId + '_' + Date.now();
                
                let currentPage = 0;
                let pageStartTime = Date.now();
                
                // Track view start
                fetch('/citra-ai/api/analytics/track', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ 
                        event_type: 'view_start', 
                        presentation_id: contentId,
                        content_type: 'printable',
                        viewer_id: viewerId,
                        session_id: sessionId,
                        referrer: document.referrer,
                        device_type: /Mobi|Android/i.test(navigator.userAgent) ? 'mobile' : 'desktop'
                    }})
                }}).catch(function() {{}});
                
                // Track page changes with IntersectionObserver
                const observer = new IntersectionObserver(function(entries) {{
                    entries.forEach(function(entry) {{
                        if (entry.isIntersecting) {{
                            const pageIndex = parseInt(entry.target.dataset.pageIndex);
                            if (!isNaN(pageIndex) && pageIndex !== currentPage) {{
                                const duration = Date.now() - pageStartTime;
                                fetch('/citra-ai/api/analytics/track', {{
                                    method: 'POST',
                                    headers: {{ 'Content-Type': 'application/json' }},
                                    body: JSON.stringify({{
                                        event_type: 'slide_view',
                                        presentation_id: contentId,
                                        content_type: 'printable',
                                        viewer_id: viewerId,
                                        session_id: sessionId,
                                        slide_index: currentPage,
                                        duration_ms: duration
                                    }})
                                }}).catch(function() {{}});
                                currentPage = pageIndex;
                                pageStartTime = Date.now();
                            }}
                        }}
                    }});
                }}, {{ threshold: 0.5 }});
                
                document.querySelectorAll('.page-wrapper').forEach(function(el, i) {{
                    el.dataset.pageIndex = i;
                    observer.observe(el);
                }});
                
                window.addEventListener('beforeunload', function() {{
                    const duration = Date.now() - pageStartTime;
                    const beaconData = JSON.stringify({{
                        event_type: 'view_end',
                        presentation_id: contentId,
                        content_type: 'printable',
                        viewer_id: viewerId,
                        session_id: sessionId,
                        slide_index: currentPage,
                        duration_ms: duration
                    }});
                    const blob = new Blob([beaconData], {{ type: 'application/json' }});
                    navigator.sendBeacon('/citra-ai/api/analytics/track', blob);
                }});
            }})();
            </script>
            '''
        
        return generate_base_html(title, pages_html + tracking_script + upsell_popup + edit_button + present_fab, extra_head, is_embed, creator_user_type, content_type='printable', source_id=source_id, branding=branding)
        
    except Exception as e:
        logger.error(f"❌ [SHARE] Failed to render printable {source_id}: {e}")
        logger.error(f"❌ [SHARE] Traceback: {traceback.format_exc()}")
        return generate_error_html("Error", "Failed to load document.")


async def render_presentation_html(source_id: str, title: str, permission: str = "read", share_token: str = None, is_embed: bool = False, creator_user_type: str = "free", branding: dict = None) -> str:
    """Render presentation as HTML slides"""
    try:
        logger.info(f"🔗 [SHARE] Rendering presentation: {source_id}")
        
        # Fetch presentation by UUID string
        presentation = presentations_collection.find_one({"_id": source_id})
        
        if not presentation:
             logger.warning(f"⚠️ [SHARE] Presentation {source_id} not found (deleted or invalid ID)")
             return generate_error_html("Presentation Not Found", "The original presentation has been deleted.")
        
        # Inject presigned URLs for images
        slides = presentation.get("slides", [])
        
        # Aggressive Logging
        logger.info(f"🔗 [SHARE] Found presentation '{presentation.get('title')}' with {len(slides)} slides")
        if not slides:
            logger.warning(f"⚠️ [SHARE] Presentation {source_id} has NO slides!")
            
        if not presentation.get("style"):
             logger.warning(f"⚠️ [SHARE] Presentation {source_id} missing 'style' definition")

        slides = image_processor.inject_presigned_urls_presentation(slides)
        
        # Filter out hidden slides for public share
        slides = [s for s in slides if not s.get("hidden", False)]
        
        # Build HTML
        # Define strict container query for responsive scaling
        extra_head = """
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js"></script>
        <style>
            .slides-container {
                display: flex;
                flex-direction: column;
                gap: 2rem;
                background: #0f172a;
                padding: 2rem;
                border-radius: 8px;
            }
            .slide-wrapper {
                 width: 100%;
                 max-width: 1200px;
                 margin: 0 auto;
                 container-type: inline-size;
            }
            .slide {
                position: relative;
                width: 100%;
                aspect-ratio: 16/9;
                background: #ffffff;
                border-radius: 4px;
                overflow: hidden;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
            }
            .slide-element {
                position: absolute;
                box-sizing: border-box;
            }
            .slide-text {
                font-family: 'Segoe UI', system-ui, sans-serif;
                white-space: pre-wrap;
                line-height: 1.4;
                display: flex;
                align-items: flex-start;
            }
            .slide-image {
                object-fit: contain;
            }
            .slide-svg-diagram {
                overflow: hidden;
            }
            .slide-svg-diagram svg {
                width: 100%;
                height: 100%;
                display: block;
            }
            .slide-chart {
                width: 100%;
                height: 100%;
            }
            .slide-number {
                position: absolute;
                bottom: 10px;
                right: 15px;
                font-size: 12px;
                color: #666;
                z-index: 1000;
            }
            
            /* Slideshow Overlay Styles */
            #slideshow-overlay {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                background: black;
                z-index: 100000;
                align-items: center;
                justify-content: center;
            }
            .slideshow-branding-watermark {
                position: absolute;
                top: 24px;
                left: 24px;
                z-index: 100003;
                background: rgba(0, 0, 0, 0.4);
                padding: 12px 20px;
                border-radius: 8px;
                backdrop-filter: blur(4px);
                border: 1px solid rgba(255,255,255,0.1);
            }
            .slideshow-branding-watermark img {
                max-height: 48px;
                max-width: 200px;
                object-fit: contain;
                display: block;
            }
            #slideshow-content {
                width: 100%;
                height: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                position: relative;
            }
            .slideshow-slide {
                display: none;
                max-width: 100%;
                max-height: 100%;
                aspect-ratio: 16/9;
                /* Scale to fit */
                width: 100%;
                height: auto;
                margin: auto;
                container-type: inline-size;
            }
            .slideshow-slide.active {
                display: block;
            }
            .slideshow-controls {
                position: absolute;
                bottom: 20px;
                left: 50%;
                transform: translateX(-50%);
                display: flex;
                gap: 1rem;
                z-index: 100002;
                opacity: 0;
                transition: opacity 0.3s;
            }
            #slideshow-overlay:hover .slideshow-controls {
                opacity: 1;
            }
            .control-btn {
                background: rgb(19, 24, 43);
                border: gray solid 1px;
                color: white;
                padding: 10px;
                border-radius: 50%;
                cursor: pointer;
                width: 44px;
                height: 44px;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: background 0.2s;
            }
            .control-btn:hover {
                background: rgba(0, 0, 0, 0.6);
            }
            .close-btn {
                position: absolute;
                top: 20px;
                right: 20px;
                z-index: 100002;
                background: transparent;
                border: none;
                color: rgba(255, 255, 255, 0.6);
                cursor: pointer;
            }
             .close-btn:hover { color: white; }
             
             #present-fab {
                position: fixed;
                bottom: 24px;
                right: 24px;
                background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
                color: white;
                border: none;
                border-radius: 50px;
                padding: 12px 24px;
                font-size: 16px;
                font-weight: 600;
                box-shadow: 0 10px 25px -5px rgba(59, 130, 246, 0.5);
                display: flex;
                align-items: center;
                gap: 8px;
                cursor: pointer;
                z-index: 9990;
                transition: transform 0.2s;
             }
             #present-fab:hover { transform: translateY(-2px); }
             
             /* Hide FAB in fullscreen */
             :fullscreen #present-fab { display: none; }

             /* Mobile responsive - Presentation */
             @media (max-width: 768px) {
                .container {
                    padding: 0.5rem !important;
                }
                .content-card {
                    padding: 0 !important;
                    border: none !important;
                    background: transparent !important;
                    box-shadow: none !important;
                }
                .title {
                    padding: 0 0.5rem !important;
                    font-size: 1.1rem !important;
                    margin-bottom: 0.75rem !important;
                }
                .slides-container {
                    padding: 0.5rem !important;
                    gap: 1rem !important;
                    border-radius: 4px !important;
                }
                .slide-wrapper {
                    margin-bottom: 0 !important;
                }
                #present-fab {
                    padding: 10px 16px !important;
                    font-size: 14px !important;
                    bottom: 16px !important;
                    right: 16px !important;
                }
                .slideshow-controls {
                    opacity: 1 !important;
                }
             }
        </style>
        <script>
            let currentSlideIdx = 0;
            let totalSlides = 0;
            
            function startSlideshow() {
                const overlay = document.getElementById('slideshow-overlay');
                const container = document.getElementById('slideshow-content');
                container.innerHTML = ''; // Clear prev
                
                // Clone slides
                const slides = document.querySelectorAll('.slide-wrapper .slide');
                totalSlides = slides.length;
                currentSlideIdx = 0;
                
                slides.forEach((slide, index) => {
                    const clone = slide.cloneNode(true);
                    clone.classList.add('slideshow-slide');
                    clone.style.width = ''; 
                    clone.style.height = ''; 
                    // Maintain aspect ratio via CSS, remove absolute positioning if container conflicts?
                    // The .slide class has aspect-ratio 16/9.
                    if (index === 0) clone.classList.add('active');
                    container.appendChild(clone);
                    
                    // Re-render charts in the cloned slide
                    const clonedCanvases = clone.querySelectorAll('canvas[data-chart-id]');
                    clonedCanvases.forEach(canvas => {
                        const chartId = canvas.getAttribute('data-chart-id');
                        if (window.chartConfigs && window.chartConfigs[chartId]) {
                            new Chart(canvas, window.chartConfigs[chartId]);
                        }
                    });
                });
                
                overlay.style.display = 'flex';
                
                // Request Fullscreen
                if (document.documentElement.requestFullscreen) {
                    document.documentElement.requestFullscreen();
                }
                
                document.addEventListener('keydown', handleKeyNav);
            }
            
            function endSlideshow() {
                const overlay = document.getElementById('slideshow-overlay');
                overlay.style.display = 'none';
                if (document.exitFullscreen && document.fullscreenElement) {
                    document.exitFullscreen();
                }
                document.removeEventListener('keydown', handleKeyNav);
            }
            
            function showSlide(index) {
                const slides = document.querySelectorAll('.slideshow-slide');
                if (index < 0) index = 0;
                if (index >= slides.length) index = slides.length - 1;
                
                currentSlideIdx = index;
                
                slides.forEach((slide, i) => {
                    if (i === currentSlideIdx) slide.classList.add('active');
                    else slide.classList.remove('active');
                });
            }
            
            function nextSlide() {
                if (currentSlideIdx < totalSlides - 1) showSlide(currentSlideIdx + 1);
            }
            
            function prevSlide() {
                if (currentSlideIdx > 0) showSlide(currentSlideIdx - 1);
            }
            
            function handleKeyNav(e) {
                if (e.key === 'ArrowRight' || e.key === 'Space') nextSlide();
                if (e.key === 'ArrowLeft') prevSlide();
                if (e.key === 'Escape') endSlideshow();
            }
            
            // Listen for fullscreen change to exit if user presses Esc
            document.addEventListener('fullscreenchange', () => {
                if (!document.fullscreenElement) {
                     const overlay = document.getElementById('slideshow-overlay');
                     overlay.style.display = 'none';
                }
            });
        </script>
        """
        
        slides_html = '<div class="slides-container">'
        
        CANVAS_WIDTH = 960.0
        CANVAS_HEIGHT = 540.0
        
        # Get global style default
        presentation_style = presentation.get("style", {})
        global_bg = presentation_style.get("slideBackground", "#ffffff")
        
        for index, slide in enumerate(slides):
            elements_html = ""
            elements = slide.get("elements", [])
            # Sort elements by zIndex to ensure correct rendering order in DOM (fallback)
            elements.sort(key=lambda x: x.get('zIndex', 0))
            
            # Use slide specific background or fallback to global style
            bg_color = slide.get("backgroundColor")
            if not bg_color:
                bg_color = global_bg
            bg_image = slide.get("backgroundImage")
            
            slide_style = f"background-color: {bg_color};"
            if bg_image:
                slide_style += f" background-image: url('{bg_image}'); background-size: 100% 100%; background-position: center; background-repeat: no-repeat;"
            
            for el in elements:
              try:
                # Common style properties - ensure numeric types
                try:
                    x = float(el.get('x', 0) or 0)
                except (ValueError, TypeError):
                    x = 0.0
                try:
                    y = float(el.get('y', 0) or 0)
                except (ValueError, TypeError):
                    y = 0.0
                try:
                    w = float(el.get('width', 0) or 0)
                except (ValueError, TypeError):
                    w = 0.0
                try:
                    h = float(el.get('height', 0) or 0)
                except (ValueError, TypeError):
                    h = 0.0
                try:
                    rotation = float(el.get('rotation', 0) or 0)
                except (ValueError, TypeError):
                    rotation = 0
                try:
                    opacity = float(el.get('opacity', 1) or 1)
                except (ValueError, TypeError):
                    opacity = 1
                z_index = el.get('zIndex', 0) or 0
                
                # Handle scaleX/scaleY for complex shapes (polygon, star, arrow, etc.)
                # The frontend stores scaleX/scaleY separately for complex shapes
                try:
                    scale_x = float(el.get('scaleX', 1) or 1)
                except (ValueError, TypeError):
                    scale_x = 1.0
                try:
                    scale_y = float(el.get('scaleY', 1) or 1)
                except (ValueError, TypeError):
                    scale_y = 1.0
                
                # Apply scaleX/scaleY to dimensions (the frontend applies these as Fabric transforms)
                effective_w = w * scale_x
                effective_h = h * scale_y
                
                # Percentage positioning
                left_pct = (x / CANVAS_WIDTH) * 100
                top_pct = (y / CANVAS_HEIGHT) * 100
                width_pct = (effective_w / CANVAS_WIDTH) * 100
                height_pct = (effective_h / CANVAS_HEIGHT) * 100
                
                # Build transform: rotation + transform-origin at top-left
                transform_parts = []
                if rotation:
                    transform_parts.append(f"rotate({rotation}deg)")
                transform_str = " ".join(transform_parts) if transform_parts else "none"
                
                # Base styling
                style = f"left: {left_pct}%; top: {top_pct}%; width: {width_pct}%; height: {height_pct}%; z-index: {z_index}; opacity: {opacity}; transform: {transform_str}; transform-origin: top left;"
                
                if el.get("type") == "text":
                    content = el.get("content", "")
                    try:
                        fontSize = float(el.get("fontSize", 20) or 20)
                    except (ValueError, TypeError):
                        fontSize = 20.0
                    # Use container query units for responsiveness
                    font_cqw = (fontSize / CANVAS_WIDTH) * 100
                    
                    # Fabric.js uses 'fill' for text color, but we support 'color' too
                    color = el.get("color") or el.get("fill")
                    
                    # Fallback color logic similar to frontend
                    if not color:
                        bg_hex = bg_color if bg_color.startswith('#') else '#ffffff'
                        # Simple luminance check
                        # Convert hex to rgb
                        try:
                            h = bg_hex.lstrip('#')
                            rgb = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
                            # Perceived brightness (YIQ)
                            brightness = (rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114) / 1000
                            if brightness < 128:
                                color = '#ffffff'
                            else:
                                color = '#000000'
                        except Exception:
                            # Fallback if hex parsing fails
                            if bg_hex in ['#000000', '#0f172a', '#111827', '#1a1a2e']:
                                color = '#ffffff'
                            else:
                                color = '#000000'

                    textAlign = el.get('textAlign', 'left')
                    fontWeight = el.get('fontWeight', 'normal')
                    fontFamily = el.get('fontFamily', 'Inter, sans-serif')
                    
                    # lineHeight and letterSpacing - match frontend defaults
                    try:
                        lineHeight = float(el.get('lineHeight') or 1.4)
                    except (ValueError, TypeError):
                        lineHeight = 1.4
                    try:
                        letterSpacing = float(el.get('letterSpacing') or 0)
                    except (ValueError, TypeError):
                        letterSpacing = 0
                    
                    # Text specific styles
                    # Note: Fabric line-height is unitless (multiplier). CSS matches.
                    style += f" font-size: {font_cqw}cqw; color: {color}; text-align: {textAlign}; font-weight: {fontWeight}; font-family: {fontFamily}; line-height: {lineHeight}; white-space: pre-wrap; word-wrap: break-word;"
                    if letterSpacing:
                        letter_spacing_cqw = (letterSpacing / CANVAS_WIDTH) * 100
                        style += f" letter-spacing: {letter_spacing_cqw:.2f}cqw;"
                    
                    elements_html += f'<div class="slide-element slide-text" style="{style}">{html.escape(content or "")}</div>'
                    
                elif el.get("type") == "image":
                    src = el.get("src", "")
                    elements_html += f'<img class="slide-element slide-image" src="{src}" style="{style}" loading="lazy" />'

                elif el.get("type") == "svg_diagram":
                    # Full-slot inline SVG diagram (org charts, process flows, infographics).
                    # The raw SVG markup lives in `svgContent` (already sanitized on save).
                    # Embed it inline and resolve `currentColor` to the element accent so
                    # themed colors render — mirrors PresentationCanvas's svg_diagram path.
                    raw_svg = el.get("svgContent") or ""
                    if isinstance(raw_svg, str) and raw_svg.strip():
                        accent = el.get("fillColor") or el.get("fill") or el.get("color") or "#3B82F6"
                        themed_svg = raw_svg.replace("currentColor", accent)
                        elements_html += f'<div class="slide-element slide-svg-diagram" style="{style}">{themed_svg}</div>'

                elif el.get("type") == "video":
                    # Video element - autoplay, loop, muted, no controls (pitch.com style)
                    src = el.get("src", "")
                    elements_html += f'''<video class="slide-element slide-video" src="{src}" style="{style}" 
                        autoplay loop muted playsinline 
                        loading="lazy"></video>'''
                
                elif el.get("type") == "animation":
                    # Animation element - render as looping autoplay video (same as regular video but uses videoSrc)
                    src = el.get("videoSrc", "")
                    if src and not src.startswith("blob:"):
                        elements_html += f'''<video class="slide-element slide-video" src="{src}" style="{style} object-fit: contain;" 
                            autoplay loop muted playsinline 
                            loading="lazy"></video>'''
                    else:
                        elements_html += f'<div class="slide-element" style="{style} background: #1a1a2e; display: flex; align-items: center; justify-content: center; color: white;">Animation</div>'

                elif el.get("type") == "shape":
                     fill = el.get("fill", "#cccccc")
                     stroke = el.get("stroke", None)
                     stroke_color = stroke if stroke and stroke != 'none' else "none"
                     try:
                         strokeWidth = float(el.get("strokeWidth", 0) or 0)
                     except (ValueError, TypeError):
                         strokeWidth = 0
                     try:
                         borderRadius = float(el.get("borderRadius", 0) or 0)
                     except (ValueError, TypeError):
                         borderRadius = 0
                     shape_type = el.get('shapeType', 'rectangle')
                     
                     # Convert strokeWidth to responsive unit  
                     stroke_width_cqw = (strokeWidth / CANVAS_WIDTH) * 100 if strokeWidth else 0
                     border_radius_cqw = (borderRadius / CANVAS_WIDTH) * 100 if borderRadius else 0
                     
                     # Use inline SVG for accurate shape rendering matching Fabric.js
                     svg_content = ""
                     stroke_attr = f'stroke="{stroke_color}" stroke-width="{strokeWidth}"' if stroke_color != "none" and strokeWidth else 'stroke="none"'
                     
                     if shape_type == 'circle':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><ellipse cx="50" cy="50" rx="48" ry="48" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'ellipse':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><ellipse cx="50" cy="50" rx="48" ry="48" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'triangle':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="50,2 98,98 2,98" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'triangle_right':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="2,2 98,50 2,98" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'diamond':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="50,2 98,50 50,98 2,50" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'star':
                         # 5-pointed star
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="50,2 61,38 98,38 68,60 79,96 50,74 21,96 32,60 2,38 39,38" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'pentagon_arrow' or shape_type == 'chevron':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="0,0 75,0 100,50 75,100 0,100" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'parallelogram':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="20,2 98,2 80,98 2,98" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'trapezoid':
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="20,2 80,2 98,98 2,98" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type == 'line':
                         line_stroke = stroke_color if stroke_color != "none" else fill
                         sw = strokeWidth if strokeWidth else 2
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><line x1="0" y1="50" x2="100" y2="50" stroke="{line_stroke}" stroke-width="{sw}" /></svg>'
                     elif shape_type in ('block_arrow',):
                         direction = el.get('direction', 'right')
                         if direction == 'right':
                             svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="0,25 65,25 65,5 100,50 65,95 65,75 0,75" fill="{fill}" {stroke_attr} /></svg>'
                         elif direction == 'left':
                             svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="100,25 35,25 35,5 0,50 35,95 35,75 100,75" fill="{fill}" {stroke_attr} /></svg>'
                         elif direction == 'up':
                             svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="25,100 25,35 5,35 50,0 95,35 75,35 75,100" fill="{fill}" {stroke_attr} /></svg>'
                         elif direction == 'down':
                             svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="25,0 25,65 5,65 50,100 95,65 75,65 75,0" fill="{fill}" {stroke_attr} /></svg>'
                         else:
                             svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><polygon points="0,25 65,25 65,5 100,50 65,95 65,75 0,75" fill="{fill}" {stroke_attr} /></svg>'
                     elif shape_type in ('callout_rect', 'callout_rounded', 'callout_cloud'):
                         rx_val = '10' if 'rounded' in shape_type else '0'
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><rect x="2" y="2" width="96" height="70" rx="{rx_val}" fill="{fill}" {stroke_attr} /><polygon points="20,72 30,72 25,98" fill="{fill}" /></svg>'
                     elif shape_type == 'arrow':
                         line_stroke = stroke_color if stroke_color != "none" else fill
                         sw = strokeWidth if strokeWidth else 2
                         svg_content = f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;display:block;"><line x1="2" y1="50" x2="85" y2="50" stroke="{line_stroke}" stroke-width="{sw}" /><polygon points="80,30 100,50 80,70" fill="{line_stroke}" /></svg>'
                     
                     if svg_content:
                         # SVG-based shape
                         style += " overflow: hidden;"
                         elements_html += f'<div class="slide-element slide-shape" style="{style}">{svg_content}</div>'
                     else:
                         # Fallback: rectangle or rectangle_rounded (CSS-based)
                         if borderRadius:
                             style += f" border-radius: {border_radius_cqw}cqw;"
                         border_style = f"border: {stroke_width_cqw}cqw solid {stroke_color};" if stroke_color != "none" and strokeWidth else ""
                         style += f" background-color: {fill}; {border_style}"
                         elements_html += f'<div class="slide-element slide-shape" style="{style}"></div>'
                     
                elif el.get("type") == "icon":
                     # Icon handling - use fill/color from element data
                     icon_color = el.get("fill") or el.get("color") or "#000000"
                     # Match frontend icon name resolution: iconName > resolvedIconName > name > icon
                     icon_name = el.get("iconName") or el.get("resolvedIconName") or el.get("name") or el.get("icon") or ""
                     src = el.get("svgSrc") or el.get("src") or ""
                     
                     # Icons in frontend are often sized by 'size' prop, but 'width'/'height' 
                     # in the element data (if updated by canvas) should be accurate.
                     # If width/height are 0 or missing, fallback to 'size' prop.
                     if effective_w == 0 or effective_h == 0:
                         try:
                             size = float(el.get("size", 24) or 24)
                         except (ValueError, TypeError):
                             size = 24.0
                         w_pct = (size / CANVAS_WIDTH) * 100
                         h_pct = (size / CANVAS_HEIGHT) * 100
                         style = style.replace(f"width: {width_pct}%;", f"width: {w_pct}%;").replace(f"height: {height_pct}%;", f"height: {h_pct}%;")
                     # Build the icon - prefer Iconify CDN (CORS-safe) over S3 presigned URL
                     # mask-image requires CORS headers; S3 presigned URLs don't include api.citra-ai.com in CORS
                     if icon_name:
                         # Priority 1: Iconify CDN (CORS-safe, works with mask-image for coloring)
                         clean_name = icon_name.split(':')[-1] if ':' in icon_name else icon_name
                         icon_prefix = icon_name.split(':')[0] if ':' in icon_name else 'lucide'
                         encoded_color = icon_color.replace('#', '%23')
                         icon_src = f"https://api.iconify.design/{icon_prefix}/{clean_name}.svg?color={encoded_color}"
                         style += f" background-color: {icon_color}; -webkit-mask-image: url('{icon_src}'); mask-image: url('{icon_src}'); -webkit-mask-size: contain; mask-size: contain; -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat; -webkit-mask-position: center; mask-position: center;"
                         elements_html += f'<div class="slide-element slide-icon" style="{style}"></div>'
                     elif src:
                         # Priority 2: S3 presigned URL via <img> tag (avoids CORS issues with mask-image)
                         elements_html += f'<div class="slide-element slide-icon" style="{style}"><img src="{src}" style="width:100%;height:100%;object-fit:contain;" alt="icon" /></div>'
                     else:
                         elements_html += f'<div class="slide-element slide-icon" style="{style}"></div>'

                elif el.get("type") == "chart":
                    # Chart rendering using Chart.js
                    import json
                    chart_config = el.get("chartConfig", {})
                    chart_id = f"chart_{el.get('id', 'x')}".replace('-', '_')
                    
                    # Build Chart.js config from our chartConfig
                    # Support both 'type' (standard Chart.js) and legacy 'chartType'
                    chart_type = chart_config.get("type", chart_config.get("chartType", "bar"))
                    chart_data = chart_config.get("data", {})
                    chart_options = chart_config.get("options", {})
                    
                    # Construct full Chart.js config
                    full_config = {
                        "type": chart_type,
                        "data": chart_data,
                        "options": {
                            **chart_options,
                            "responsive": True,
                            "maintainAspectRatio": False
                        }
                    }
                    config_json = json.dumps(full_config)
                    
                    elements_html += f'''
                    <div class="slide-element" style="{style}">
                        <canvas id="{chart_id}" data-chart-id="{chart_id}" class="slide-chart"></canvas>
                        <script>
                            window.chartConfigs = window.chartConfigs || {{}};
                            window.chartConfigs['{chart_id}'] = {config_json};
                            
                            (function() {{
                                setTimeout(() => {{
                                    var ctx = document.getElementById('{chart_id}');
                                    if (ctx) {{
                                        new Chart(ctx, window.chartConfigs['{chart_id}']);
                                    }}
                                }}, 100);
                            }})();
                        </script>
                    </div>
                    '''

              except Exception as el_err:
                  logger.warning(f"⚠️ [SHARE] Skipping element {el.get('id', 'unknown')} (type={el.get('type', 'unknown')}) in presentation {source_id}: {el_err}")
                  continue

            slides_html += f"""
            <div class="slide-wrapper">
                <div class="slide" style="{slide_style}">
                    {elements_html}
                    <div class="slide-number">{index + 1}</div>
                </div>
            </div>
            """
            
        slides_html += '</div>'
        
        # Inject analytics tracking script if analytics is enabled
        analytics_enabled = presentation.get("analytics_enabled", True)  # Default to enabled
        tracking_script = ""
        
        if analytics_enabled:
            tracking_script = f'''
            <script>
            (function() {{
                const presentationId = "{source_id}";
                const viewerId = localStorage.getItem('ma_viewer_id') || crypto.randomUUID();
                localStorage.setItem('ma_viewer_id', viewerId);
                const sessionId = viewerId + '_' + Date.now();
                
                let currentSlide = 0;
                let slideStartTime = Date.now();
                
                // Track view start
                fetch('/citra-ai/api/analytics/track', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ 
                        event_type: 'view_start', 
                        presentation_id: presentationId,
                        viewer_id: viewerId,
                        session_id: sessionId,
                        referrer: document.referrer,
                        device_type: /Mobi|Android/i.test(navigator.userAgent) ? 'mobile' : 'desktop'
                    }})
                }}).catch(function() {{}});
                
                // Track slide changes with IntersectionObserver
                const observer = new IntersectionObserver(function(entries) {{
                    entries.forEach(function(entry) {{
                        if (entry.isIntersecting) {{
                            const slideIndex = parseInt(entry.target.dataset.slideIndex);
                            if (!isNaN(slideIndex) && slideIndex !== currentSlide) {{
                                const duration = Date.now() - slideStartTime;
                                fetch('/citra-ai/api/analytics/track', {{
                                    method: 'POST',
                                    headers: {{ 'Content-Type': 'application/json' }},
                                    body: JSON.stringify({{
                                        event_type: 'slide_view',
                                        presentation_id: presentationId,
                                        viewer_id: viewerId,
                                        session_id: sessionId,
                                        slide_index: currentSlide,
                                        duration_ms: duration
                                    }})
                                }}).catch(function() {{}});
                                currentSlide = slideIndex;
                                slideStartTime = Date.now();
                            }}
                        }}
                    }});
                }}, {{ threshold: 0.5 }});
                
                document.querySelectorAll('.slide-wrapper').forEach(function(el, i) {{
                    el.dataset.slideIndex = i;
                    observer.observe(el);
                }});
                
                window.addEventListener('beforeunload', function() {{
                    const duration = Date.now() - slideStartTime;
                    const beaconData = JSON.stringify({{
                        event_type: 'view_end',
                        presentation_id: presentationId,
                        viewer_id: viewerId,
                        session_id: sessionId,
                        slide_index: currentSlide,
                        duration_ms: duration
                    }});
                    const blob = new Blob([beaconData], {{ type: 'application/json' }});
                    navigator.sendBeacon('/citra-ai/api/analytics/track', blob);
                }});
            }})();
            </script>
            '''
        
        # Add upsell popup for new user acquisition
        upsell_popup = get_upsell_popup_script('presentation')

        # Add Edit Button (Presentation)
        # Note: Using source_id directly as it's passed in
        edit_button = get_edit_button_html('presentation', source_id, permission, share_token)
        
        # Build watermark HTML for the fullscreen slideshow based on Custom Branding
        watermark_html = ""
        if branding and branding.get("enabled"):
            logo_url = branding.get("logo_url")
            company_name = branding.get("company_name", "Company")
            if logo_url:
                watermark_html = f'''
                <div class="slideshow-branding-watermark">
                    <img src="{logo_url}" alt="{company_name} Logo">
                </div>
                '''

        # Present Button and Overlay HTML
        present_fab = f"""
        <button id="present-fab" onclick="startSlideshow()">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
            </svg>
            Present
        </button>
        
        <div id="slideshow-overlay">
            {watermark_html}
            <button class="close-btn" onclick="endSlideshow()">
                <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
            <div id="slideshow-content">
                <!-- Slides will be cloned here -->
            </div>
            <div class="slideshow-controls">
                <button class="control-btn" onclick="prevSlide()">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="15 18 9 12 15 6"></polyline>
                    </svg>
                </button>
                <button class="control-btn" onclick="nextSlide()">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="9 18 15 12 9 6"></polyline>
                    </svg>
                </button>
            </div>
        </div>
        """
        
        return generate_base_html(title, slides_html + tracking_script + upsell_popup + edit_button + present_fab, extra_head, is_embed, creator_user_type, content_type='presentation', source_id=source_id, branding=branding)

    except Exception as e:
        logger.error(f"❌ [SHARE] Failed to render presentation: {e}")
        logger.error(f"❌ [SHARE] Traceback: {traceback.format_exc()}")
        return generate_error_html("Error", "Failed to load presentation.")


def process_markdown_basic(text: str) -> str:
    """Enhanced markdown processing for display - handles common patterns including tables"""
    import re
    
    # Store code blocks temporarily to avoid processing markdown inside them
    code_blocks = []
    def store_code_block(match):
        code_blocks.append(match.group(0))
        return f'___CODE_BLOCK_{len(code_blocks)-1}___'
    
    # Preserve code blocks before HTML escaping
    text = re.sub(r'```[\s\S]*?```', store_code_block, text)
    
    # Escape HTML
    text = html.escape(text)
    
    # Process tables BEFORE other formatting
    def process_table(match):
        table_text = match.group(0)
        lines = [line.strip() for line in table_text.strip().split('\n') if line.strip()]
        
        if len(lines) < 2:
            return table_text
        
        # Helper to apply inline formatting to cell content
        def format_cell_content(content):
            # Bold
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            # Italic
            content = re.sub(r'(?<!\*)\*(.+?)\*(?!\*)', r'<em>\1</em>', content)
            # Inline code
            content = re.sub(r'`(.+?)`', r'<code style="background: rgba(0,0,0,0.3); padding: 0.125rem 0.375rem; border-radius: 3px;">\1</code>', content)
            return content
        
        html_table = '<table style="border-collapse: collapse; width: 100%; margin: 1rem 0; background: rgba(0,0,0,0.2); border-radius: 8px; overflow: hidden; font-size: 0.9rem;">'
        
        is_header_row = True
        for i, line in enumerate(lines):
            # Skip separator line (contains only |, -, :, spaces)
            if re.match(r'^[\|\-:\s]+$', line):
                continue
            
            cells = [cell.strip() for cell in line.split('|')]
            cells = [c for c in cells if c]  # Remove empty cells from start/end
            
            if is_header_row:
                # Header row
                html_table += '<thead><tr>'
                for cell in cells:
                    formatted_cell = format_cell_content(cell)
                    html_table += f'<th style="padding: 0.75rem; text-align: left; border-bottom: 2px solid rgba(96, 165, 250, 0.5); font-weight: 600; color: #60a5fa; white-space: normal;">{formatted_cell}</th>'
                html_table += '</tr></thead><tbody>'
                is_header_row = False
            else:
                # Data row
                html_table += '<tr style="border-bottom: 1px solid rgba(255,255,255,0.1);">'
                for cell in cells:
                    formatted_cell = format_cell_content(cell)
                    html_table += f'<td style="padding: 0.75rem; text-align: left; vertical-align: top; white-space: normal; line-height: 1.5;">{formatted_cell}</td>'
                html_table += '</tr>'
        
        html_table += '</tbody></table>'
        return html_table
    
    # Match markdown tables (consecutive lines with | delimiters, allow leading spaces)
    text = re.sub(r'(?:^\s*\|.*\|\s*$\n?)+', process_table, text, flags=re.MULTILINE)
    
    # Headers (process from most specific to least)
    text = re.sub(r'^######\s+(.+)$', r'<h6 style="font-size: 0.9rem; margin: 1rem 0 0.5rem 0; color: #60a5fa; font-weight: 600;">\1</h6>', text, flags=re.MULTILINE)
    text = re.sub(r'^#####\s+(.+)$', r'<h5 style="font-size: 0.95rem; margin: 1rem 0 0.5rem 0; color: #60a5fa; font-weight: 600;">\1</h5>', text, flags=re.MULTILINE)
    text = re.sub(r'^####\s+(.+)$', r'<h4 style="font-size: 1rem; margin: 1rem 0 0.5rem 0; color: #60a5fa; font-weight: 600;">\1</h4>', text, flags=re.MULTILINE)
    text = re.sub(r'^###\s+(.+)$', r'<h3 style="font-size: 1.1rem; margin: 1rem 0 0.5rem 0; color: #60a5fa; font-weight: 600;">\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^##\s+(.+)$', r'<h2 style="font-size: 1.2rem; margin: 1rem 0 0.5rem 0; color: #60a5fa; font-weight: 600;">\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^#\s+(.+)$', r'<h1 style="font-size: 1.4rem; margin: 1rem 0 0.5rem 0; color: #60a5fa; font-weight: 700;">\1</h1>', text, flags=re.MULTILINE)
    
    # Bold (must come before italic to avoid conflicts)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
    
    # Italic
    text = re.sub(r'(?<!\*)\*([^*\s](?:[^*]*[^*\s])?)\*(?!\*)', r'<em>\1</em>', text)
    text = re.sub(r'(?<!_)_([^_\s](?:[^_]*[^_\s])?)_(?!_)', r'<em>\1</em>', text)
    
    # Inline code
    text = re.sub(r'`([^`]+)`', r'<code style="background: rgba(0,0,0,0.3); padding: 0.125rem 0.375rem; border-radius: 3px; font-family: monospace; font-size: 0.875rem;">\1</code>', text)
    
    # Numbered lists
    text = re.sub(r'^(\d+)\.\s+(.+)$', r'<li style="margin-left: 1.5rem; margin-bottom: 0.5rem; line-height: 1.6;">\2</li>', text, flags=re.MULTILINE)
    
    # Bullet lists (dash and asterisk)
    text = re.sub(r'^[-*]\s+(.+)$', r'<li style="margin-left: 1.5rem; margin-bottom: 0.5rem; line-height: 1.6;">\1</li>', text, flags=re.MULTILINE)
    
    # Wrap consecutive list items in ul
    text = re.sub(r'(<li[^>]*>.*?</li>\s*)+', lambda m: f'<ul style="list-style: disc; padding-left: 1.5rem; margin: 0.5rem 0;">{m.group(0)}</ul>', text)
    
    # Horizontal rules
    text = re.sub(r'^-{3,}$', r'<hr style="border: none; border-top: 1px solid rgba(255,255,255,0.2); margin: 1.5rem 0;">', text, flags=re.MULTILINE)
    text = re.sub(r'^\*{3,}$', r'<hr style="border: none; border-top: 1px solid rgba(255,255,255,0.2); margin: 1.5rem 0;">', text, flags=re.MULTILINE)
    
    # Links [text](url)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" rel="noopener noreferrer" style="color: #60a5fa; text-decoration: underline;">\1</a>', text)
    
    # Blockquotes (> at start of line)
    text = re.sub(r'^&gt;\s*(.+)$', r'<blockquote style="border-left: 3px solid #60a5fa; padding-left: 1rem; margin: 1rem 0; color: #a1a1aa; font-style: italic;">\1</blockquote>', text, flags=re.MULTILINE)
    
    # Restore code blocks
    for i, code_block in enumerate(code_blocks):
        # Extract language and code content
        match = re.match(r'```(\w*)\n?([\s\S]*?)```', code_block)
        if match:
            lang = match.group(1) or ''
            code_content = match.group(2)
            # Already escaped, no need to escape again
            formatted_code = f'<pre style="background: rgba(0,0,0,0.4); padding: 1rem; border-radius: 6px; overflow-x: auto; margin: 1rem 0; border-left: 3px solid #60a5fa;"><code style="font-family: monospace; font-size: 0.875rem; line-height: 1.5;">{code_content}</code></pre>'
            text = text.replace(f'___CODE_BLOCK_{i}___', formatted_code)
    
    # Paragraph handling - preserve structure around block elements
    # Don't wrap block elements in <p> tags
    text = re.sub(r'\n\n+', '\n</p><p>\n', text)
    
    # Wrap content in paragraphs, but exclude block-level elements
    lines = text.split('\n')
    result = []
    in_paragraph = False
    
    for line in lines:
        stripped = line.strip()
        # Check if line is a block element or empty
        is_block = (stripped.startswith('<table') or stripped.startswith('<h') or 
                   stripped.startswith('<ul') or stripped.startswith('<pre') or
                   stripped.startswith('<hr') or stripped.startswith('<blockquote') or
                   stripped.startswith('</table') or stripped.startswith('</ul') or 
                   stripped.startswith('</pre') or stripped.startswith('</blockquote') or
                   stripped == '<p>' or stripped == '</p>' or not stripped)
        
        if is_block:
            if in_paragraph and stripped not in ['<p>', '']:
                result.append('</p>')
                in_paragraph = False
            result.append(line)
        else:
            if not in_paragraph:
                result.append('<p style="margin: 0.75rem 0; line-height: 1.6;">')
                in_paragraph = True
            result.append(line)
            # Add <br> for line breaks within paragraphs
            if line and not line.strip().startswith('<'):
                result.append('<br>')
    
    if in_paragraph:
        result.append('</p>')
    
    text = '\n'.join(result)
    
    # Clean up extra <br> tags before closing tags
    text = re.sub(r'<br>\s*</p>', '</p>', text)
    text = re.sub(r'<p[^>]*>\s*</p>', '', text)
    
    return text
