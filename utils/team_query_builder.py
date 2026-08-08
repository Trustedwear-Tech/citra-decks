"""
Team Query Builder - Helper utilities for building team-aware MongoDB queries

This module provides utilities to modify existing queries to support team/workspace
filtering. It can be used by all content APIs (documents, presentations, reports, etc.)
to enable team-based access control.

Usage:
    from team_query_builder import build_team_query, TeamQueryContext
    
    # In your API endpoint:
    query_context = TeamQueryContext(request)
    base_query = {"status": "active"}
    query = build_team_query(base_query, query_context)
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from fastapi import Request
import logging

logger = logging.getLogger(__name__)


class TeamQueryContext:
    """
    Extract team context from a FastAPI request.
    
    Team context can come from:
    - X-Team-ID header
    - team_id query parameter
    - Default to personal workspace (team_id = None)
    """
    
    def __init__(self, request: Request):
        self.team_id: Optional[str] = None
        self.user_id: Optional[str] = None
        self.user_email: Optional[str] = None
        self.is_personal: bool = True
        
        # Extract from request state (set by auth_middleware)
        if hasattr(request, 'state'):
            self.team_id = getattr(request.state, 'team_id', None)
            self.user_id = getattr(request.state, 'user_id', None)
            self.user_email = getattr(request.state, 'user_email', None)
            self.is_personal = getattr(request.state, 'is_personal_workspace', True)
            
        logger.debug(f"[TeamQueryContext] team_id={self.team_id}, user_id={self.user_id}, is_personal={self.is_personal}")


def build_team_query(
    base_query: Dict[str, Any],
    context: TeamQueryContext,
    user_field: str = "user_id",
    team_field: str = "team_id"
) -> Dict[str, Any]:
    """
    Build a MongoDB query that filters by team or personal workspace.
    
    For personal workspace (team_id=None):
        - Returns documents owned by the user with no team_id
        
    For team workspace (team_id set):
        - Returns documents belonging to the team
        - User must be a team member (validated at API level)
    
    Args:
        base_query: Original query dict (e.g., {"status": "active"})
        context: TeamQueryContext with user and team info
        user_field: Field name for user ID in documents
        team_field: Field name for team ID in documents
        
    Returns:
        Modified query with team/user filtering
    """
    query = dict(base_query)  # Copy to avoid mutation
    
    if context.is_personal or not context.team_id:
        # Personal workspace: user's own documents without team
        query[user_field] = context.user_id
        query["$or"] = [
            {team_field: {"$exists": False}},
            {team_field: None}
        ]
    else:
        # Team workspace: documents belonging to the team
        query[team_field] = context.team_id
        
    return query


def build_team_filter(
    context: TeamQueryContext,
    user_field: str = "user_id",
    team_field: str = "team_id"
) -> Dict[str, Any]:
    """
    Build just the team/user filter portion of a query.
    
    Useful when you need to append to an existing complex query.
    """
    if context.is_personal or not context.team_id:
        return {
            user_field: context.user_id,
            "$or": [
                {team_field: {"$exists": False}},
                {team_field: None}
            ]
        }
    else:
        return {team_field: context.team_id}


def add_team_to_document(
    document: Dict[str, Any],
    context: TeamQueryContext,
    team_field: str = "team_id"
) -> Dict[str, Any]:
    """
    Add team_id to a document being created.
    
    For personal workspace: team_id is set to None
    For team workspace: team_id is set to the active team
    """
    doc = dict(document)
    
    if context.is_personal or not context.team_id:
        doc[team_field] = None
    else:
        doc[team_field] = context.team_id
        
    return doc


def get_content_visibility_query(
    context: TeamQueryContext,
    include_shared: bool = True,
    user_field: str = "user_id",
    team_field: str = "team_id"
) -> Dict[str, Any]:
    """
    Build a query that includes both owned and shared content.
    
    This is useful for listing endpoints where users should see:
    - Their own content
    - Content shared with them
    - Team content (if in a team workspace)
    
    Args:
        context: TeamQueryContext
        include_shared: Whether to include content shared with the user
        user_field: Field name for user ID
        team_field: Field name for team ID
        
    Returns:
        MongoDB query with $or conditions for visibility
    """
    conditions = []
    
    if context.is_personal or not context.team_id:
        # Personal workspace
        # 1. User's own content
        conditions.append({
            user_field: context.user_id,
            "$or": [
                {team_field: {"$exists": False}},
                {team_field: None}
            ]
        })
        
        # 2. Content shared with user (if enabled)
        if include_shared:
            conditions.append({
                "shared_with": {"$elemMatch": {"email": context.user_email}}
            })
    else:
        # Team workspace
        # All team content
        conditions.append({
            team_field: context.team_id
        })
        
    if len(conditions) == 1:
        return conditions[0]
    else:
        return {"$or": conditions}


def can_modify_content(
    document: Dict[str, Any],
    context: TeamQueryContext,
    user_field: str = "user_id",
    team_field: str = "team_id"
) -> bool:
    """
    Check if the current user can modify a document.
    
    Personal workspace: User must be the owner
    Team workspace: User must be a team member (additional role check may be needed)
    
    Note: This is a basic check. For full authorization, use the team_auth_middleware.
    """
    doc_team_id = document.get(team_field)
    doc_user_id = document.get(user_field)
    
    if doc_team_id:
        # Team content - must be in same team
        return context.team_id == doc_team_id
    else:
        # Personal content - must be owner
        return context.user_id == doc_user_id


# ==================== Migration Helpers ====================

async def migrate_content_to_team(
    db,
    collection_name: str,
    document_id: str,
    target_team_id: str,
    user_id: str
) -> bool:
    """
    Migrate a personal document to a team workspace.
    
    This is used when users want to share their personal content with a team.
    Creates a copy or moves the original (based on your requirements).
    
    Args:
        db: MongoDB database instance
        collection_name: Collection containing the document
        document_id: ID of the document to migrate
        target_team_id: Team to migrate to
        user_id: User performing the migration (must be owner)
        
    Returns:
        True if migration successful
    """
    collection = db[collection_name]
    
    try:
        # Verify ownership
        doc = await collection.find_one({"_id": document_id, "user_id": user_id})
        if not doc:
            logger.warning(f"[TeamMigration] Document {document_id} not found or not owned by user")
            return False
            
        # Update with team_id
        result = await collection.update_one(
            {"_id": document_id},
            {
                "$set": {
                    "team_id": target_team_id,
                    "migrated_to_team_at": datetime.utcnow()
                }
            }
        )
        
        return result.modified_count > 0
        
    except Exception as e:
        logger.error(f"[TeamMigration] Error migrating document: {e}")
        return False
