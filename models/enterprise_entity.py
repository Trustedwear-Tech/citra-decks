"""
Enterprise Entity Model
=====================

Simple model for managing enterprise entities with basic fields:
- user_id: user identifier (for user-scoped data isolation)
- entity_name: display name of the entity
- entity_id: unique identifier within the user's scope
- entity_type: type of entity (patient, case, criminal, etc.)
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from bson import ObjectId


class EnterpriseEntity(BaseModel):
    """Simple enterprise entity model for user-scoped data"""
    
    id: Optional[str] = Field(None, alias="_id")
    user_id: Optional[str] = Field(None, description="User identifier for data isolation")
    entity_name: str = Field(..., description="Display name of the entity")
    entity_id: str = Field(..., description="Unique identifier within user's scope")
    entity_type: str = Field(..., description="Type of entity (patient, case, criminal, etc.)")
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat() if v else None
        }


class EnterpriseEntitySearchRequest(BaseModel):
    """Search request for enterprise entities"""
    
    query: str = Field(..., description="Search query for name or ID")
    entity_type: Optional[str] = Field(None, description="Filter by entity type")
    limit: int = Field(default=20, ge=1, le=100, description="Maximum results to return")
    

class EnterpriseEntitySearchResponse(BaseModel):
    """Search response for enterprise entities"""
    
    entities: list[EnterpriseEntity] = Field(default=[], description="List of matching entities")
    total_count: int = Field(description="Total number of matching entities")
    query: str = Field(description="Original search query")