"""
Enterprise Branding API - Manage enterprise-level branding for on-prem deployments

Architecture:
- Single enterprise branding document in `enterprise_branding` collection (_id: "enterprise")
- Admin access controlled via `admins` collection (seeded directly in MongoDB)
- All branding write operations require admin role
- Branding read (for rendering shared content) available to any authenticated user
"""

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Request
from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
import logging
import re
import os
from citra_auth import get_current_user
from citra_mongo import get_mongo_client, get_database_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/customization", tags=["customization"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])
root_router = APIRouter(tags=["customization-root"])

# ============== MongoDB Collections ==============

def get_admins_collection():
    """Get admins collection (seeded directly in MongoDB during deployment)"""
    return get_mongo_client()[get_database_name()]['admins']


def get_enterprise_branding_collection():
    """Get enterprise_branding collection (single document with _id: 'enterprise')"""
    return get_mongo_client()[get_database_name()]['enterprise_branding']


# ============== Constants ==============

ENTERPRISE_DOC_ID = "enterprise"
BASE_URL = os.getenv("BASE_URL", "https://localhost:8085")


# ============== Admin Helpers ==============

def is_admin(email: str) -> bool:
    """Check if an email is in the admins collection"""
    admins_col = get_admins_collection()
    return admins_col.find_one({"email": email}) is not None


def require_admin(current_user: dict):
    """Raise 403 if the current user is not an admin"""
    email = current_user.get("email") or current_user.get("user_id")
    if not is_admin(email):
        raise HTTPException(status_code=403, detail="Admin access required")
    return email


# ============== Pydantic Models ==============

class BrandingConfig(BaseModel):
    """Enterprise branding configuration"""
    company_name: str = Field(..., min_length=1, max_length=100)
    contact_email: Optional[str] = None
    contact_address: Optional[str] = None
    contact_phone: Optional[str] = None
    website_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    show_powered_by: bool = False

    @validator('primary_color', 'secondary_color', pre=True, always=True)
    def validate_color(cls, v):
        if v is None:
            return v
        if not re.match(r'^#[0-9A-Fa-f]{6}$', v):
            raise ValueError('Invalid hex color format (use #RRGGBB)')
        return v


class BrandingResponse(BaseModel):
    """Full branding response"""
    enabled: bool
    logo_url: Optional[str] = None
    company_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_address: Optional[str] = None
    contact_phone: Optional[str] = None
    website_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    show_powered_by: bool = False


# ============== Admin Endpoints ==============

@admin_router.get("/check")
def check_admin(current_user: dict = Depends(get_current_user)):
    """Check if current user is an admin"""
    email = current_user.get("email") or current_user.get("user_id")
    return {"is_admin": is_admin(email)}


# ============== Enterprise Branding Endpoints ==============

@router.get("/branding", response_model=BrandingResponse)
def get_branding(current_user: dict = Depends(get_current_user)):
    """
    Get enterprise branding configuration (any authenticated user).
    Used by all users for rendering shared content with enterprise branding.
    """
    branding_col = get_enterprise_branding_collection()
    doc = branding_col.find_one({"_id": ENTERPRISE_DOC_ID})

    if not doc:
        return BrandingResponse(enabled=False, show_powered_by=False)

    logo_url = None
    if doc.get("logo") and doc["logo"].get("s3_key"):
        try:
            from bucket import generate_download_url
            logo_url = generate_download_url(doc["logo"]["s3_key"], expiry_seconds=3600)
        except Exception as e:
            logger.warning(f"Failed to generate presigned URL for logo: {e}")
            logo_url = doc["logo"].get("url")

    return BrandingResponse(
        enabled=True,
        logo_url=logo_url,
        company_name=doc.get("company_name"),
        contact_email=doc.get("contact_email"),
        contact_address=doc.get("contact_address"),
        contact_phone=doc.get("contact_phone"),
        website_url=doc.get("website_url"),
        primary_color=doc.get("colors", {}).get("primary"),
        secondary_color=doc.get("colors", {}).get("secondary"),
        show_powered_by=doc.get("show_powered_by", False)
    )


@router.put("/branding")
def update_branding(
    config: BrandingConfig,
    current_user: dict = Depends(get_current_user)
):
    """Update enterprise branding configuration (admin only)"""
    admin_email = require_admin(current_user)

    branding_col = get_enterprise_branding_collection()

    update_doc = {
        "_id": ENTERPRISE_DOC_ID,
        "company_name": config.company_name,
        "contact_email": config.contact_email,
        "contact_address": config.contact_address,
        "contact_phone": config.contact_phone,
        "website_url": config.website_url,
        "colors": {},
        "show_powered_by": config.show_powered_by,
        "updated_at": datetime.utcnow(),
        "updated_by": admin_email
    }

    if config.primary_color:
        update_doc["colors"]["primary"] = config.primary_color
    if config.secondary_color:
        update_doc["colors"]["secondary"] = config.secondary_color

    # Preserve existing logo if present
    existing = branding_col.find_one({"_id": ENTERPRISE_DOC_ID})
    if existing and existing.get("logo"):
        update_doc["logo"] = existing["logo"]

    branding_col.replace_one(
        {"_id": ENTERPRISE_DOC_ID},
        update_doc,
        upsert=True
    )

    logger.info(f"🎨 Enterprise branding updated by {admin_email}")
    return {"success": True, "message": "Enterprise branding updated"}


