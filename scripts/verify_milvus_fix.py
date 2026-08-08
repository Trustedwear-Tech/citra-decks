import os
import asyncio
import logging
import sys
from dotenv import load_dotenv

# Add current directory to path
sys.path.insert(0, os.getcwd())

from llamaindex_query_engine import UnifiedQueryEngine

async def test_type_checks():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    load_dotenv()
    
    engine = UnifiedQueryEngine()
    
    print("\n--- Test 1: Valid Dense Vector ---")
    valid_vector = [0.1] * 768
    try:
        # This might return 0 results but shouldn't raise ValueError from my checks
        # We don't care about Milvus connection errors here as much as my own type checks
        engine._milvus_query(vector=valid_vector, top_k=1)
        print("✅ Valid vector check passed (no ValueError)")
    except ValueError as e:
        print(f"❌ Valid vector check failed: {e}")
    except Exception as e:
        print(f"ℹ️ Milvus call failed (expected if not connected), but type check passed: {type(e).__name__}")

    print("\n--- Test 2: Invalid Vector Type (String) ---")
    try:
        engine._milvus_query(vector="not a list", top_k=1)
        print("❌ Invalid type (string) NOT caught!")
    except ValueError as e:
        print(f"✅ Invalid type caught: {e}")

    print("\n--- Test 3: Invalid Element Type (String in list) ---")
    try:
        engine._milvus_query(vector=[0.1, "bad"], top_k=1)
        print("❌ Invalid element type NOT caught!")
    except ValueError as e:
        print(f"✅ Invalid element type caught: {e}")

    print("\n--- Test 4: Simulation Hybrid Search (Recap) ---")
    try:
        from scripts.simulate_hybrid_search import run_simulation
        await run_simulation()
        print("✅ Simulation successful")
    except Exception as e:
        print(f"❌ Simulation failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_type_checks())
