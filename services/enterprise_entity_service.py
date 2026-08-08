"""
Enterprise Entity Service
=======================

Simple service for managing enterprise entities loaded from ETL jobs.
Provides search functionality by name or ID.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel, TEXT
from bson import ObjectId

from models.enterprise_entity import (
    EnterpriseEntity, 
    EnterpriseEntitySearchRequest, 
    EnterpriseEntitySearchResponse
)
from models.unified_metadata_schema import UnifiedMetadataSchema

logger = logging.getLogger(__name__)


class EnterpriseEntityService:
    """Service for managing enterprise entities"""
    
    def __init__(self, mongo_client: AsyncIOMotorClient, database_name: str):
        self.client = mongo_client
        self.db: AsyncIOMotorDatabase = mongo_client[database_name]
        self.collection = self.db.enterprise_entities
        self._indexes_created = False
    
    async def ensure_indexes(self):
        """Create necessary indexes for enterprise entities"""
        if self._indexes_created:
            return
        
        try:
            # Create indexes for efficient queries
            indexes = [
                IndexModel([("entity_id", 1), ("user_id", 1)], unique=True),  # Unique per user
                IndexModel([("entity_name", TEXT)]),  # Text search on name
                IndexModel([("entity_type", 1)]),
                IndexModel([("user_id", 1)]),
                IndexModel([("updated_at", -1)])
            ]
            
            await self.collection.create_indexes(indexes)
            logger.info("Enterprise entity indexes created successfully")
            self._indexes_created = True
            
        except Exception as e:
            logger.error(f"Failed to create enterprise entity indexes: {e}")
            raise
    
    async def create_entity(self, entity: EnterpriseEntity) -> str:
        """Create a new enterprise entity"""
        await self.ensure_indexes()
        
        try:
            # Validate required fields
            if not entity.user_id:
                raise ValueError("user_id is required for enterprise entity creation")
            
            # Convert Pydantic model to dict for MongoDB
            entity_dict = entity.dict(by_alias=True, exclude_unset=True)
            
            # Remove None _id if present
            if "_id" in entity_dict and entity_dict["_id"] is None:
                del entity_dict["_id"]
            
            # Ensure timestamps
            now = datetime.utcnow()
            entity_dict["created_at"] = now
            entity_dict["updated_at"] = now
            
            result = await self.collection.insert_one(entity_dict)
            entity_id = str(result.inserted_id)
            
            logger.info(
                f"Created enterprise entity: {entity.entity_name} "
                f"({entity.entity_id}) for user {entity.user_id}"
            )
            
            return entity_id
            
        except Exception as e:
            logger.error(f"Failed to create enterprise entity {entity.entity_id}: {e}")
            raise
    
    async def bulk_create_entities(self, entities: List[EnterpriseEntity]) -> Dict[str, Any]:
        """Bulk create multiple enterprise entities (for ETL jobs)"""
        await self.ensure_indexes()
        
        try:
            if not entities:
                return {"inserted": [], "duplicates": []}
            
            # Validate all entities have user_id
            for entity in entities:
                if not entity.user_id:
                    raise ValueError("user_id is required for all enterprise entities")
            
            # Check for existing entities to avoid duplicates
            entity_ids = [entity.entity_id for entity in entities]
            user_id = entities[0].user_id  # All entities should have the same user_id
            
            existing_entities = await self.collection.find({
                "entity_id": {"$in": entity_ids},
                "user_id": user_id
            }).to_list(length=None)
            
            existing_ids = {entity["entity_id"] for entity in existing_entities}
            
            # Filter out duplicates
            new_entities = [entity for entity in entities if entity.entity_id not in existing_ids]
            
            if not new_entities:
                # All entities are duplicates
                return {
                    "inserted": [],
                    "duplicates": entity_ids
                }
            
            # Convert to dicts for insertion
            now = datetime.utcnow()
            entity_dicts = []
            
            for entity in new_entities:
                entity_dict = entity.dict(by_alias=True, exclude_unset=True)
                if "_id" in entity_dict and entity_dict["_id"] is None:
                    del entity_dict["_id"]
                entity_dict["created_at"] = now
                entity_dict["updated_at"] = now
                entity_dicts.append(entity_dict)
            
            result = await self.collection.insert_many(entity_dicts, ordered=False)
            inserted_ids = [str(id) for id in result.inserted_ids]
            
            logger.info(f"Bulk created {len(inserted_ids)} enterprise entities, {len(existing_ids)} duplicates skipped")
            
            return {
                "inserted": inserted_ids,
                "duplicates": list(existing_ids)
            }
            
        except Exception as e:
            logger.error(f"Bulk enterprise entity creation failed: {e}")
            raise
    
    async def search_entities(
        self, 
        request: EnterpriseEntitySearchRequest,
        user_id: str
    ) -> EnterpriseEntitySearchResponse:
        """Search enterprise entities by name, ID, or type"""
        await self.ensure_indexes()
        
        try:
            # Build search query
            query_filters = {
                "user_id": user_id
            }
            
            # Add entity type filter if specified
            if request.entity_type:
                query_filters["entity_type"] = request.entity_type
            
            # Search logic: search in entity_name, entity_id, and entity_type
            search_query = request.query.strip()
            if search_query:
                # Use $or to search in name, ID, and type fields
                # For name: case-insensitive partial match
                # For ID: starts with query (case-insensitive)
                # For type: case-insensitive partial match
                query_filters["$or"] = [
                    {"entity_name": {"$regex": search_query, "$options": "i"}},
                    {"entity_id": {"$regex": f"^{search_query}", "$options": "i"}},  # ID starts with query
                    {"entity_type": {"$regex": search_query, "$options": "i"}}  # Type partial match
                ]
            
            # Count total results
            total_count = await self.collection.count_documents(query_filters)
            
            # Execute search with pagination
            cursor = self.collection.find(query_filters).limit(request.limit)
            
            entities = []
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                entities.append(EnterpriseEntity(**doc))
            
            logger.info(
                f"Enterprise entity search completed: {len(entities)} results "
                f"(total: {total_count}) for query: '{search_query}'"
            )
            
            return EnterpriseEntitySearchResponse(
                entities=entities,
                total_count=total_count,
                query=search_query
            )
        
        except Exception as e:
            logger.error(f"Enterprise entity search failed: {e}")
            raise
    
    async def get_entity_by_id(
        self, 
        entity_id: str,
        user_id: str
    ) -> Optional[EnterpriseEntity]:
        """Get entity by entity_id and user_id"""
        await self.ensure_indexes()
        
        try:
            entity_doc = await self.collection.find_one({
                "entity_id": entity_id,
                "user_id": user_id
            })
            
            if entity_doc:
                entity_doc["_id"] = str(entity_doc["_id"])
                return EnterpriseEntity(**entity_doc)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get enterprise entity {entity_id}: {e}")
            raise
    
    async def get_entities_by_type(
        self, 
        entity_type: str,
        user_id: str,
        limit: int = 100
    ) -> List[EnterpriseEntity]:
        """Get entities by type"""
        await self.ensure_indexes()
        
        try:
            cursor = self.collection.find({
                "entity_type": entity_type,
                "user_id": user_id
            }).limit(limit)
            
            entities = []
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                entities.append(EnterpriseEntity(**doc))
            
            return entities
            
        except Exception as e:
            logger.error(f"Failed to get entities by type {entity_type}: {e}")
            raise
    
    async def update_entity(
        self, 
        entity_id: str,
        entity: EnterpriseEntity,
        user_id: str
    ) -> Optional[EnterpriseEntity]:
        """Update an existing enterprise entity"""
        await self.ensure_indexes()
        
        try:
            # Validate required fields
            if not entity.user_id:
                raise ValueError("user_id is required for enterprise entity update")
            
            # Ensure user_id matches
            if entity.user_id != user_id:
                raise ValueError("user_id mismatch")
            
            # Convert Pydantic model to dict for MongoDB
            entity_dict = entity.dict(by_alias=True, exclude_unset=True)
            
            # Remove _id if present (we don't want to update the ID)
            if "_id" in entity_dict:
                del entity_dict["_id"]
            
            # Update timestamp
            entity_dict["updated_at"] = datetime.utcnow()
            
            # Update the entity
            result = await self.collection.update_one(
                {"entity_id": entity_id, "user_id": user_id},
                {"$set": entity_dict}
            )
            
            if result.matched_count == 0:
                return None  # Entity not found
            
            # Fetch and return the updated entity
            updated_entity_doc = await self.collection.find_one({
                "entity_id": entity_id,
                "user_id": user_id
            })
            
            if updated_entity_doc:
                updated_entity_doc["_id"] = str(updated_entity_doc["_id"])
                return EnterpriseEntity(**updated_entity_doc)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to update enterprise entity {entity_id}: {e}")
            raise
    
    async def get_entity_stats(self, user_id: str) -> Dict[str, Any]:
        """Get entity statistics for user"""
        await self.ensure_indexes()
        
        try:
            pipeline = [
                {"$match": {"user_id": user_id}},
                {
                    "$group": {
                        "_id": "$entity_type",
                        "count": {"$sum": 1}
                    }
                }
            ]
            
            stats = {"total": 0, "by_type": {}}
            
            async for doc in self.collection.aggregate(pipeline):
                entity_type = doc["_id"]
                count = doc["count"]
                
                stats["by_type"][entity_type] = count
                stats["total"] += count
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get entity stats: {e}")
            raise
    
    async def delete_entity(
        self, 
        entity_id: str,
        user_id: str
    ) -> bool:
        """Delete entity and all related data (S3, Milvus, MongoDB)"""
        await self.ensure_indexes()
        
        try:
            # Step 1: Get all related documents and transcripts before deletion
            related_docs = await self.collection.database.document_chunked.find({
                "user_id": user_id,
                "entity_id": entity_id,
                "is_enterprise": True
            }).to_list(length=None)
            
            related_transcripts = await self.collection.database.transcripts.find({
                "user_id": user_id,
                "entity_id": entity_id,
                "is_enterprise": True
            }).to_list(length=None)
            
            # Step 2: Delete files from S3
            await self._delete_s3_files(related_docs, related_transcripts, user_id)
            
            # Step 3: Delete vectors from Milvus
            await self._delete_milvus_vectors(related_docs, related_transcripts)
            
            # Step 4: Delete related documents and transcripts from MongoDB
            await self._delete_mongodb_related_data(entity_id, user_id)
            
            # Step 5: Delete the entity itself
            result = await self.collection.delete_one({
                "entity_id": entity_id,
                "user_id": user_id
            })
            
            success = result.deleted_count > 0
            
            if success:
                logger.info(f"Deleted enterprise entity {entity_id} and all related data")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete enterprise entity {entity_id}: {e}")
            raise
    
    async def _delete_s3_files(self, docs: list, transcripts: list, user_id: str):
        """Delete related files from S3 using files_service"""
        try:
            from services.files_service import FilesService
            from bucket import delete_file
            
            files_service = FilesService(self.collection.database.client, self.collection.database.name)
            
            # Collect all document/transcript IDs to delete
            file_ids_to_delete = set()
            
            # From documents
            for doc in docs:
                if "document_id" in doc:
                    file_ids_to_delete.add(doc["document_id"])
                elif "_id" in doc:
                    file_ids_to_delete.add(str(doc["_id"]))
            
            # From transcripts
            for transcript in transcripts:
                if "_id" in transcript:
                    file_ids_to_delete.add(str(transcript["_id"]))
            
            # Delete files from S3 using files_service (single source of truth)
            deleted_count = 0
            for file_id in file_ids_to_delete:
                try:
                    # Get S3 URL from files collection
                    file_resources = await files_service.get_file_resources(file_id, user_id)
                    
                    if file_resources and file_resources.get("s3_url"):
                        s3_url = file_resources["s3_url"]
                        
                        # Extract S3 key from URL
                        if ".amazonaws.com/" in s3_url:
                            s3_key = s3_url.split(".amazonaws.com/")[-1]
                        elif "s3://" in s3_url:
                            s3_key = s3_url.split("s3://", 1)[-1].split("/", 1)[-1]
                        else:
                            s3_key = s3_url  # Fallback
                        
                        # Delete from S3
                        if delete_file(s3_key):
                            deleted_count += 1
                            logger.info(f"✅ Deleted S3 file: {s3_key}")
                        else:
                            logger.warning(f"⚠️ S3 delete failed for {s3_key}")
                        
                        # Delete from files registry
                        await files_service.delete_file(file_id, user_id)
                    else:
                        logger.warning(f"⚠️ No S3 URL found for file {file_id}")
                        
                except Exception as e:
                    # Log but don't fail - S3 might be unavailable
                    logger.warning(f"S3 delete failed for {file_id} (continuing): {e}")
            
            logger.info(f"✅ Deleted {deleted_count} files from S3 for enterprise entity")
                    
        except Exception as e:
            # Log S3 connection errors but don't fail entity deletion
            logger.warning(f"S3 Storage connection failed during entity cleanup (continuing): {e}")
                    
        except Exception as e:
            # Log S3 connection errors but don't fail entity deletion
            logger.warning(f"S3 Storage connection failed during entity cleanup (continuing): {e}")
    
    async def _delete_milvus_vectors(self, docs: list, transcripts: list):
        """Delete related vectors from Milvus"""
        try:
            from config.milvus_config import get_collection_name, get_milvus_client
            
            collection_name = get_collection_name()
            
            # Use singleton Milvus client
            client = get_milvus_client()
            
            total_deleted = 0
            
            # Delete vectors for each document using filter expressions
            for doc in docs:
                if doc.get("has_vectors", False) and "document_id" in doc:
                    doc_id = doc["document_id"]
                    user_id = doc.get("user_id")
                    
                    try:
                        # Create filter expression for this document
                        filter_expr = f'document_id == "{doc_id}"'
                        if user_id:
                            filter_expr += f' and user_id == "{user_id}" and is_enterprise == true'
                        
                        # Delete vectors matching the filter
                        result = client.delete(
                            collection_name=collection_name,
                            filter=filter_expr
                        )
                        
                        deleted_count = result.get("delete_count", 0)
                        total_deleted += deleted_count
                        logger.info(f"Deleted {deleted_count} vectors for document {doc_id}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to delete vectors for document {doc_id}: {e}")
            
            # Delete vectors for each transcript using filter expressions
            for transcript in transcripts:
                if "transcript_id" in transcript:
                    transcript_id = transcript["transcript_id"]
                    user_id = transcript.get("user_id")
                    
                    try:
                        # Create filter expression for this transcript (use document_id not transcript_id)
                        filter_expr = f'document_id == "{transcript_id}"'
                        if user_id:
                            filter_expr += f' and user_id == "{user_id}" and is_enterprise == true'
                        
                        # Delete vectors matching the filter
                        result = client.delete(
                            collection_name=collection_name,
                            filter=filter_expr
                        )
                        
                        deleted_count = result.get("delete_count", 0)
                        total_deleted += deleted_count
                        logger.info(f"Deleted {deleted_count} vectors for transcript {transcript_id}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to delete vectors for transcript {transcript_id}: {e}")
            
            logger.info(f"Total vectors deleted from Milvus: {total_deleted}")
                        
        except Exception as e:
            logger.error(f"Error deleting Milvus vectors: {e}")
    
    async def _delete_mongodb_related_data(self, entity_id: str, user_id: str):
        """Delete related documents and transcripts from MongoDB"""
        try:
            # Delete document chunks
            doc_result = await self.collection.database.document_chunked.delete_many({
                "user_id": user_id,
                "entity_id": entity_id,
                "is_enterprise": True
            })
            logger.info(f"Deleted {doc_result.deleted_count} document chunks")
            
            # Delete audio transcripts
            transcript_result = await self.collection.database.transcripts.delete_many({
                "user_id": user_id,
                "entity_id": entity_id,
                "is_enterprise": True
            })
            logger.info(f"Deleted {transcript_result.deleted_count} audio transcripts")
            
            # Delete video transcripts
            video_result = await self.collection.database.video_transcripts.delete_many({
                "user_id": user_id,
                "entity_id": entity_id,
                "is_enterprise": True
            })
            logger.info(f"Deleted {video_result.deleted_count} video transcripts")
            
            # Delete milvus_chunks entries
            milvus_chunks_result = await self.collection.database.milvus_chunks.delete_many({
                "user_id": user_id,
                "entity_id": entity_id,
                "is_enterprise": True
            })
            logger.info(f"Deleted {milvus_chunks_result.deleted_count} milvus_chunks entries")
            
        except Exception as e:
            logger.error(f"Error deleting MongoDB related data: {e}")
            raise