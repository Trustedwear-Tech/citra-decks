import asyncio
import os
import sys
import logging

# Ensure local modules can be imported
sys.path.insert(0, os.getcwd())

from llamaindex_query_engine import UnifiedQueryEngine
from llama_index.core import Settings
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_hybrid_search():
    try:
        engine = UnifiedQueryEngine()
        
        # Test query
        query = "test query"
        user_id = "test_user"
        
        logger.info(f"🔍 Testing hybrid search for query: '{query}'")
        
        # Calling retrieve_personal_context which triggers _perform_personal_hybrid_query
        # which triggers _milvus_query
        results = await engine.retrieve_personal_context(
            query=query,
            user_id=user_id,
            top_k=5
        )
        
        logger.info(f"✅ Search complete. Found {len(results)} results")
        
    except Exception as e:
        logger.error(f"❌ Search failed: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_hybrid_search())
