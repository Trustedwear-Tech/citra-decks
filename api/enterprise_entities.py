"""
Enterprise Entity API
===================

API endpoints for enterprise entity search functionality.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import Optional
import logging

from models.enterprise_entity import (
    EnterpriseEntity,
    EnterpriseEntitySearchRequest,
    EnterpriseEntitySearchResponse
)
from services.enterprise_entity_service import EnterpriseEntityService
from citra_mongo import MongoDBManager
from citra_auth import get_secure_user_id

# Create router
router = APIRouter(prefix="/v2/enterprise-entities", tags=["Enterprise Entities"])
logger = logging.getLogger(__name__)

# Dependency to get enterprise entity service
def get_enterprise_entity_service() -> EnterpriseEntityService:
    """Get enterprise entity service instance"""
    mongo_manager = MongoDBManager()
    return EnterpriseEntityService(
        mongo_client=mongo_manager.get_async_client(),
        database_name=mongo_manager.database_name
    )


@router.get("/search", response_model=EnterpriseEntitySearchResponse)
async def search_enterprise_entities(
    request: Request,
    query: str = Query(..., description="Search query for entity name, ID, or type"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results to return"),
    service: EnterpriseEntityService = Depends(get_enterprise_entity_service)
):
    """
    Search enterprise entities by name, ID, or type.
    
    - **query**: Search term to match against entity names, IDs, or types
    - **entity_type**: Optional filter by entity type (patient, case, criminal, etc.)
    - **limit**: Maximum number of results (1-100, default 20)
    
    Returns matching entities with user_id, entity_name, entity_id, and entity_type.
    """
    try:
        # Get authenticated user_id
        user_id = get_secure_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        logger.info(f"🔍 Searching enterprise entities - Query: '{query}', Type: {entity_type}, Limit: {limit}, User: {user_id}")
        
        search_request = EnterpriseEntitySearchRequest(
            query=query,
            entity_type=entity_type,
            limit=limit
        )
        
        result = await service.search_entities(search_request, user_id)
        
        logger.info(f"✅ Found {len(result.entities)} entities (total: {result.total_count})")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Enterprise entity search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/entity/{entity_id}", response_model=EnterpriseEntity)
async def get_enterprise_entity(
    request: Request,
    entity_id: str,
    service: EnterpriseEntityService = Depends(get_enterprise_entity_service)
):
    """
    Get a specific enterprise entity by ID.
    
    - **entity_id**: Unique entity identifier within the user's scope
    """
    try:
        # Get authenticated user_id
        user_id = get_secure_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        logger.info(f"🔍 Getting enterprise entity: {entity_id} for user: {user_id}")
        
        entity = await service.get_entity_by_id(entity_id, user_id)
        
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
        
        logger.info(f"✅ Found entity: {entity.entity_name}")
        return entity
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get enterprise entity {entity_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get entity: {str(e)}")


@router.get("/types/{entity_type}", response_model=list[EnterpriseEntity])
async def get_entities_by_type(
    request: Request,
    entity_type: str,
    limit: int = Query(100, ge=1, le=1000, description="Maximum results to return"),
    service: EnterpriseEntityService = Depends(get_enterprise_entity_service)
):
    """
    Get all entities of a specific type.
    
    - **entity_type**: Type of entities to retrieve (patient, case, criminal, etc.)
    - **limit**: Maximum number of results (1-1000, default 100)
    """
    try:
        # Get authenticated user_id
        user_id = get_secure_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        logger.info(f"🔍 Getting entities by type: {entity_type} for user: {user_id}")
        
        entities = await service.get_entities_by_type(entity_type, user_id, limit)
        
        logger.info(f"✅ Found {len(entities)} entities of type {entity_type}")
        return entities
        
    except Exception as e:
        logger.error(f"❌ Failed to get entities by type {entity_type}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get entities: {str(e)}")


@router.get("/stats", response_model=dict)
async def get_entity_stats(
    request: Request,
    service: EnterpriseEntityService = Depends(get_enterprise_entity_service)
):
    """
    Get statistics about entities for the authenticated user.
    
    Returns counts by entity type and total count.
    """
    try:
        # Get authenticated user_id
        user_id = get_secure_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        logger.info(f"📊 Getting entity stats for user: {user_id}")
        
        stats = await service.get_entity_stats(user_id)
        
        logger.info(f"✅ Retrieved stats: {stats['total']} total entities")
        return stats
        
    except Exception as e:
        logger.error(f"❌ Failed to get entity stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.post("/", response_model=str)
async def create_enterprise_entity(
    request: Request,
    entity: EnterpriseEntity,
    service: EnterpriseEntityService = Depends(get_enterprise_entity_service)
):
    """
    Create a new enterprise entity.
    
    The entity will be associated with the authenticated user.
    """
    try:
        # Get authenticated user_id
        user_id = get_secure_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Ensure the entity has the correct user_id
        entity.user_id = user_id
        
        logger.info(f"➕ Creating enterprise entity: {entity.entity_name} ({entity.entity_id}) for user: {user_id}")
        
        entity_id = await service.create_entity(entity)
        
        logger.info(f"✅ Created entity with ID: {entity_id}")
        return entity_id
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to create enterprise entity: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create entity: {str(e)}")


@router.post("/bulk", response_model=dict)
async def bulk_create_enterprise_entities(
    request: Request,
    entities: list[EnterpriseEntity],
    service: EnterpriseEntityService = Depends(get_enterprise_entity_service)
):
    """
    Bulk create multiple enterprise entities.
    
    All entities will be associated with the authenticated user.
    Returns a summary of inserted entities and duplicates found.
    """
    try:
        # Get authenticated user_id
        user_id = get_secure_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Ensure all entities have the correct user_id
        for entity in entities:
            entity.user_id = user_id
        
        logger.info(f"➕ Bulk creating {len(entities)} enterprise entities for user: {user_id}")
        
        result = await service.bulk_create_entities(entities)
        
        logger.info(f"✅ Bulk operation complete: {len(result['inserted'])} inserted, {len(result['duplicates'])} duplicates")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to bulk create enterprise entities: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create entities: {str(e)}")


@router.put("/entity/{entity_id}", response_model=EnterpriseEntity)
async def update_enterprise_entity(
    request: Request,
    entity_id: str,
    entity: EnterpriseEntity,
    service: EnterpriseEntityService = Depends(get_enterprise_entity_service)
):
    """
    Update an existing enterprise entity.
    
    - **entity_id**: Unique entity identifier within the user's scope
    - **entity**: Updated entity data (entity_id in URL must match entity.entity_id)
    """
    try:
        # Get authenticated user_id
        user_id = get_secure_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Validate that URL entity_id matches the entity data
        if entity.entity_id != entity_id:
            raise HTTPException(status_code=400, detail="Entity ID in URL must match entity data")
        
        # Ensure the entity has the correct user_id
        entity.user_id = user_id
        
        logger.info(f"✏️ Updating enterprise entity: {entity.entity_name} ({entity_id}) for user: {user_id}")
        
        updated_entity = await service.update_entity(entity_id, entity, user_id)
        
        if not updated_entity:
            raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
        
        logger.info(f"✅ Updated entity: {entity.entity_name}")
        return updated_entity
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to update enterprise entity {entity_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update entity: {str(e)}")


@router.delete("/entity/{entity_id}", response_model=dict)
async def delete_enterprise_entity(
    request: Request,
    entity_id: str,
    service: EnterpriseEntityService = Depends(get_enterprise_entity_service)
):
    """
    Delete an existing enterprise entity.
    
    - **entity_id**: Unique entity identifier within the user's scope
    """
    try:
        # Get authenticated user_id
        user_id = get_secure_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        logger.info(f"🗑️ Deleting enterprise entity: {entity_id} for user: {user_id}")
        
        deleted = await service.delete_entity(entity_id, user_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
        
        logger.info(f"✅ Deleted entity: {entity_id}")
        return {"message": f"Entity '{entity_id}' deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete enterprise entity {entity_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete entity: {str(e)}")