@router.post("/branding/logo")
def upload_branding_logo(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload enterprise branding logo to S3 (admin only)"""
    admin_email = require_admin(current_user)

    ext = file.filename.split('.')[-1].lower() if file.filename and '.' in file.filename else ''
    if ext not in ['png', 'jpg', 'jpeg', 'svg', 'webp']:
        raise HTTPException(status_code=400, detail="Invalid file type. Must be PNG, JPG, SVG, or WebP.")

    content = file.file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 2MB.")

    from bucket import upload_file
    import time

    s3_key = f"branding/enterprise/logo_{int(time.time())}.{ext}"

    try:
        s3_url = upload_file(content, s3_key, content_type=file.content_type)
    except Exception as e:
        logger.error(f"Failed to upload logo: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload logo to storage")

    branding_col = get_enterprise_branding_collection()
    logo_data = {
        "url": s3_url,
        "s3_key": s3_key,
        "uploaded_at": datetime.utcnow()
    }

    branding_col.update_one(
        {"_id": ENTERPRISE_DOC_ID},
        {"$set": {"logo": logo_data}},
        upsert=True
    )

    logger.info(f"🎨 Enterprise logo uploaded by {admin_email}")
    return {"success": True, "logo_url": s3_url}


@router.delete("/branding/logo")
def delete_branding_logo(current_user: dict = Depends(get_current_user)):
    """Delete enterprise branding logo (admin only)"""
    admin_email = require_admin(current_user)

    branding_col = get_enterprise_branding_collection()
    branding_col.update_one(
        {"_id": ENTERPRISE_DOC_ID},
        {"$unset": {"logo": 1}}
    )

    logger.info(f"🎨 Enterprise logo deleted by {admin_email}")
    return {"success": True, "message": "Logo removed"}


@router.delete("/branding")
def disable_branding(current_user: dict = Depends(get_current_user)):
    """Delete enterprise branding entirely (admin only)"""
    admin_email = require_admin(current_user)

    branding_col = get_enterprise_branding_collection()
    branding_col.delete_one({"_id": ENTERPRISE_DOC_ID})

    logger.info(f"🎨 Enterprise branding disabled by {admin_email}")
    return {"success": True, "message": "Enterprise branding disabled"}


# ============== Share Route ==============

@root_router.get("/s/{share_token}")
async def unified_public_share(share_token: str, request: Request, embed: bool = False):
    """
    Public share route. Renders shared content with enterprise branding.
    """
    from fastapi.responses import HTMLResponse
    from api.public_share import view_public_share, generate_error_html

    try:
        from api.public_share import public_shares_collection
        share = public_shares_collection.find_one({"share_token": share_token})

        if not share:
            return HTMLResponse(content=generate_error_html("Share Not Found", "This share link is invalid or has been revoked."))

        rendered_html = await view_public_share(share_token=share_token, embed=embed)
        return HTMLResponse(content=rendered_html)

    except Exception as e:
        logger.error(f"❌ [SHARE] Failed share route: {e}")
        from api.public_share import generate_error_html
        return HTMLResponse(content=generate_error_html("Error", "An error occurred while loading this content."))


# ============== Utility Functions (imported by other modules) ==============

def get_share_base_url(user_id: str, team_id: Optional[str] = None) -> str:
    """Get the base URL for generating share links (always uses BASE_URL for on-prem)"""
    return BASE_URL.rstrip("/")


def get_branding_for_resource(user_id: str, team_id: Optional[str] = None) -> dict:
    """
    Get enterprise branding for rendering shared content.
    Returns default branding if no enterprise branding is configured.
    """
    default_branding = {
        "enabled": False,
        "logo_url": None,
        "company_name": "Citra AI",
        "contact_email": None,
        "website_url": None,
        "primary_color": "#6366F1",
        "secondary_color": "#4F46E5",
        "show_powered_by": False
    }

    try:
        branding_col = get_enterprise_branding_collection()
        doc = branding_col.find_one({"_id": ENTERPRISE_DOC_ID})

        if not doc:
            return default_branding

        logo_url = None
        if doc.get("logo") and doc["logo"].get("s3_key"):
            try:
                from bucket import generate_download_url
                logo_url = generate_download_url(doc["logo"]["s3_key"], expiry_seconds=3600)
            except Exception:
                logo_url = doc["logo"].get("url")

        return {
            "enabled": True,
            "logo_url": logo_url,
            "company_name": doc.get("company_name"),
            "contact_email": doc.get("contact_email"),
            "contact_address": doc.get("contact_address"),
            "contact_phone": doc.get("contact_phone"),
            "website_url": doc.get("website_url"),
            "primary_color": doc.get("colors", {}).get("primary"),
            "secondary_color": doc.get("colors", {}).get("secondary"),
            "show_powered_by": doc.get("show_powered_by", False)
        }
    except Exception as e:
        logger.warning(f"Failed to fetch enterprise branding: {e}")
        return default_branding
