import asyncio
import logging
from mongodb_manager_optimized import get_optimized_mongodb_manager
from optimized_document_operations import OptimizedDocumentOperations
from optimized_query_operations import OptimizedQueryOperations

logger = logging.getLogger(__name__)

async def initialize_mongodb_optimizations():
    """Initialize all MongoDB optimizations at startup"""
    logger.info("🚀 Starting MongoDB optimization initialization...")
    
    try:
        # Get manager instance
        mongo_manager = get_optimized_mongodb_manager()
        
        # Initialize connection pool
        await mongo_manager.get_async_client()
        logger.info("✅ MongoDB connection pool initialized")
        
        # Create indexes
        await mongo_manager.ensure_indexes()
        logger.info("✅ MongoDB indexes created")
        
        # Warm up collections
        db = await mongo_manager.get_database()
        collections = ['document_chunked', 'transcripts', 'Notes', 'chat_history', 'users']
        
        for collection_name in collections:
            collection = db[collection_name]
            # Warm up with a simple query
            await collection.find_one({})
        
        logger.info("✅ MongoDB collections warmed up")
        
        # Initialize operation handlers
        doc_ops = OptimizedDocumentOperations()
        query_ops = OptimizedQueryOperations()
        
        logger.info("✅ MongoDB optimization initialization complete")
        
        return {
            'mongo_manager': mongo_manager,
            'doc_ops': doc_ops,
            'query_ops': query_ops
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize MongoDB optimizations: {e}")
        raise

# Run initialization
if __name__ == "__main__":
    asyncio.run(initialize_mongodb_optimizations())
