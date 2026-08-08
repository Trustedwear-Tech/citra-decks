"""
printable Analytics API
Track and retrieve analytics for shared printables.
"""
import logging
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
analytics_collection = mongo_manager.get_sync_collection("printable_analytics")
printables_collection = mongo_manager.get_sync_collection("printables")


# ============================================================================
# MODELS
# ============================================================================

class TrackEventRequest(BaseModel):
    event_type: str  # "view_start", "PAGE_view", "view_end"
    printable_id: str
    viewer_id: str
    session_id: Optional[str] = None
    PAGE_index: Optional[int] = None
    duration_ms: Optional[int] = None
    referrer: Optional[str] = None
    device_type: Optional[str] = None


class PAGEStats(BaseModel):
    PAGE_index: int
    total_views: int
    avg_duration_ms: float
    drop_off_count: int  # Number of viewers who left at this PAGE


class ViewerInfo(BaseModel):
    viewer_id: str
    session_id: str
    viewed_at: datetime
    duration_ms: int
    device_type: str
    location: Optional[str] = None
    PAGES_viewed: int


class AnalyticsResponse(BaseModel):
    printable_id: str
    total_views: int
    unique_viewers: int
    avg_duration_ms: float
    completion_rate: float  # % of viewers who viewed all PAGES
    PAGE_stats: List[PAGEStats]
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
async def track_event(request: Request, event: TrackEventRequest):
    """
    Track analytics event for a shared printable.
    Called from the tracking script injected into shared printables.
    """
    try:
        # Get client IP for geolocation
        client_ip = request.client.host if request.client else None
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        
        # Check if printable has analytics enabled
        printable = printables_collection.find_one({"_id": event.printable_id})
        if not printable:
            # Silently ignore - don't reveal if printable exists
            return {"status": "ok"}
        
        # Check if analytics is disabled for this printable
        if printable.get("analytics_enabled") == False:
            return {"status": "ok"}
        
        now = datetime.utcnow()
        
        if event.event_type == "view_start":
            # Get location from IP
            location = await get_location_from_ip(client_ip) if client_ip else None
            
            # Create new analytics session
            session_doc = {
                "printable_id": event.printable_id,
                "viewer_id": event.viewer_id,
                "session_id": event.session_id or f"{event.viewer_id}_{int(now.timestamp())}",
                "started_at": now,
                "ended_at": None,
                "total_duration_ms": 0,
                "device_type": event.device_type or "unknown",
                "referrer": event.referrer,
                "ip_address": client_ip,
                "location": location,
                "PAGE_views": [],
                "completed": False
            }
            analytics_collection.insert_one(session_doc)
            logger.info(f"📊 [ANALYTICS] view_start: {event.printable_id} from {location or client_ip}")
            
        elif event.event_type == "PAGE_view":
            # Update existing session with PAGE view
            analytics_collection.update_one(
                {
                    "printable_id": event.printable_id,
                    "viewer_id": event.viewer_id,
                    "ended_at": None  # Active session
                },
                {
                    "$push": {
                        "PAGE_views": {
                            "PAGE_index": event.PAGE_index,
                            "duration_ms": event.duration_ms or 0,
                            "viewed_at": now
                        }
                    }
                },
                upsert=False
            )
            logger.debug(f"📊 [ANALYTICS] PAGE_view: PAGE {event.PAGE_index} for {event.duration_ms}ms")
            
        elif event.event_type == "view_end":
            # Get total PAGES for completion calculation
            total_PAGES = len(printable.get("PAGES", []))
            
            # Mark session as ended
            result = analytics_collection.update_one(
                {
                    "printable_id": event.printable_id,
                    "viewer_id": event.viewer_id,
                    "ended_at": None
                },
                {
                    "$set": {
                        "ended_at": now,
                        "completed": event.PAGE_index >= (total_PAGES - 1) if total_PAGES > 0 else False
                    },
                    "$push": {
                        "PAGE_views": {
                            "PAGE_index": event.PAGE_index,
                            "duration_ms": event.duration_ms or 0,
                            "viewed_at": now
                        }
                    }
                }
            )
            
            # Calculate total duration from PAGE views
            if result.modified_count > 0:
                session = analytics_collection.find_one({
                    "printable_id": event.printable_id,
                    "viewer_id": event.viewer_id,
                    "ended_at": now
                })
                if session:
                    total_duration = sum(sv.get("duration_ms", 0) for sv in session.get("PAGE_views", []))
                    analytics_collection.update_one(
                        {"_id": session["_id"]},
                        {"$set": {"total_duration_ms": total_duration}}
                    )
            
            logger.info(f"📊 [ANALYTICS] view_end: {event.printable_id}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"❌ [ANALYTICS] Track error: {e}")
        # Don't expose errors to client
        return {"status": "ok"}


# ============================================================================
# GET ANALYTICS ENDPOINT (Authenticated - owner only)
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
        # Get user_id from request (set by auth middleware)
        user_id = getattr(request.state, "user_id", None)
        
        # Verify ownership
        printable = printables_collection.find_one({"_id": printable_id})
        if not printable:
            raise HTTPException(status_code=404, detail="printable not found")
        
        # Check ownership (if user_id is available)
        if user_id and printable.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get analytics for the time period
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        sessions = list(analytics_collection.find({
            "printable_id": printable_id,
            "started_at": {"$gte": cutoff_date}
        }).sort("started_at", -1))
        
        if not sessions:
            return {
                "printable_id": printable_id,
                "total_views": 0,
                "unique_viewers": 0,
                "avg_duration_ms": 0,
                "completion_rate": 0,
                "PAGE_stats": [],
                "recent_viewers": []
            }
        
        # Calculate stats
        total_views = len(sessions)
        unique_viewers = len(set(s.get("viewer_id") for s in sessions))
        
        completed_sessions = [s for s in sessions if s.get("completed")]
        completion_rate = (len(completed_sessions) / total_views * 100) if total_views > 0 else 0
        
        total_duration = sum(s.get("total_duration_ms", 0) for s in sessions)
        avg_duration = total_duration / total_views if total_views > 0 else 0
        
        # Calculate PAGE stats
        total_PAGES = len(printable.get("PAGES", []))
        PAGE_stats = []
        
        for PAGE_idx in range(total_PAGES):
            PAGE_views = []
            drop_offs = 0
            
            for session in sessions:
                session_PAGES = session.get("PAGE_views", [])
                for sv in session_PAGES:
                    if sv.get("PAGE_index") == PAGE_idx:
                        PAGE_views.append(sv.get("duration_ms", 0))
                
                # Check for drop-off at this PAGE
                if session_PAGES:
                    max_PAGE = max(sv.get("PAGE_index", 0) for sv in session_PAGES)
                    if max_PAGE == PAGE_idx and not session.get("completed"):
                        drop_offs += 1
            
            PAGE_stats.append({
                "PAGE_index": PAGE_idx,
                "total_views": len(PAGE_views),
                "avg_duration_ms": sum(PAGE_views) / len(PAGE_views) if PAGE_views else 0,
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
                "PAGES_viewed": len(session.get("PAGE_views", []))
            })
        
        return {
            "printable_id": printable_id,
            "total_views": total_views,
            "unique_viewers": unique_viewers,
            "avg_duration_ms": round(avg_duration),
            "completion_rate": round(completion_rate, 1),
            "PAGE_stats": PAGE_stats,
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

@router.post("/printable/{printable_id}/toggle")
async def toggle_analytics(
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
            raise HTTPException(status_code=404, detail="printable not found")
        
        if user_id and printable.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Update analytics_enabled flag
        printables_collection.update_one(
            {"_id": printable_id},
            {"$set": {"analytics_enabled": enabled}}
        )
        
        logger.info(f"📊 [ANALYTICS] Tracking {'enabled' if enabled else 'disabled'} for {printable_id}")
        
        return {"status": "ok", "analytics_enabled": enabled}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [ANALYTICS] Toggle error: {e}")
        raise HTTPException(status_code=500, detail="Failed to toggle analytics")
