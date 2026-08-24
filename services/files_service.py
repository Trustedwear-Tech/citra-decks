# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

# ============================  Files Service  =============================
# Purpose: Centralized file metadata service for all file types
# Features: Single source of truth for file metadata and resource tracking
# ----------------------------------------------------------------------------------------

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)


class FilesService:
    """
    Centralized file registry service for all file types.
    Single source of truth for file metadata and resources.
    
    Tracks:
    - Documents (PDF, DOCX, etc.)
    - Audio files (MP3, WAV, etc.)
    - Video files (MP4, WEBM, etc.)
    - Images (JPG, PNG, etc.)
    - Notes
    
    Enables:
    - Fast file lookups
    - Unified search across all file types
    - Quick deletion (all resource IDs in one query)
    - Storage analytics
    """
    
    def __init__(self, mongo_client: AsyncIOMotorClient, database_name: str):
        self.logger = logging.getLogger(__name__)
        self.client = mongo_client
        self.db = self.client[database_name]
        self.collection = self.db["files"]
        self.logger.info(f"🗂️ FilesService initialized for database: {database_name}")
    
    async def create_indexes(self):
        """Create optimized indexes for fast lookups"""
        try:
            # Primary lookups
            await self.collection.create_index("_id", unique=True)
            await self.collection.create_index("user_id")
            await self.collection.create_index([("user_id", 1), ("filename", 1)])
            
            # Filtering
            await self.collection.create_index("file_type_category")
            await self.collection.create_index([("user_id", 1), ("file_type_category", 1)])
            await self.collection.create_index([("user_id", 1), ("folder_id", 1)])
            
            # Timestamp sorting
            await self.collection.create_index([("user_id", 1), ("created_at", -1)])
            
            # Enterprise filtering
            await self.collection.create_index([("entity_id", 1), ("is_enterprise", 1)])
            
            self.logger.info("✅ File registry indexes created successfully")
        except Exception as e:
            self.logger.warning(f"⚠️ Index creation warning (may already exist): {e}")
    
    async def register_file(self, file_metadata: dict) -> str:
        """
        Register a new file in the registry.
        
        Args:
            file_metadata: Complete file metadata dictionary
            
        Returns:
            File ID of registered file
        """
        try:
            # Ensure created_at and updated_at
            if "created_at" not in file_metadata:
                file_metadata["created_at"] = datetime.utcnow().isoformat()
            if "updated_at" not in file_metadata:
                file_metadata["updated_at"] = datetime.utcnow().isoformat()
            
            # Insert into registry
            result = await self.collection.insert_one(file_metadata)
            
            file_id = file_metadata.get("_id", str(result.inserted_id))
            self.logger.info(f"✅ File registered: {file_id} ({file_metadata.get('filename')})")
            
            return file_id
            
        except Exception as e:
            self.logger.error(f"❌ Failed to register file: {e}")
            raise
    
    async def update_file(self, file_id: str, updates: dict) -> bool:
        """
        Update file registry entry.
        
        Args:
            file_id: File identifier
            updates: Fields to update
            
        Returns:
            True if updated, False otherwise
        """
        try:
            # Add updated_at timestamp
            updates["updated_at"] = datetime.utcnow().isoformat()
            
            result = await self.collection.update_one(
                {"_id": file_id},
                {"$set": updates}
            )
            
            if result.modified_count > 0:
                self.logger.info(f"✅ File updated: {file_id}")
                return True
            else:
                self.logger.warning(f"⚠️ File not found or no changes: {file_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Failed to update file {file_id}: {e}")
            raise
    
    async def get_file(self, file_id: str, user_id: str = None) -> Optional[dict]:
        """
        Get complete file metadata.
        
        Args:
            file_id: File identifier
            user_id: Optional user_id filter for security
            
        Returns:
            File metadata dictionary or None
        """
        try:
            query = {"_id": file_id}
            if user_id:
                query["user_id"] = user_id
            
            file_metadata = await self.collection.find_one(query)
            return file_metadata
            
        except Exception as e:
            self.logger.error(f"❌ Failed to get file {file_id}: {e}")
            return None
    
    async def list_user_files(
        self,
        filters: dict,
        limit: int = 50,
        offset: int = 0
    ) -> List[dict]:
        """
        List user files with filters.
        Filters already include user_id for security.
        
        Args:
            filters: Query filters (must include user_id)
            limit: Maximum results to return
            offset: Pagination offset
            
        Returns:
            List of file metadata dictionaries
        """
        try:
            cursor = self.collection.find(filters).sort("created_at", -1).skip(offset).limit(limit)
            files = await cursor.to_list(length=limit)
            
            # Convert ObjectId to string for JSON serialization if needed
            for file in files:
                if "_id" in file and hasattr(file["_id"], "__str__"):
                    file["_id"] = str(file["_id"])
            
            return files
            
        except Exception as e:
            self.logger.error(f"❌ Failed to list files: {e}")
            return []
    
    async def count_files(self, filters: dict) -> int:
        """
        Count total files matching filters.
        
        Args:
            filters: Query filters
            
        Returns:
            Total count of matching files
        """
        try:
            return await self.collection.count_documents(filters)
        except Exception as e:
            self.logger.error(f"❌ Failed to count files: {e}")
            return 0
    
    async def get_file_resources(self, file_id: str, user_id: str) -> Optional[dict]:
        """
        Get all resource IDs for file deletion.
        Returns: Milvus primary_keys, S3 URL, MongoDB collection IDs
        
        SECURITY: Always verify user_id matches to prevent unauthorized deletion
        
        Args:
            file_id: File identifier
            user_id: Authenticated user_id from JWT token
            
        Returns:
            Dictionary with all resource IDs or None if not found
        """
        try:
            file_metadata = await self.collection.find_one({
                "_id": file_id,
                "user_id": user_id  # CRITICAL: Security check
            })
            
            if not file_metadata:
                self.logger.warning(f"⚠️ File not found or unauthorized: {file_id}")
                return None
            
            return {
                "milvus_primary_keys": file_metadata.get("milvus_primary_keys", []),
                "s3_url": file_metadata.get("s3_url"),
                "storage_location": file_metadata.get("storage_location", "s3"),
                "mongodb_refs": file_metadata.get("mongodb_collections", {}),
                "file_type": file_metadata.get("file_type_category"),
                "filename": file_metadata.get("filename")
            }
            
        except Exception as e:
            self.logger.error(f"❌ Failed to get file resources {file_id}: {e}")
            return None
    
    async def delete_file(self, file_id: str, user_id: str) -> bool:
        """
        Delete file from registry.
        
        SECURITY: Always verify user_id matches
        
        Args:
            file_id: File identifier
            user_id: Authenticated user_id from JWT token
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            result = await self.collection.delete_one({
                "_id": file_id,
                "user_id": user_id  # CRITICAL: Security check
            })
            
            if result.deleted_count > 0:
                self.logger.info(f"✅ File deleted from registry: {file_id}")
                return True
            else:
                self.logger.warning(f"⚠️ File not found or unauthorized: {file_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Failed to delete file {file_id}: {e}")
            return False
    
    async def get_storage_stats(self, user_id: str, entity_id: str = None) -> dict:
        """
        Get storage statistics for user or entity.
        
        Args:
            user_id: User identifier
            entity_id: Optional enterprise entity ID
            
        Returns:
            Storage statistics dictionary
        """
        try:
            match_filter = {"user_id": user_id}
            if entity_id:
                match_filter["entity_id"] = entity_id
                match_filter["is_enterprise"] = True
            
            pipeline = [
                {"$match": match_filter},
                {"$group": {
                    "_id": "$file_type_category",
                    "total_files": {"$sum": 1},
                    "total_bytes": {"$sum": "$file_size_bytes"}
                }}
            ]
            
            results = await self.collection.aggregate(pipeline).to_list(length=None)
            
            # Format results
            stats = {
                "user_id": user_id,
                "entity_id": entity_id,
                "by_type": {},
                "total_files": 0,
                "total_bytes": 0
            }
            
            for item in results:
                file_type = item["_id"] or "unknown"
                stats["by_type"][file_type] = {
                    "count": item["total_files"],
                    "bytes": item["total_bytes"],
                    "size_mb": round(item["total_bytes"] / (1024 * 1024), 2)
                }
                stats["total_files"] += item["total_files"]
                stats["total_bytes"] += item["total_bytes"]
            
            stats["total_size_mb"] = round(stats["total_bytes"] / (1024 * 1024), 2)
            stats["total_size_gb"] = round(stats["total_bytes"] / (1024 * 1024 * 1024), 2)
            
            return stats
            
        except Exception as e:
            self.logger.error(f"❌ Failed to get storage stats: {e}")
            return {
                "user_id": user_id,
                "entity_id": entity_id,
                "error": str(e)
            }
