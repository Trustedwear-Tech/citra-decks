"""
Direct test of pricing_configs collection without listing collections
"""
import asyncio
import os
import logging
from dotenv import load_dotenv
from mongodb_manager import get_async_mongo_client, MONGODB_DATABASE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_pricing_direct():
    load_dotenv()
    
    logger.info(f"Testing direct pricing_configs query...")
    logger.info(f"Database: {MONGODB_DATABASE}")
    
    client = get_async_mongo_client()
    db = client[MONGODB_DATABASE]
    pricing_configs = db['pricingconfigs']  # Correct collection name without underscore
    
    try:
        # Try to count documents
        logger.info("Attempting count_documents...")
        count = await pricing_configs.count_documents({})
        logger.info(f"✅ Total documents in pricing_configs: {count}")
        
        # Try to find active pricing
        logger.info("Attempting find_one with is_active=True...")
        pricing = await pricing_configs.find_one(
            {'is_active': True},
            sort=[('version', -1)]
        )
        
        if pricing:
            logger.info(f"✅ Found active pricing:")
            logger.info(f"   Version: {pricing.get('version')}")
            logger.info(f"   is_active: {pricing.get('is_active')}")
            logger.info(f"   LLM input: ₹{pricing.get('token_pricing', {}).get('llm', {}).get('input_per_1k')}")
        else:
            logger.warning("⚠️ No active pricing found")
            
            # Try to find any pricing
            logger.info("Attempting to find any pricing document...")
            any_pricing = await pricing_configs.find_one({})
            if any_pricing:
                logger.info(f"Found pricing version {any_pricing.get('version')}: is_active={any_pricing.get('is_active')}, active={any_pricing.get('active')}")
            else:
                logger.error("❌ No pricing documents at all!")
                
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        
        # If permission error, try accessing the 'admin' database (usually has different permissions)
        if "not authorized" in str(e).lower() or "unauthorized" in str(e).lower():
            logger.info("\n🔍 Permission error detected. This means:")
            logger.info("   1. Connection is successful ✅")
            logger.info("   2. Authentication is successful ✅")
            logger.info("   3. But user 'dev' lacks read permissions on 'dev' database ❌")
            logger.info("\n📝 ACTION REQUIRED:")
            logger.info("   Go to MongoDB Atlas → Database Access")
            logger.info("   Edit user 'dev'")
            logger.info("   Grant 'readWrite' role on database 'dev'")

if __name__ == '__main__':
    asyncio.run(test_pricing_direct())
