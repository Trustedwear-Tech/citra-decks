"""
Test MongoDB connection and pricing_configs collection
"""
import asyncio
import os
import logging
from dotenv import load_dotenv
from mongodb_manager import get_async_mongo_client, MONGODB_DATABASE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_connection():
    load_dotenv()
    
    logger.info(f"Testing MongoDB connection...")
    logger.info(f"MONGODB_CONN_STRING env var: {os.getenv('MONGODB_CONN_STRING')[:50]}...")
    logger.info(f"MONGODB_DATABASE env var: {os.getenv('MONGODB_DATABASE')}")
    logger.info(f"MONGODB_DATABASE from manager: {MONGODB_DATABASE}")
    
    client = get_async_mongo_client()
    db = client[MONGODB_DATABASE]
    
    logger.info(f"\nDatabase object: {db.name}")
    
    # List all collections
    collections = await db.list_collection_names()
    logger.info(f"\nCollections in {db.name}:")
    for col in sorted(collections):
        logger.info(f"  - {col}")
    
    # Check pricing_configs collection
    pricing_configs = db['pricing_configs']
    count = await pricing_configs.count_documents({})
    logger.info(f"\nTotal documents in pricing_configs: {count}")
    
    if count > 0:
        all_docs = await pricing_configs.find({}).to_list(length=10)
        for doc in all_docs:
            logger.info(f"  Version: {doc.get('version')}, is_active: {doc.get('is_active')}, active: {doc.get('active')}")
    else:
        logger.warning("No documents found in pricing_configs collection!")
        logger.info("\nChecking if collection exists in other common database names...")
        
        # Try other possible database names
        for db_name in ['citra-ai', 'citra-ai', 'test', 'admin']:
            try:
                test_db = client[db_name]
                test_collection = test_db['pricing_configs']
                test_count = await test_collection.count_documents({})
                if test_count > 0:
                    logger.info(f"  ✅ Found {test_count} pricing configs in database: {db_name}")
            except Exception as e:
                logger.debug(f"  Could not check {db_name}: {e}")

if __name__ == '__main__':
    asyncio.run(test_connection())
