import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import logging
from mongodb_manager_optimized import get_optimized_mongodb_manager

logger = logging.getLogger(__name__)

class OptimizedQueryOperations:
    """Optimized query and chat operations"""
    
    def __init__(self):
        self.mongo_manager = get_optimized_mongodb_manager()
    
    async def get_chat_history_optimized(self, user_id: str, session_id: Optional[str] = None,
                                       limit: int = 50) -> List[Dict]:
        """Get chat history with optimization"""
        # Build filter
        filter_query = {'user_id': user_id}
        if session_id:
            filter_query['session_id'] = session_id
        
        # Use aggregation for efficient retrieval
        pipeline = [
            {'$match': filter_query},
            {'$sort': {'timestamp': -1}},
            {'$limit': limit},
            {'$lookup': {
                'from': 'users',
                'localField': 'user_id',
                'foreignField': 'email',
                'as': 'user_info'
            }},
            {'$project': {
                'session_id': 1,
                'query': 1,
                'response': 1,
                'timestamp': 1,
                'model_used': 1,
                'contexts_used': {'$size': {'$ifNull': ['$contexts', []]}},
                'user_name': {'$arrayElemAt': ['$user_info.name', 0]}
            }}
        ]
        
        return await self.mongo_manager.aggregate_optimized('chat_history', pipeline)
    
    async def store_chat_message_optimized(self, message_data: Dict) -> Dict[str, Any]:
        """Store chat message with optimization"""
        # Add metadata
        message_data['timestamp'] = datetime.utcnow()
        message_data['indexed'] = False  # For background processing
        
        # Use single operation
        db = await self.mongo_manager.get_database()
        collection = db['chat_history']
        
        result = await collection.insert_one(message_data)
        
        # Queue for background indexing
        asyncio.create_task(self._background_index_message(str(result.inserted_id)))
        
        return {'success': True, 'message_id': str(result.inserted_id)}
    
    async def _background_index_message(self, message_id: str):
        """Background task to index message for search"""
        try:
            await asyncio.sleep(2)  # Small delay to avoid immediate processing
            
            db = await self.mongo_manager.get_database()
            collection = db['chat_history']
            
            # Extract keywords and update
            message = await collection.find_one({'_id': message_id})
            if message:
                keywords = self._extract_keywords(message.get('query', '') + ' ' + message.get('response', ''))
                
                await collection.update_one(
                    {'_id': message_id},
                    {
                        '$set': {
                            'keywords': keywords,
                            'indexed': True
                        }
                    }
                )
        except Exception as e:
            logger.error(f"Failed to index message {message_id}: {e}")
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text"""
        # Simple keyword extraction - can be enhanced with NLP
        import re
        words = re.findall(r'\b\w+\b', text.lower())
        # Filter common words
        stop_words = {'the', 'is', 'at', 'which', 'on', 'and', 'a', 'an', 'as', 'are', 'was', 'were'}
        keywords = [w for w in words if len(w) > 3 and w not in stop_words]
        return list(set(keywords[:20]))  # Limit to 20 keywords
    
    async def get_usage_analytics(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get usage analytics with aggregation"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {
                '$match': {
                    'user_id': user_id,
                    'timestamp': {'$gte': start_date}
                }
            },
            {
                '$facet': {
                    'daily_usage': [
                        {
                            '$group': {
                                '_id': {
                                    'year': {'$year': '$timestamp'},
                                    'month': {'$month': '$timestamp'},
                                    'day': {'$dayOfMonth': '$timestamp'}
                                },
                                'queries': {'$sum': 1},
                                'models_used': {'$addToSet': '$model_used'}
                            }
                        },
                        {'$sort': {'_id': 1}}
                    ],
                    'model_distribution': [
                        {
                            '$group': {
                                '_id': '$model_used',
                                'count': {'$sum': 1}
                            }
                        }
                    ],
                    'feature_usage': [
                        {
                            '$group': {
                                '_id': {
                                    'deep_research': '$deep_research',
                                    'internet_search': '$use_internet'
                                },
                                'count': {'$sum': 1}
                            }
                        }
                    ]
                }
            }
        ]
        
        results = await self.mongo_manager.aggregate_optimized('chat_history', pipeline)
        
        if results:
            return results[0]
        return {'daily_usage': [], 'model_distribution': [], 'feature_usage': []}
