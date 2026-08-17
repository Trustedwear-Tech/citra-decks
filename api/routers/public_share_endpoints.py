# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

from fastapi import APIRouter, HTTPException, Request, Depends
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
from bson import ObjectId
import logging

from citra_mongo import MongoDBManager
from api.public_share import public_shares_collection, _LazyCollection

router = APIRouter()

mongo_manager = MongoDBManager()

# Use lazy collection proxy for reconnection-aware access
shared_with_me_collection = _LazyCollection('shared_with_me')
# Ensure index
try:
    shared_with_me_collection.create_index([("user_id", 1), ("content_type", 1), ("source_id", 1)], unique=True)
except Exception:
    pass

@router.post("/accept/{content_type}/{share_token}")
async def accept_share(content_type: str, share_token: str, request: Request):
    """
    Track that a user has accessed a shared item with Edit permission.
    This adds it to their 'Shared with Me' list.
    """
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # 1. Validate Share Token
    share = public_shares_collection.find_one({"share_token": share_token})
    if not share:
        raise HTTPException(status_code=404, detail="Share link invalid or revoked")
    
    if share["content_type"] != content_type:
        raise HTTPException(status_code=400, detail="Content type mismatch")
    
    # Check if edit permission (only track edit shares usually, or all?)
    # Requirement: "Enable users to share content with 'Edit' permission, display shared content in their lists"
    # We should probably track READ shares too if they are 'accepted' explicitly via deep link?
    # But usually 'shared with me' implies some persistent access.
    # For now, we allow tracking any accepted share.
    
    # 2. Upsert into shared_with_me
    shared_entry = {
        "user_id": user_id,
        "content_type": content_type,
        "source_id": share["source_id"],
        "share_token": share_token,
        "owner_id": share["user_id"],
        "title": share.get("title", "Untitled"),
        "permission": share.get("permission", "read"),
        "accepted_at": datetime.utcnow()
    }
    
    shared_with_me_collection.update_one(
        {
            "user_id": user_id,
            "content_type": content_type,
            "source_id": share["source_id"]
        },
        {"$set": shared_entry},
        upsert=True
    )
    
    # Sync to centralized authorization system
    try:
        from services.authorization_service import get_authorization_service
        
        auth_service = get_authorization_service()
        
        # Map content_type to resource_type
        type_mapping = {
            "presentation": "presentation",
            "report": "report",
            "diagram": "diagram",
            "chat": "chat",
            "printable": "printable",
            "document": "document"
        }
        resource_type = type_mapping.get(content_type, content_type)
        
        # Register the resource first (in case it's not registered)
        await auth_service.register_resource(
            resource_id=share["source_id"],
            resource_type=resource_type,
            owner_id=share["user_id"],
            team_id=share.get("team_id")
        )
        
        # Grant access to the accepting user
        await auth_service.grant_access(
            owner_id=share["user_id"],
            resource_id=share["source_id"],
            resource_type=resource_type,
            target_user_id=user_id,
            permission=share.get("permission", "read"),
            team_id=share.get("team_id")
        )
        logging.getLogger(__name__).info(f"✅ Synced share accept to centralized auth: {resource_type}:{share['source_id']} -> {user_id}")
    except Exception as sync_e:
        logging.getLogger(__name__).warning(f"⚠️ Could not sync to centralized auth: {sync_e}")
    
    return {"success": True, "source_id": share["source_id"], "permission": share.get("permission", "read")}


@router.get("/shared-with-me")
async def list_shared_with_me(
    request: Request, 
    content_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """List items shared with the current user with pagination"""
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Validate pagination
    skip = max(0, skip)
    limit = min(100, max(1, limit))  # Cap at 100 items
    
    query = {"user_id": user_id}
    if content_type:
        query["content_type"] = content_type
    
    # Use aggregation to join with public_shares in a single query (fix N+1)
    pipeline = [
        {"$match": query},
        {"$sort": {"accepted_at": -1}},
        {"$skip": skip},
        {"$limit": limit},
        # Lookup to join with public_shares collection
        {
            "$lookup": {
                "from": "public_shares",
                "localField": "share_token",
                "foreignField": "share_token",
                "as": "share_info"
            }
        },
        # Filter out items where the share no longer exists
        {"$match": {"share_info": {"$ne": []}}},
        # Project final shape
        {
            "$project": {
                "_id": 0,
                "source_id": 1,
                "content_type": 1,
                "title": 1,
                "owner_id": 1,
                "accepted_at": 1,
                "permission": {"$arrayElemAt": ["$share_info.permission", 0]}
            }
        }
    ]
    
    items = list(shared_with_me_collection.aggregate(pipeline))
    
    # Get total count for pagination info
    total_count = shared_with_me_collection.count_documents(query)
    
    # Format dates
    for item in items:
        if "accepted_at" in item and item["accepted_at"]:
            item["accepted_at"] = item["accepted_at"].isoformat()
        if not item.get("permission"):
            item["permission"] = "read"
    
    return {
        "shared_items": items,
        "pagination": {
            "skip": skip,
            "limit": limit,
            "total": total_count,
            "has_more": skip + limit < total_count
        }
    }

