"""
Usage Trend API - Daily usage statistics endpoint
Provides daily usage trend data from credittransactions collection.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, status, Request
from fastapi.responses import JSONResponse

from services.daily_usage_trend_service import DailyUsageTrendService
from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
from citra_auth import get_secure_user_id

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter()


def _get_trend_service() -> DailyUsageTrendService:
    """Get trend service with a fresh async MongoDB client for the current event loop."""
    async_mongo_client = get_async_mongo_client()
    async_db = async_mongo_client[MONGODB_DATABASE]
    return DailyUsageTrendService(async_db)


@router.get("/get-daily-usage-trend")
async def get_daily_usage_trend(
    request: Request,
    days: int = Query(30, description="Number of days to retrieve (default: 30)")
):
    """
    GET /api/usage/get-daily-usage-trend
    Retrieves daily usage trend data from credittransactions collection.
    """
    try:
        user_id = get_secure_user_id(request)
        logger.info(f"📊 Fetching {days}-day usage trend for user: {user_id}")
        
        # Validate days parameter
        if days <= 0 or days > 365:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Days must be between 1 and 365"
            )
        
        # Get trend data from service (created per-request to avoid event loop mismatch)
        trend_service = _get_trend_service()
        result = await trend_service.get_daily_usage_trend(user_id, days)
        
        logger.info(f"✅ Retrieved {days}-day trend: {result['summary']['total_queries']} queries, {result['summary']['total_uploads']} uploads")
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching daily usage trend: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve daily usage trend: {str(e)}"
        )
