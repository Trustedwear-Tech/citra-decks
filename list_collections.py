"""List all collections in MongoDB database"""
import asyncio
from citra_mongo import get_async_mongo_client, MONGODB_DATABASE

async def main():
    client = get_async_mongo_client()
    db = client[MONGODB_DATABASE]
    
    collections = await db.list_collection_names()
    print(f"\n📚 Collections in database '{MONGODB_DATABASE}':")
    for coll in sorted(collections):
        count = await db[coll].count_documents({})
        print(f"   - {coll}: {count} documents")

if __name__ == "__main__":
    asyncio.run(main())
