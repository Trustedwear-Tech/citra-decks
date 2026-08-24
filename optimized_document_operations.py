# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

from typing import List, Dict, Optional, Any
import asyncio
from datetime import datetime
import logging
from mongodb_manager_optimized import get_optimized_mongodb_manager

logger = logging.getLogger(__name__)

class OptimizedDocumentOperations:
    """Optimized document operations for Citra AI"""
    
    def __init__(self):
        self.mongo_manager = get_optimized_mongodb_manager()
        self._batch_size = 100
    
    async def bulk_insert_documents(self, documents: List[Dict]) -> Dict[str, Any]:
        """Bulk insert documents with optimization"""
        if not documents:
            return {'success': True, 'inserted': 0}
        
        # Prepare bulk operations
        operations = []
        for doc in documents:
            # Add timestamps if not present
            if 'created_at' not in doc:
                doc['created_at'] = datetime.utcnow()
            if 'updated_at' not in doc:
                doc['updated_at'] = doc['created_at']
            
            operations.append({
                'type': 'insert',
                'document': doc
            })
        
        # Execute in batches
        results = {'success': True, 'inserted': 0, 'errors': []}
        
        for i in range(0, len(operations), self._batch_size):
            batch = operations[i:i + self._batch_size]
            result = await self.mongo_manager.bulk_write_optimized('document_chunked', batch)
            
            if result['success']:
                results['inserted'] += result['inserted']
            else:
                results['errors'].append(result.get('error'))
        
        logger.info(f"✅ Bulk inserted {results['inserted']} documents")
        return results
    
    async def get_documents_paginated(self, user_id: str, folder_id: Optional[str] = None,
                                    page: int = 1, limit: int = 50, query: Optional[str] = None,
                                    team_id: Optional[str] = None) -> Dict[str, Any]:
        """Get documents with optimized pagination and optional search"""
        # Build filter - IMPORTANT: Only get first chunk of each document (chunk_index=0)
        # Filter by team_id for workspace support
        if team_id:
            # Team workspace: Show only team documents
            filter_query = {
                'team_id': team_id,
                'chunk_index': 0,  # 🔑 KEY FIX: Only return first chunk per document
                'is_enterprise': {'$ne': True}  # 🔑 EXCLUDE enterprise documents from team views
            }
        else:
            # Personal workspace: Show user's personal documents (no team_id or null team_id)
            filter_query = {
                'user_id': user_id,
                'chunk_index': 0,  # 🔑 KEY FIX: Only return first chunk per document (like enterprise documents)
                'is_enterprise': {'$ne': True},  # 🔑 EXCLUDE enterprise documents from personal views
                '$or': [
                    {'team_id': {'$exists': False}},
                    {'team_id': None}
                ]
            }
        if folder_id:
            filter_query['folder_id'] = folder_id
        
        # Add text search if query provided
        if query and query.strip():
            # Use regex search across multiple fields instead of $text for better compatibility
            search_regex = {"$regex": query.strip(), "$options": "i"}
            filter_query["$or"] = [
                {"filename": search_regex},
                {"topic": search_regex},
                {"topic_or_filename": search_regex},
                {"chunk_text": search_regex}
            ]
        
        # Use aggregation for efficient pagination
        pipeline = [
            {'$match': filter_query},
            {'$sort': {'created_at': -1}},  # Sort by creation date, newest first
            # Lookup entity information from enterprise_entities collection
            {'$lookup': {
                'from': 'enterprise_entities',
                'localField': 'entity_id',
                'foreignField': 'entity_id',
                'as': 'entity_info'
            }},
            # Add entity_name field from the lookup result
            {'$addFields': {
                'entity_name': {
                    '$ifNull': [
                        {'$arrayElemAt': ['$entity_info.entity_name', 0]},
                        None
                    ]
                }
            }},
            {'$facet': {
                'metadata': [{'$count': 'total'}],
                'documents': [
                    {'$skip': (page - 1) * limit},
                    {'$limit': limit},
                    {'$project': {
                        'document_id': 1,
                        'topic_or_filename': 1,  # Unified field for display
                        'file_type': 1,
                        'created_at': 1,
                        'folder_id': 1,
                        'file_size': 1,
                        'chunk_count': 1,
                        'is_enterprise': 1,  # Include enterprise flag for UI indicators
                        'entity_id': 1,      # Include entity information
                        'entity_name': 1,    # Include entity name from lookup
                        '_id': 0             # Exclude MongoDB _id from results
                    }}
                ]
            }}
        ]
        
        results = await self.mongo_manager.aggregate_optimized('document_chunked', pipeline)
        
        if results and results[0]:
            total = results[0]['metadata'][0]['total'] if results[0]['metadata'] else 0
            documents = results[0]['documents']
            
            return {
                'documents': documents,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit,
                'has_more': page * limit < total
            }
        
        return {
            'documents': [],
            'total': 0,
            'page': page,
            'pages': 0,
            'has_more': False
        }
    
    async def search_documents(self, user_id: str, query: str, 
                             filters: Optional[Dict] = None) -> List[Dict]:
        """Optimized document search using text index"""
        # Build search query
        search_filter = {
            'user_id': user_id,
            '$text': {'$search': query},
            'is_enterprise': {'$ne': True}  # 🔑 EXCLUDE enterprise documents from personal search
        }
        
        if filters:
            search_filter.update(filters)
        
        # Use projection to reduce data transfer
        projection = {
            'document_id': 1,
            'topic_or_filename': 1,  # Unified field for display
            'file_type': 1,
            'created_at': 1,
            'score': {'$meta': 'textScore'}
        }
        
        # Execute search with caching
        results = await self.mongo_manager.find_cached(
            'document_chunked',
            search_filter,
            projection=projection,
            sort=[('score', {'$meta': 'textScore'})],
            limit=50,
            cache_key=f"search:{user_id}:{query}"
        )
        
        return results
    
    async def update_documents_bulk(self, updates: List[Dict]) -> Dict[str, Any]:
        """Bulk update documents"""
        operations = []
        
        for update in updates:
            operations.append({
                'type': 'update',
                'filter': {'document_id': update['document_id']},
                'update': {
                    '$set': {
                        **update.get('fields', {}),
                        'updated_at': datetime.utcnow()
                    }
                },
                'upsert': False
            })
        
        return await self.mongo_manager.bulk_write_optimized('document_chunked', operations)
    
    async def get_folder_statistics(self, user_id: str) -> List[Dict]:
        """Get folder statistics using aggregation"""
        pipeline = [
            {'$match': {
                'user_id': user_id,
                'is_enterprise': {'$ne': True}  # 🔑 EXCLUDE enterprise documents from personal folder stats
            }},
            {'$group': {
                '_id': '$folder_id',
                'count': {'$sum': 1},
                'total_size': {'$sum': '$file_size'},
                'file_types': {'$addToSet': '$file_type'},
                'latest_upload': {'$max': '$created_at'}
            }},
            {'$project': {
                'folder_id': '$_id',
                'document_count': '$count',
                'total_size': 1,
                'file_types': 1,
                'latest_upload': 1,
                '_id': 0
            }},
            {'$sort': {'document_count': -1}}
        ]
        
        return await self.mongo_manager.aggregate_optimized('document_chunked', pipeline)
