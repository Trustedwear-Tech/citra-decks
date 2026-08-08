import os
from pymilvus import connections, Collection, DataType, utility
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_milvus():
    uri = os.getenv("ZILLIZ_CLOUD_URI")
    token = os.getenv("ZILLIZ_CLOUD_API_KEY")
    collection_name = os.getenv("MILVUS_COLLECTION", "citra")

    if not uri or not token:
        logger.error("❌ ZILLIZ_CLOUD_URI or ZILLIZ_CLOUD_API_KEY not set")
        return

    # Connect using low-level API
    connections.connect(alias="default", uri=uri, token=token)
    
    logger.info(f"🔌 Connected to Milvus (low-level). Checking collection: {collection_name}")
    
    if not utility.has_collection(collection_name):
        logger.error(f"❌ Collection {collection_name} not found!")
        return
        
    collection = Collection(collection_name)
    print("\n" + "="*50)
    print(f"COLLECTION: {collection_name}")
    print("="*50)
    
    schema = collection.schema
    fields = schema.fields
    
    print(f"Fields found: {len(fields)}")
    for field in fields:
        name = field.name
        dtype = field.dtype
        params = field.params
        dim = params.get('dim', 'N/A')
        print(f" - {name:20} | Type: {dtype} | Dim: {dim}")
    
    # Check for indexes
    print("\nINDEXES:")
    indexes = collection.indexes
    print(f"Indexes found: {len(indexes)}")
    for index in indexes:
        print(f" - Field: {index.field_name}")
        print(f"   Index Name: {index.index_name}")
        print(f"   Index Params: {index.params}")
    
    # Check for functions (server-side BM25)
    # Functions are part of schema in newer Milvus
    try:
        if hasattr(schema, 'functions'):
            functions = schema.functions
            print(f"\nFunctions found: {len(functions)}")
            for func in functions:
                print(f" - {func}")
    except Exception:
        print("\nFunctions not accessible via this schema object")
    
    print("="*50 + "\n")

if __name__ == "__main__":
    check_milvus()

if __name__ == "__main__":
    check_milvus()
