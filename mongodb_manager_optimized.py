# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

import asyncio
import time
import os
from typing import Dict, List, Optional, Any
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import MongoClient, UpdateOne, InsertOne, DeleteOne
from pymongo.errors import BulkWriteError
import logging
from functools import lru_cache
from collections import defaultdict

logger = logging.getLogger(__name__)

# Durability caps: these generic find/aggregate helpers must never pull an
# unbounded result set into memory (a forgotten `limit` could load a whole
# collection and stall a worker). A `maxTimeMS` also bounds a slow/locked query
# so it can't hang the event loop indefinitely.
_FIND_MAX_MS = int(os.getenv("MONGO_OPT_MAX_TIME_MS", "30000"))
_FIND_DEFAULT_CAP = int(os.getenv("MONGO_OPT_FIND_CAP", "10000"))
_AGG_DEFAULT_CAP = int(os.getenv("MONGO_OPT_AGG_CAP", "50000"))


class OptimizedMongoDBManager:
    """Enhanced MongoDB manager with advanced optimization features"""
    
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        self._initialized = True
        from require_env import require_env
        self.mongo_conn_string = os.getenv("MONGODB_CONN_STRING")
        # REQUIRED: no hardcoded DB-name default — a missing MONGODB_DATABASE
        # must fail loud, not silently point at the wrong (e.g. dev) database.
        self.database_name = require_env("MONGODB_DATABASE")
        
        # MongoDB connection pool settings from environment variables
        self.max_pool_size = int(os.getenv("MONGODB_MAX_POOL_SIZE", "10"))
        self.min_pool_size = int(os.getenv("MONGODB_MIN_POOL_SIZE", "2"))
        self.max_idle_time_ms = int(os.getenv("MONGODB_MAX_IDLE_TIME_MS", "30000"))
        self.server_selection_timeout_ms = int(os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "5000"))
        self.connect_timeout_ms = int(os.getenv("MONGODB_CONNECT_TIMEOUT_MS", "10000"))
        self.socket_timeout_ms = int(os.getenv("MONGODB_SOCKET_TIMEOUT_MS", "20000"))
        
        # Connection pools
        self._async_client = None
        self._sync_client = None
        
        # Bulk operation queues
        self._bulk_queues = defaultdict(list)
        self._bulk_timers = {}
        self._bulk_size_threshold = 100
        self._bulk_time_threshold = 5.0  # seconds
        
        # Performance metrics
        self._operation_metrics = defaultdict(lambda: {
            'count': 0,
            'total_time': 0,
            'errors': 0
        })
    
    async def get_async_client(self) -> AsyncIOMotorClient:
        """Get optimized async MongoDB client with connection pooling"""
        if self._async_client is None:
            async with self._lock:
                if self._async_client is None:
                    self._async_client = AsyncIOMotorClient(
                        self.mongo_conn_string,
                        maxPoolSize=self.max_pool_size,  # Now configurable via .env (default 10)
                        minPoolSize=self.min_pool_size,  # Now configurable via .env (default 2)
                        maxIdleTimeMS=self.max_idle_time_ms,  # Now configurable via .env
                        serverSelectionTimeoutMS=self.server_selection_timeout_ms,  # Now configurable via .env
                        connectTimeoutMS=self.connect_timeout_ms,  # Now configurable via .env
                        socketTimeoutMS=self.socket_timeout_ms,  # Now configurable via .env
                        retryWrites=True,
                        w='majority',
                        readPreference='primaryPreferred'
                    )
                    # Warm up connection pool
                    await self._async_client.admin.command('ping')
                    logger.info(f"🚀 Initialized optimized async MongoDB client (Max Pool: {self.max_pool_size})")
        return self._async_client
    
    def get_sync_client(self) -> MongoClient:
        """Get optimized sync MongoDB client"""
        if self._sync_client is None:
            self._sync_client = MongoClient(
                self.mongo_conn_string,
                maxPoolSize=self.max_pool_size,  # Now configurable via .env (default 10)
                minPoolSize=self.min_pool_size,  # Now configurable via .env (default 2)
                maxIdleTimeMS=self.max_idle_time_ms,  # Now configurable via .env
                serverSelectionTimeoutMS=self.server_selection_timeout_ms,  # Now configurable via .env
                connectTimeoutMS=self.connect_timeout_ms,  # Now configurable via .env
                socketTimeoutMS=self.socket_timeout_ms,  # Now configurable via .env
                retryWrites=True,
                w='majority',
                readPreference='primaryPreferred'
            )
            logger.info("🚀 Initialized optimized sync MongoDB client")
        return self._sync_client
    
    async def get_database(self) -> AsyncIOMotorDatabase:
        """Get async database instance"""
        client = await self.get_async_client()
        return client[self.database_name]
    
    async def ensure_indexes(self):
        """Create all necessary indexes for optimal performance"""
        db = await self.get_database()
        
        index_definitions = {
            'document_chunked': [
                ([('user_id', 1), ('document_id', 1)], {'name': 'device_doc_idx'}),
                ([('document_id', 1), ('chunk_index', 1)], {'unique': True, 'name': 'doc_chunk_unique_idx'}),
                ([('user_id', 1), ('folder_id', 1), ('created_at', -1)], {'name': 'device_folder_created_idx'}),
                ([('processing_status', 1)], {'name': 'processing_status_idx'}),
                ([('file_type', 1), ('created_at', -1)], {'name': 'file_type_created_idx'}),
                ([('user_id', 1), ('created_at', -1)], {'name': 'device_created_idx'}),
                ([('document_id', 1)], {'name': 'document_id_idx'}),
                ([('folder_id', 1), ('created_at', -1)], {'name': 'folder_created_idx'}),
                ([('file_type', 1)], {'name': 'file_type_idx'}),
                ([('created_at', -1)], {'name': 'created_at_idx'}),
                # Text index for full-text search
                ([('chunk_text', 'text'), ('topic', 'text'), ('filename', 'text')], {'name': 'text_search_idx'})
            ],
            'transcripts': [
                ([('user_id', 1), ('timestamp', -1)], {'name': 'device_timestamp_idx'}),
                ([('transcript_id', 1)], {'unique': True, 'name': 'transcript_id_unique_idx'}),
                ([('folder_id', 1)], {'name': 'folder_idx'})
            ],
            'Notes': [
                ([('user_id', 1), ('created_at', -1)], {'name': 'device_created_idx'}),
                ([('note_id', 1)], {'unique': True, 'name': 'note_id_unique_idx'}),
                ([('vector_id', 1)], {'name': 'vector_id_idx'})
            ],
            'chat_history': [
                ([('user_id', 1), ('session_id', 1)], {'name': 'device_session_idx'}),
                ([('session_id', 1), ('timestamp', -1)], {'name': 'session_timestamp_idx'}),
                ([('user_id', 1), ('timestamp', -1)], {'name': 'device_timestamp_idx'})
            ],
            'users': [
                ([('email', 1)], {'unique': True, 'name': 'email_unique_idx'}),
                ([('user_id', 1)], {'name': 'user_id_idx'})
            ],
            'milvus_chunks': [
                ([('document_id', 1)], {'unique': True, 'name': 'document_id_unique_idx'}),
                ([('user_id', 1)], {'name': 'user_id_idx'})
            ]
        }
        
        # Create indexes in parallel
        tasks = []
        for collection_name, indexes in index_definitions.items():
            collection = db[collection_name]
            for index_spec, index_options in indexes:
                tasks.append(self._create_index_safe(collection, index_spec, index_options))
        
        await asyncio.gather(*tasks)
        logger.info("✅ All indexes created successfully")
    
    async def _create_index_safe(self, collection, index_spec, index_options):
        """Safely create index, handling existing indexes and conflicts"""
        try:
            await collection.create_index(index_spec, **index_options)
        except Exception as e:
            index_name = index_options.get('name', 'unnamed')
            if any(keyword in str(e) for keyword in [
                "already exists", "IndexOptionsConflict", "IndexKeySpecsConflict", 
                "same name as the requested index"
            ]):
                logger.info(f"📋 Index {index_name} already exists or has conflicts - skipping")
            else:
                logger.error(f"Failed to create index {index_name}: {e}")
    
    # Bulk Operations
    async def bulk_write_optimized(self, collection_name: str, operations: List[Dict], ordered: bool = False):
        """Execute bulk write operations with optimization"""
        start_time = time.time()
        db = await self.get_database()
        collection = db[collection_name]
        
        try:
            if not operations:
                return {'success': True, 'modified': 0, 'inserted': 0}
            
            # Convert operations to pymongo format
            bulk_ops = []
            for op in operations:
                if op['type'] == 'insert':
                    bulk_ops.append(InsertOne(op['document']))
                elif op['type'] == 'update':
                    bulk_ops.append(UpdateOne(op['filter'], op['update'], upsert=op.get('upsert', False)))
                elif op['type'] == 'delete':
                    bulk_ops.append(DeleteOne(op['filter']))
            
            # Execute bulk operation
            result = await collection.bulk_write(bulk_ops, ordered=ordered)
            
            # Track metrics
            elapsed = time.time() - start_time
            self._track_operation('bulk_write', collection_name, elapsed, True)
            
            return {
                'success': True,
                'inserted': result.inserted_count,
                'modified': result.modified_count,
                'deleted': result.deleted_count,
                'upserted': len(result.upserted_ids) if result.upserted_ids else 0
            }
            
        except BulkWriteError as e:
            self._track_operation('bulk_write', collection_name, time.time() - start_time, False)
            logger.error(f"Bulk write error on {collection_name}: {e}")
            return {
                'success': False,
                'error': str(e),
                'write_errors': e.details.get('writeErrors', [])
            }
    
    async def find_cached(self, collection_name: str, filter_query: Dict, 
                         projection: Optional[Dict] = None, 
                         sort: Optional[List] = None,
                         limit: Optional[int] = None,
                         cache_key: Optional[str] = None) -> List[Dict]:
        """Find documents — always queries MongoDB live for data freshness."""
        start_time = time.time()
        db = await self.get_database()
        collection = db[collection_name]
        
        cursor = collection.find(filter_query, projection).max_time_ms(_FIND_MAX_MS)
        if sort:
            cursor = cursor.sort(sort)
        # Never an unbounded fetch: an explicit limit wins; otherwise apply a hard
        # default cap so a caller that forgets `limit` can't pull a whole
        # collection into memory and stall the worker.
        effective_limit = limit if limit else _FIND_DEFAULT_CAP
        cursor = cursor.limit(effective_limit)

        results = await cursor.to_list(effective_limit)
        if not limit and len(results) >= _FIND_DEFAULT_CAP:
            logger.warning(
                "find_cached on %s hit the default cap %d (no explicit limit) — "
                "results truncated; pass an explicit limit/paginate",
                collection_name, _FIND_DEFAULT_CAP,
            )
        
        # Track metrics
        elapsed = time.time() - start_time
        self._track_operation('find_direct', collection_name, elapsed, True)
        
        return results
    
    # Aggregation Pipeline
    async def aggregate_optimized(self, collection_name: str, pipeline: List[Dict], 
                                 allow_disk_use: bool = True) -> List[Dict]:
        """Execute optimized aggregation pipeline"""
        start_time = time.time()
        db = await self.get_database()
        collection = db[collection_name]
        
        try:
            # Add optimization hints to pipeline
            optimized_pipeline = self._optimize_pipeline(pipeline)
            
            cursor = collection.aggregate(
                optimized_pipeline,
                allowDiskUse=allow_disk_use,
                maxTimeMS=_FIND_MAX_MS,
                # Removed hint to avoid index errors - let MongoDB choose optimal index
            )

            # Bounded materialization — a pipeline without a $limit stage can emit
            # an unbounded result set; cap what we pull into memory.
            results = await cursor.to_list(_AGG_DEFAULT_CAP)
            if len(results) >= _AGG_DEFAULT_CAP:
                logger.warning(
                    "aggregate_optimized on %s hit the default cap %d — add a "
                    "$limit stage; results truncated",
                    collection_name, _AGG_DEFAULT_CAP,
                )
            
            # Track metrics
            elapsed = time.time() - start_time
            self._track_operation('aggregate', collection_name, elapsed, True)
            
            return results
            
        except Exception as e:
            self._track_operation('aggregate', collection_name, time.time() - start_time, False)
            logger.error(f"Aggregation error on {collection_name}: {e}")
            raise
    
    def _optimize_pipeline(self, pipeline: List[Dict]) -> List[Dict]:
        """Optimize aggregation pipeline"""
        optimized = []
        
        # Move $match stages to the beginning
        matches = [stage for stage in pipeline if '$match' in stage]
        others = [stage for stage in pipeline if '$match' not in stage]
        
        optimized.extend(matches)
        optimized.extend(others)
        
        return optimized
    
    # Performance Tracking
    def _track_operation(self, operation: str, collection: str, elapsed: float, success: bool):
        """Track operation metrics"""
        key = f"{operation}:{collection}"
        self._operation_metrics[key]['count'] += 1
        self._operation_metrics[key]['total_time'] += elapsed
        if not success:
            self._operation_metrics[key]['errors'] += 1
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        stats = {}
        for key, metrics in self._operation_metrics.items():
            avg_time = metrics['total_time'] / metrics['count'] if metrics['count'] > 0 else 0
            stats[key] = {
                'count': metrics['count'],
                'avg_time': round(avg_time, 3),
                'total_time': round(metrics['total_time'], 3),
                'errors': metrics['errors'],
                'error_rate': round(metrics['errors'] / metrics['count'] * 100, 2) if metrics['count'] > 0 else 0
            }
        return stats

# Singleton instance
_optimized_manager = None

def get_optimized_mongodb_manager() -> OptimizedMongoDBManager:
    """Get singleton instance of optimized MongoDB manager"""
    global _optimized_manager
    if _optimized_manager is None:
        _optimized_manager = OptimizedMongoDBManager()
    return _optimized_manager
