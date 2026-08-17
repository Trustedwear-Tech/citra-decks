# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""
Presentation Analytics API
Track and retrieve analytics for shared presentations.
"""
import logging
import json
import traceback
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from bson import ObjectId
import httpx

from citra_mongo import MongoDBManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

# MongoDB setup
mongo_manager = MongoDBManager()

# Collections - using mongo_manager for proper connection handling
analytics_collection = mongo_manager.get_sync_collection("presentation_analytics")
presentations_collection = mongo_manager.get_sync_collection("presentations")
printables_collection = mongo_manager.get_sync_collection("printables")


# ============================================================================
# MODELS
# ============================================================================

class TrackEventRequest(BaseModel):
    event_type: str  # "view_start", "slide_view", "view_end"
    presentation_id: str
    viewer_id: str
    session_id: Optional[str] = None
    slide_index: Optional[int] = None
    duration_ms: Optional[int] = None
    referrer: Optional[str] = None
    device_type: Optional[str] = None
    content_type: Optional[str] = "presentation"  # "presentation" or "printable"


class SlideStats(BaseModel):
    slide_index: int
    total_views: int
    avg_duration_ms: float
    drop_off_count: int  # Number of viewers who left at this slide


class ViewerInfo(BaseModel):
    viewer_id: str
    session_id: str
    viewed_at: datetime
    duration_ms: int
    device_type: str
    location: Optional[str] = None
    slides_viewed: int


class AnalyticsResponse(BaseModel):
    presentation_id: str
    total_views: int
    unique_viewers: int
    avg_duration_ms: float
    completion_rate: float  # % of viewers who viewed all slides
    slide_stats: List[SlideStats]
    recent_viewers: List[ViewerInfo]


# ============================================================================
# IP GEOLOCATION
# ============================================================================

async def get_location_from_ip(ip: str) -> Optional[str]:
    """Get approximate location from IP address.
    
    Returns None — external geolocation disabled for on-premises deployment.
    """
    if ip in ["127.0.0.1", "localhost", "::1"]:
        return "Local"
    
    return None


# ============================================================================
# TRACK ENDPOINT (Public - no auth required)
# ============================================================================

@router.post("/track")
async def track_event(request: Request):
    """
    Track analytics event for a shared presentation.
    Called from the tracking script injected into shared presentations.
    
    NOTE: We intentionally do NOT declare a Pydantic body parameter here.
    navigator.sendBeacon may send the body as raw bytes or with text/plain
    content-type, which causes FastAPI's automatic body parsing to fail with
    a RequestValidationError BEFORE the function body executes. Instead, we
    manually parse the raw body to handle all content-type variants.
    """
    try:
        # Manually parse the request body as JSON
        # This handles cases where navigator.sendBeacon sends 'text/plain'
        # or the body arrives as raw bytes regardless of Content-Type header
        try:
            raw_body = await request.body()
            if not raw_body:
                return {"status": "ok", "detail": "empty body"}
            
            body_str = raw_body.decode('utf-8') if isinstance(raw_body, bytes) else raw_body
            data = json.loads(body_str)
            event = TrackEventRequest(**data)
        except Exception as e:
            logger.warning(f"⚠️ [ANALYTICS] Failed to parse track event body: {e}")
            return {"status": "ok", "detail": f"parse_error: {str(e)}"}

        # Get client IP for geolocation
        client_ip = request.client.host if request.client else None
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        
        # Check if presentation/printable has analytics enabled
        content_collection = printables_collection if event.content_type == "printable" else presentations_collection
        content_doc = content_collection.find_one({"_id": event.presentation_id})
        if not content_doc:
            # Silently ignore - don't reveal if content exists
            return {"status": "ok"}
        
        # Check if analytics is disabled
        if content_doc.get("analytics_enabled") == False:
            return {"status": "ok"}
        
        now = datetime.utcnow()
        
        if event.event_type == "view_start":
            # Get location from IP
            location = await get_location_from_ip(client_ip) if client_ip else None
            
            # Create new analytics session
            session_doc = {
                "presentation_id": event.presentation_id,
                "viewer_id": event.viewer_id,
                "session_id": event.session_id or f"{event.viewer_id}_{int(now.timestamp())}",
                "started_at": now,
                "ended_at": None,
                "total_duration_ms": 0,
                "device_type": event.device_type or "unknown",
                "referrer": event.referrer,
                "ip_address": client_ip,
                "location": location,
                "slide_views": [],
                "completed": False
            }
            analytics_collection.insert_one(session_doc)
            logger.info(f"📊 [ANALYTICS] view_start: {event.presentation_id} from {location or client_ip}")
            
        elif event.event_type == "slide_view":
            # Update existing session with slide view
            analytics_collection.update_one(
                {
                    "presentation_id": event.presentation_id,
                    "viewer_id": event.viewer_id,
                    "ended_at": None  # Active session
                },
                {
                    "$push": {
                        "slide_views": {
                            "slide_index": event.slide_index,
                            "duration_ms": event.duration_ms or 0,
                            "viewed_at": now
                        }
                    }
                },
                upsert=False
            )
            logger.debug(f"📊 [ANALYTICS] slide_view: slide {event.slide_index} for {event.duration_ms}ms")
            
        elif event.event_type == "view_end":
            # Get total slides/pages for completion calculation
            if event.content_type == "printable":
                total_slides = len(content_doc.get("PAGES", []))
            else:
                total_slides = len(content_doc.get("slides", []))
            
            # Mark session as ended
            result = analytics_collection.update_one(
                {
                    "presentation_id": event.presentation_id,
                    "viewer_id": event.viewer_id,
                    "ended_at": None
                },
                {
                    "$set": {
                        "ended_at": now,
                        "completed": event.slide_index >= (total_slides - 1) if total_slides > 0 else False
                    },
                    "$push": {
                        "slide_views": {
                            "slide_index": event.slide_index,
                            "duration_ms": event.duration_ms or 0,
                            "viewed_at": now
                        }
                    }
                }
            )
            
            # Calculate total duration from slide views
            if result.modified_count > 0:
                session = analytics_collection.find_one({
                    "presentation_id": event.presentation_id,
                    "viewer_id": event.viewer_id,
                    "ended_at": now
                })
                if session:
                    total_duration = sum(sv.get("duration_ms", 0) for sv in session.get("slide_views", []))
                    analytics_collection.update_one(
                        {"_id": session["_id"]},
                        {"$set": {"total_duration_ms": total_duration}}
                    )
            
            logger.info(f"📊 [ANALYTICS] view_end: {event.presentation_id}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"❌ [ANALYTICS] Track error: {e}")
        # Don't expose errors to client
        return {"status": "ok"}


# ============================================================================
# GET ANALYTICS ENDPOINT (Authenticated - owner only)
# ============================================================================

@router.get("/presentation/{presentation_id}")
async def get_presentation_analytics(
    presentation_id: str,
    request: Request,
    days: int = 30
):
    """
    Get analytics for a presentation.
    Only the presentation owner can access this.
    """
    try:
        # Get user_id from request (set by auth middleware)
        user_id = getattr(request.state, "user_id", None)
        
        # Verify ownership
        presentation = presentations_collection.find_one({"_id": presentation_id})
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        # Check ownership (if user_id is available)
        if user_id and presentation.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get analytics for the time period
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        sessions = list(analytics_collection.find({
            "presentation_id": presentation_id,
            "started_at": {"$gte": cutoff_date}
        }).sort("started_at", -1))
        
        if not sessions:
            return {
                "presentation_id": presentation_id,
                "total_views": 0,
                "unique_viewers": 0,
                "avg_duration_ms": 0,
                "completion_rate": 0,
                "slide_stats": [],
                "recent_viewers": []
            }
        
        # Calculate stats
        total_views = len(sessions)
        unique_viewers = len(set(s.get("viewer_id") for s in sessions))
        
        completed_sessions = [s for s in sessions if s.get("completed")]
        completion_rate = (len(completed_sessions) / total_views * 100) if total_views > 0 else 0
        
        total_duration = sum(s.get("total_duration_ms", 0) for s in sessions)
        avg_duration = total_duration / total_views if total_views > 0 else 0
        
        # Calculate slide stats
        total_slides = len(presentation.get("slides", []))
        slide_stats = []
        
        for slide_idx in range(total_slides):
            slide_views = []
            drop_offs = 0
            
            for session in sessions:
                session_slides = session.get("slide_views", [])
                for sv in session_slides:
                    if sv.get("slide_index") == slide_idx:
                        slide_views.append(sv.get("duration_ms", 0))
                
                # Check for drop-off at this slide
                if session_slides:
                    max_slide = max(sv.get("slide_index", 0) for sv in session_slides)
                    if max_slide == slide_idx and not session.get("completed"):
                        drop_offs += 1
            
            slide_stats.append({
                "slide_index": slide_idx,
                "total_views": len(slide_views),
                "avg_duration_ms": sum(slide_views) / len(slide_views) if slide_views else 0,
                "drop_off_count": drop_offs
            })
        
        # Recent viewers (last 20)
        recent_viewers = []
        for session in sessions[:20]:
            recent_viewers.append({
                "viewer_id": session.get("viewer_id", "")[:8] + "...",  # Truncated for privacy
                "session_id": session.get("session_id", ""),
                "viewed_at": session.get("started_at"),
                "duration_ms": session.get("total_duration_ms", 0),
                "device_type": session.get("device_type", "unknown"),
                "location": session.get("location"),
                "slides_viewed": len(session.get("slide_views", []))
            })
        
        return {
            "presentation_id": presentation_id,
            "total_views": total_views,
            "unique_viewers": unique_viewers,
            "avg_duration_ms": round(avg_duration),
            "completion_rate": round(completion_rate, 1),
            "slide_stats": slide_stats,
            "recent_viewers": recent_viewers
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [ANALYTICS] Get analytics error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve analytics")


# ============================================================================
# TOGGLE ANALYTICS ENDPOINT
# ============================================================================

@router.post("/presentation/{presentation_id}/toggle")
async def toggle_analytics(
    presentation_id: str,
    request: Request,
    enabled: bool = True
):
    """
    Enable or disable analytics tracking for a presentation.
    """
    try:
        user_id = getattr(request.state, "user_id", None)
        
        # Verify ownership
        presentation = presentations_collection.find_one({"_id": presentation_id})
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        if user_id and presentation.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Update analytics_enabled flag
        presentations_collection.update_one(
            {"_id": presentation_id},
            {"$set": {"analytics_enabled": enabled}}
        )
        
        logger.info(f"📊 [ANALYTICS] Tracking {'enabled' if enabled else 'disabled'} for {presentation_id}")
        
        return {"status": "ok", "analytics_enabled": enabled}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [ANALYTICS] Toggle error: {e}")
        raise HTTPException(status_code=500, detail="Failed to toggle analytics")


# ============================================================================
# PRINTABLE ANALYTICS ENDPOINTS
# ============================================================================

@router.get("/printable/{printable_id}")
async def get_printable_analytics(
    printable_id: str,
    request: Request,
    days: int = 30
):
    """
    Get analytics for a printable.
    Only the printable owner can access this.
    """
    try:
        user_id = getattr(request.state, "user_id", None)
        
        # Verify ownership
        printable = printables_collection.find_one({"_id": printable_id})
        if not printable:
            raise HTTPException(status_code=404, detail="Printable not found")
        
        if user_id and printable.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get analytics for the time period
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        sessions = list(analytics_collection.find({
            "presentation_id": printable_id,
            "started_at": {"$gte": cutoff_date}
        }).sort("started_at", -1))
        
        if not sessions:
            return {
                "presentation_id": printable_id,
                "total_views": 0,
                "unique_viewers": 0,
                "avg_duration_ms": 0,
                "completion_rate": 0,
                "slide_stats": [],
                "recent_viewers": []
            }
        
        # Calculate stats
        total_views = len(sessions)
        unique_viewers = len(set(s.get("viewer_id") for s in sessions))
        
        completed_sessions = [s for s in sessions if s.get("completed")]
        completion_rate = (len(completed_sessions) / total_views * 100) if total_views > 0 else 0
        
        total_duration = sum(s.get("total_duration_ms", 0) for s in sessions)
        avg_duration = total_duration / total_views if total_views > 0 else 0
        
        # Calculate page stats (printables use PAGES)
        total_pages = len(printable.get("PAGES", []))
        page_stats = []
        
        for page_idx in range(total_pages):
            page_views = []
            drop_offs = 0
            
            for session in sessions:
                session_slides = session.get("slide_views", [])
                for sv in session_slides:
                    if sv.get("slide_index") == page_idx:
                        page_views.append(sv.get("duration_ms", 0))
                
                # Check for drop-off at this page
                if session_slides:
                    max_page = max(sv.get("slide_index", 0) for sv in session_slides)
                    if max_page == page_idx and not session.get("completed"):
                        drop_offs += 1
            
            page_stats.append({
                "slide_index": page_idx,
                "total_views": len(page_views),
                "avg_duration_ms": sum(page_views) / len(page_views) if page_views else 0,
                "drop_off_count": drop_offs
            })
        
        # Recent viewers (last 20)
        recent_viewers = []
        for session in sessions[:20]:
            recent_viewers.append({
                "viewer_id": session.get("viewer_id", "")[:8] + "...",
                "session_id": session.get("session_id", ""),
                "viewed_at": session.get("started_at"),
                "duration_ms": session.get("total_duration_ms", 0),
                "device_type": session.get("device_type", "unknown"),
                "location": session.get("location"),
                "pages_viewed": len(session.get("slide_views", []))
            })
        
        return {
            "presentation_id": printable_id,
            "total_views": total_views,
            "unique_viewers": unique_viewers,
            "avg_duration_ms": round(avg_duration),
            "completion_rate": round(completion_rate, 1),
            "page_stats": page_stats,
            "recent_viewers": recent_viewers
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [ANALYTICS] Get printable analytics error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve analytics")


@router.post("/printable/{printable_id}/toggle")
async def toggle_printable_analytics(
    printable_id: str,
    request: Request,
    enabled: bool = True
):
    """
    Enable or disable analytics tracking for a printable.
    """
    try:
        user_id = getattr(request.state, "user_id", None)
        
        # Verify ownership
        printable = printables_collection.find_one({"_id": printable_id})
        if not printable:
            raise HTTPException(status_code=404, detail="Printable not found")
        
        if user_id and printable.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Update analytics_enabled flag
        printables_collection.update_one(
            {"_id": printable_id},
            {"$set": {"analytics_enabled": enabled}}
        )
        
        logger.info(f"📊 [ANALYTICS] Printable tracking {'enabled' if enabled else 'disabled'} for {printable_id}")
        
        return {"status": "ok", "analytics_enabled": enabled}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [ANALYTICS] Printable toggle error: {e}")
        raise HTTPException(status_code=500, detail="Failed to toggle analytics")
