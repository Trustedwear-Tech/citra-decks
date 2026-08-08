"""
Daily Usage Trend Service
Fetches daily aggregated usage from credittransactions collection
"""
from datetime import datetime, timedelta
from typing import Dict, List, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

logger = logging.getLogger(__name__)


class DailyUsageTrendService:
    """Service for fetching daily usage trends from credit transactions"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.transactions_collection = db.credittransactions
    
    async def get_daily_usage_trend(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Fetch daily usage trend for the last N days
        
        Args:
            user_id: User email
            days: Number of days to fetch (default 30)
            
        Returns:
            Dictionary with daily trend data
        """
        try:
            # Calculate date N days ago
            start_date = datetime.utcnow() - timedelta(days=days)
            
            logger.info(f"📊 Fetching {days}-day usage trend for: {user_id}")
            logger.info(f"📅 Date range: Last {days} days from {start_date.isoformat()}")
            
            # MongoDB aggregation pipeline
            pipeline = [
                {
                    '$match': {
                        'user_id': user_id,
                        'type': {'$in': ['query_usage', 'upload_usage']},
                        'timestamp': {'$gte': start_date}
                    }
                },
                {
                    '$project': {
                        'date': {
                            '$dateToString': {
                                'format': '%Y-%m-%d',
                                'date': '$timestamp'
                            }
                        },
                        'type': 1,
                        'amount': {'$abs': '$amount'},  # Make amounts positive
                        'query_metadata': 1,
                        'upload_metadata': 1
                    }
                },
                {
                    '$group': {
                        '_id': {
                            'date': '$date',
                            'type': '$type'
                        },
                        'total_cost': {'$sum': '$amount'},
                        'count': {'$sum': 1},
                        # Query-specific aggregations
                        'total_tokens': {
                            '$sum': {
                                '$cond': [
                                    {'$eq': ['$type', 'query_usage']},
                                    {'$ifNull': ['$query_metadata.tokens_used', 0]},
                                    0
                                ]
                            }
                        },
                        # Upload-specific aggregations
                        'total_bytes': {
                            '$sum': {
                                '$cond': [
                                    {'$eq': ['$type', 'upload_usage']},
                                    {'$ifNull': ['$upload_metadata.file_size_bytes', 0]},
                                    0
                                ]
                            }
                        }
                    }
                },
                {
                    '$sort': {'_id.date': 1}
                }
            ]
            
            # Execute aggregation
            daily_usage = await self.transactions_collection.aggregate(pipeline).to_list(length=None)
            
            logger.info(f"✅ Found {len(daily_usage)} daily usage records")
            
            # Transform data for frontend consumption
            dates = []
            query_data = []
            upload_data = []
            query_count_data = []
            upload_count_data = []
            query_token_data = []
            
            # Create a map for quick lookup
            usage_map = {}
            for item in daily_usage:
                key = f"{item['_id']['date']}_{item['_id']['type']}"
                usage_map[key] = item
            
            # Generate all dates in the last N days
            for i in range(days - 1, -1, -1):
                date = datetime.utcnow() - timedelta(days=i)
                date_str = date.strftime('%Y-%m-%d')
                
                dates.append(date_str)
                
                # Query data
                query_key = f"{date_str}_query_usage"
                query_item = usage_map.get(query_key)
                query_data.append(query_item['total_cost'] if query_item else 0)
                query_count_data.append(query_item['count'] if query_item else 0)
                query_token_data.append(query_item['total_tokens'] if query_item else 0)
                
                # Upload data
                upload_key = f"{date_str}_upload_usage"
                upload_item = usage_map.get(upload_key)
                upload_data.append(upload_item['total_cost'] if upload_item else 0)
                upload_count_data.append(upload_item['count'] if upload_item else 0)
            
            # Calculate summary statistics
            total_query_cost = sum(query_data)
            total_upload_cost = sum(upload_data)
            total_query_count = sum(query_count_data)
            total_upload_count = sum(upload_count_data)
            total_query_tokens = sum(query_token_data)
            
            return {
                'success': True,
                'date_range': {
                    'start': dates[0] if dates else None,
                    'end': dates[-1] if dates else None,
                    'days': days
                },
                'daily_trend': {
                    'dates': dates,
                    'query_costs': query_data,
                    'upload_costs': upload_data,
                    'query_counts': query_count_data,
                    'upload_counts': upload_count_data,
                    'query_tokens': query_token_data
                },
                'summary': {
                    'total_query_cost': round(total_query_cost, 2),
                    'total_upload_cost': round(total_upload_cost, 2),
                    'total_cost': round(total_query_cost + total_upload_cost, 2),
                    'total_queries': total_query_count,
                    'total_uploads': total_upload_count,
                    'total_query_tokens': total_query_tokens,
                    'avg_query_cost': round(total_query_cost / total_query_count, 2) if total_query_count > 0 else 0,
                    'avg_upload_cost': round(total_upload_cost / total_upload_count, 2) if total_upload_count > 0 else 0
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error fetching daily usage trend: {e}")
            raise
