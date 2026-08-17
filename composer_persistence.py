# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""
Composer Report Persistence - MongoDB CRUD endpoints for saving/loading reports
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from bson import ObjectId
import logging

# Import MongoDB connection
# Import MongoDB connection
from citra_mongo import MongoDBManager
from services.image_processor import image_processor
from citra_auth import get_secure_user_id

logger = logging.getLogger(__name__)

router = APIRouter()

# Get MongoDB database and collection for reports
mongo_manager = MongoDBManager()
reports_collection = mongo_manager.get_sync_collection("composer_reports")


class ReportPage(BaseModel):
    id: str
    order: int
    title: str
    content: str
    wordCount: int = 0


class ReportMetadata(BaseModel):
    title: str = "Untitled Report"
    author: Optional[str] = None
    description: Optional[str] = None
    description: Optional[str] = None
    overall_goal: Optional[str] = None
    report_type: str = "report"  # report, case_review, research, proposal, summary


class ReportCreate(BaseModel):
    team_id: Optional[str] = None  # Team/Workspace ID (null for personal workspace)
    title: str = "Untitled Report"
    goal: Optional[str] = None
    report_type: str = "report"
    pages: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}
    thumbnail: Optional[str] = None  # Base64 or URL for report thumbnail
    folder_id: Optional[str] = None  # Report's dedicated folder (one per artifact)


class ReportUpdate(BaseModel):
    title: Optional[str] = None
    goal: Optional[str] = None
    report_type: Optional[str] = None
    pages: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    thumbnail: Optional[str] = None  # Base64 or URL for report thumbnail
    folder_id: Optional[str] = None  # Report's dedicated folder (one per artifact)


def serialize_report(report: dict) -> dict:
    """Convert MongoDB document to JSON-serializable format"""
    if report:
        report["id"] = str(report.pop("_id"))
        if "created_at" in report and isinstance(report["created_at"], datetime):
            report["created_at"] = report["created_at"].isoformat()
        if "updated_at" in report and isinstance(report["updated_at"], datetime):
            report["updated_at"] = report["updated_at"].isoformat()
    return report


@router.post("/composer/reports")
async def create_report(http_request: Request, payload: ReportCreate):
    """
    Create a new report.
    
    SECURITY: Uses authenticated user_id from JWT token.
    """
    authenticated_user_id = get_secure_user_id(http_request)

    # Personal-SA ownership stamp: reports are personal-output resources.
    _personal_sa_id = getattr(http_request.state, "personal_sa_id", "") or ""
    _owner_org_id = getattr(http_request.state, "org_id", "") or ""
    if not _personal_sa_id:
        logger.warning(
            "[COMPOSER] reject: personal_sa_id missing for user=%s org=%s",
            authenticated_user_id, _owner_org_id,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "code": "personal_sa_id_missing",
                "message": (
                    "Cannot create report: your Personal Service Account is not "
                    "provisioned. Sign out + sign in to refresh, or contact your "
                    "admin to run 'Fix Service Accounts' on your user record."
                ),
            },
        )

    try:
        logger.info(f"📄 [COMPOSER] Creating report for authenticated user: {authenticated_user_id}")
        
        # Generate ID first to allow S3 image path construction
        new_id = ObjectId()
        report_id = str(new_id)

        # Process thumbnail if provided (base64 -> S3) - Use authenticated user
        thumbnail_url = None
        if payload.thumbnail:
            try:
                if payload.thumbnail.startswith('data:image'):
                    thumbnail_url = image_processor.upload_base64_image(
                        payload.thumbnail,
                        authenticated_user_id,  # SECURITY: Use authenticated user
                        "reports",
                        f"{report_id}_thumbnail"
                    )
                elif payload.thumbnail.startswith('http'):
                    thumbnail_url = payload.thumbnail
            except Exception as thumb_err:
                logger.warning(f"⚠️ [COMPOSER] Thumbnail processing failed: {thumb_err}")

        report_doc = {
            "user_id": authenticated_user_id,  # SECURITY: Use authenticated user from JWT
            "team_id": payload.team_id,
            "title": payload.title,
            "goal": payload.goal,
            "report_type": payload.report_type,
            "pages": payload.pages,
            "metadata": payload.metadata,
            "owner_type": "service_account",
            "owner_id": _personal_sa_id,
            "org_id": _owner_org_id or None,
            "thumbnail": thumbnail_url,
            "folder_id": payload.folder_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        report_doc["_id"] = new_id

        # Process images (Extract Base64 -> S3) - Use authenticated user
        if report_doc.get("pages"):
            updated_pages, _ = await image_processor.process_report_content(
                report_doc["pages"], 
                authenticated_user_id,  # SECURITY: Use authenticated user
                report_id
            )
            report_doc["pages"] = updated_pages
        
        result = reports_collection.insert_one(report_doc)
        # report_id is already set
        
        logger.info(f"✅ [COMPOSER] Report created: {report_id} for user {authenticated_user_id}")
        
        return {
            "success": True,
            "report_id": report_id,
            "message": "Report created successfully"
        }
        
    except Exception as e:
        logger.error(f"❌ [COMPOSER] Failed to create report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/composer/reports")
async def list_reports(request: Request, team_id: Optional[str] = None, all_workspaces: Optional[bool] = False):
    """
    List all reports for a user or team. Uses JWT auth.
    """
    try:
        authenticated_user_id = get_secure_user_id(request)
        
        logger.info(f"📄 [COMPOSER] Listing reports for authenticated user: {authenticated_user_id}, team: {team_id}, all_workspaces: {all_workspaces}")
        
        # Build query based on team context
        if all_workspaces:
            # User-level: all reports across all workspaces
            match_query = {"user_id": authenticated_user_id}
        elif team_id:
            # Team workspace: show all team reports
            match_query = {"team_id": team_id, "user_id": authenticated_user_id}
        else:
            # Personal workspace: show user's personal reports (no team_id)
            match_query = {
                "user_id": authenticated_user_id,
                "$or": [
                    {"team_id": {"$exists": False}},
                    {"team_id": None}
                ]
            }
        
        # Use aggregation for efficient projection and array counting
        pipeline = [
            {"$match": match_query},
            {"$sort": {"updated_at": -1}},
            {"$project": {
                "_id": 1,
                "title": {"$ifNull": ["$title", "Untitled Report"]},
                "goal": 1,
                "report_type": {"$ifNull": ["$report_type", "report"]},
                "thumbnail": 1,
                "created_at": 1,
                "updated_at": 1,
                "user_id": 1,
                "team_id": 1,
                # Efficiently count pages without returning the array
                "page_count": {"$size": {"$ifNull": ["$pages", []]}}
            }}
        ]

        cursor = reports_collection.aggregate(pipeline)
        
        reports = []
        for doc in cursor:
            # Generate presigned URL for thumbnail if it's an S3 key
            thumbnail_url = doc.get("thumbnail")
            if thumbnail_url and thumbnail_url.startswith("s3://"):
                try:
                    thumbnail_url = image_processor.generate_presigned_url(thumbnail_url)
                except Exception as url_err:
                    logger.warning(f"⚠️ [COMPOSER] Failed to generate thumbnail URL: {url_err}")
                    thumbnail_url = None
            
            reports.append({
                "id": str(doc["_id"]),
                "title": doc.get("title"),
                "goal": doc.get("goal"),
                "report_type": doc.get("report_type"),
                "page_count": doc.get("page_count", 0),
                "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
                "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
                "thumbnail": thumbnail_url,
                "is_shared": False
            })
        
        # Fetch reports shared with the user via authorization service
        shared_reports = []
        try:
            from services.authorization_service import get_authorization_service
            auth_service = get_authorization_service()
            
            # Get accessible reports (shared with user)
            accessible_result = await auth_service.get_accessible_resources(
                user_id=authenticated_user_id,
                resource_type="report",
                team_id=team_id if team_id and not all_workspaces else None
            )
            
            if accessible_result.get("success"):
                # Get shared resource IDs (not owned by user)
                shared_ids = [
                    r["resource_id"] for r in accessible_result.get("shared_details", [])
                    if not r.get("is_owner", False)
                ]
                
                if shared_ids:
                    # Fetch report details for shared ones
                    from bson import ObjectId
                    shared_query = {"_id": {"$in": [ObjectId(sid) if ObjectId.is_valid(sid) else sid for sid in shared_ids]}}
                    
                    shared_pipeline = [
                        {"$match": shared_query},
                        {"$sort": {"updated_at": -1}},
                        {"$project": {
                            "_id": 1,
                            "title": {"$ifNull": ["$title", "Untitled Report"]},
                            "goal": 1,
                            "report_type": {"$ifNull": ["$report_type", "report"]},
                            "thumbnail": 1,
                            "created_at": 1,
                            "updated_at": 1,
                            "user_id": 1,
                            "team_id": 1,
                            "page_count": {"$size": {"$ifNull": ["$pages", []]}}
                        }}
                    ]
                    
                    shared_cursor = reports_collection.aggregate(shared_pipeline)
                    
                    for doc in shared_cursor:
                        thumbnail_url = doc.get("thumbnail")
                        if thumbnail_url and thumbnail_url.startswith("s3://"):
                            try:
                                thumbnail_url = image_processor.generate_presigned_url(thumbnail_url)
                            except Exception:
                                thumbnail_url = None
                        
                        shared_reports.append({
                            "id": str(doc["_id"]),
                            "title": doc.get("title"),
                            "goal": doc.get("goal"),
                            "report_type": doc.get("report_type"),
                            "page_count": doc.get("page_count", 0),
                            "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
                            "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
                            "thumbnail": thumbnail_url,
                            "is_shared": True,
                            "shared_by": doc.get("user_id")
                        })
                    
                    logger.info(f"📤 [COMPOSER] Found {len(shared_reports)} shared reports for user {authenticated_user_id}")
        except Exception as share_e:
            logger.warning(f"⚠️ [COMPOSER] Could not fetch shared reports: {share_e}")
        
        # Combine owned and shared (avoid duplicates)
        owned_ids = {r["id"] for r in reports}
        all_reports = reports + [r for r in shared_reports if r["id"] not in owned_ids]
        
        logger.info(f"✅ [COMPOSER] Found {len(reports)} owned + {len(shared_reports)} shared reports")
        
        return {
            "success": True,
            "reports": all_reports,
            "count": len(all_reports),
            "owned_count": len(reports),
            "shared_count": len(shared_reports)
        }
        
    except Exception as e:
        logger.error(f"❌ [COMPOSER] Failed to list reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/composer/reports/{report_id}")
async def get_report(report_id: str, request: Request):
    """
    Get a single report by ID.
    
    SECURITY: Validates that the authenticated user owns the report or has shared access.
    
    Args:
        report_id: Report ID
        request: FastAPI request (contains JWT auth)
        
    Raises:
        HTTPException 403: If user doesn't own or have shared access to the report
        HTTPException 404: If report not found
    """
    try:
        authenticated_user_id = get_secure_user_id(request)
        
        logger.info(f"📄 [COMPOSER] Getting report: {report_id} for user: {authenticated_user_id}")
        
        report = reports_collection.find_one({"_id": ObjectId(report_id)})
        
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        
        # SECURITY: Verify ownership or shared access
        report_owner = report.get("user_id")
        shared_with = report.get("shared_with", [])  # List of user_ids/emails with access
        
        has_access = (
            report_owner == authenticated_user_id or
            authenticated_user_id in shared_with
        )
        
        # Also check centralized permissions if not found in legacy fields
        if not has_access:
            try:
                from services.authorization_service import get_authorization_service
                auth_service = get_authorization_service()
                access_result = await auth_service.check_access(
                    user_id=authenticated_user_id,
                    resource_id=report_id,
                    resource_type="report",
                    required_permission="read"
                )
                has_access = access_result.get("allowed", False)
            except Exception as auth_err:
                logger.warning(f"⚠️ [COMPOSER] Auth service check failed: {auth_err}")
        
        if not has_access:
            logger.warning(f"🔒 Access denied: User {authenticated_user_id} tried to access report {report_id} owned by {report_owner}")
            raise HTTPException(
                status_code=403, 
                detail="Access denied. You don't have permission to view this report."
            )
        
        # Inject Presigned URLs for secure viewing
        if "pages" in report:
            report["pages"] = image_processor.inject_presigned_urls_report(report["pages"])

        logger.info(f"✅ [COMPOSER] Report found: {report_id}")
        
        return {
            "success": True,
            "report": serialize_report(report)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [COMPOSER] Failed to get report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/composer/reports/{report_id}")
async def update_report(report_id: str, payload: ReportUpdate, request: Request):
    """
    Update an existing report.
    
    SECURITY: Only the owner can update their report.
    """
    try:
        authenticated_user_id = get_secure_user_id(request)
        
        logger.info(f"📄 [COMPOSER] Updating report: {report_id} by user: {authenticated_user_id}")
        
        # Check permissions and existing doc
        existing = reports_collection.find_one({"_id": ObjectId(report_id)})
        
        if not existing:
            raise HTTPException(status_code=404, detail="Report not found")
        
        # SECURITY: Verify ownership or shared write access
        report_owner = existing.get("user_id")
        if report_owner != authenticated_user_id:
            # Check centralized permissions for write access
            try:
                from services.authorization_service import get_authorization_service
                auth_service = get_authorization_service()
                access_result = await auth_service.check_access(
                    user_id=authenticated_user_id,
                    resource_id=report_id,
                    resource_type="report",
                    required_permission="write"
                )
                if not access_result.get("allowed"):
                    logger.warning(f"🔒 Access denied: User {authenticated_user_id} tried to update report {report_id} owned by {report_owner}")
                    raise HTTPException(
                        status_code=403, 
                        detail="Access denied. You don't have permission to update this report."
                    )
                logger.info(f"✅ [COMPOSER] Write access granted to collaborator {authenticated_user_id} for report {report_id}")
            except HTTPException:
                raise
            except Exception as auth_err:
                logger.warning(f"⚠️ [COMPOSER] Auth check failed: {auth_err}")
                raise HTTPException(
                    status_code=403, 
                    detail="Access denied. You don't have permission to update this report."
                )
        
        update_doc = {"updated_at": datetime.utcnow()}
        
        if payload.title is not None:
            update_doc["title"] = payload.title
        if payload.goal is not None:
            update_doc["goal"] = payload.goal
        if payload.report_type is not None:
            update_doc["report_type"] = payload.report_type
        if payload.pages is not None:
            update_doc["pages"] = payload.pages
        if payload.metadata is not None:
            update_doc["metadata"] = payload.metadata
        if payload.folder_id is not None:
            update_doc["folder_id"] = payload.folder_id

        # Process thumbnail if provided
        if payload.thumbnail is not None:
            if report_owner:
                try:
                    if payload.thumbnail.startswith('data:image'):
                        thumbnail_url = image_processor.upload_base64_image(
                            payload.thumbnail,
                            report_owner,
                            "reports",
                            f"{report_id}_thumbnail"
                        )
                        update_doc["thumbnail"] = thumbnail_url
                    elif payload.thumbnail.startswith('http'):
                        update_doc["thumbnail"] = payload.thumbnail
                except Exception as thumb_err:
                    logger.warning(f"⚠️ [COMPOSER] Thumbnail update failed: {thumb_err}")
             
        # Process images if pages are updated
        if payload.pages is not None:
            if report_owner:
                updated_pages, active_keys = await image_processor.process_report_content(
                    payload.pages,
                    report_owner,
                    report_id
                )
                update_doc["pages"] = updated_pages
                
                # Garbage Collect unused images
                image_processor.garbage_collect(report_owner, "reports", report_id, active_keys)
        
        result = reports_collection.update_one(
            {"_id": ObjectId(report_id)},
            {"$set": update_doc}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Report not found")
        
        logger.info(f"✅ [COMPOSER] Report updated: {report_id}")
        
        return {
            "success": True,
            "report_id": report_id,
            "message": "Report updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [COMPOSER] Failed to update report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/composer/reports/{report_id}")
async def delete_report(report_id: str, request: Request):
    """
    Delete a report.
    
    SECURITY: Only the owner can delete their report.
    
    Raises:
        HTTPException 403: If user is not the report owner
        HTTPException 404: If report not found
    """
    try:
        authenticated_user_id = get_secure_user_id(request)
        
        logger.info(f"📄 [COMPOSER] Deleting report: {report_id} by user: {authenticated_user_id}")
        
        # Get report to verify ownership and for S3 deletion
        report = reports_collection.find_one({"_id": ObjectId(report_id)})
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        
        # SECURITY: Verify ownership
        report_owner = report.get("user_id")
        if report_owner != authenticated_user_id:
            logger.warning(f"🔒 Access denied: User {authenticated_user_id} tried to delete report {report_id} owned by {report_owner}")
            raise HTTPException(
                status_code=403, 
                detail="Access denied. You don't have permission to delete this report."
            )
        
        # Delete S3 resources
        if report_owner:
            image_processor.delete_document_folder(report_owner, "reports", report_id)

        result = reports_collection.delete_one({"_id": ObjectId(report_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Report not found")
        
        logger.info(f"✅ [COMPOSER] Report deleted: {report_id} by {authenticated_user_id}")
        
        return {
            "success": True,
            "message": "Report deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [COMPOSER] Failed to delete report: {e}")
        raise HTTPException(status_code=500, detail=str(e))
