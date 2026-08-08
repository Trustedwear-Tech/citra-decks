"""Quick check: structured_file_metadata for the test user."""
import asyncio
from dotenv import load_dotenv
load_dotenv()
from mongodb_manager import get_async_mongo_client, MONGODB_DATABASE

async def check():
    client = get_async_mongo_client()
    db = client[MONGODB_DATABASE]
    cursor = db["structured_file_metadata"].find(
        {
            "user_id": "rohit@trustedweartech.com",
            "folder_id": "3750a177-cd61-4dab-af9e-f16e760796be",
        },
        {"_id": 0, "document_id": 1, "filename": 1, "total_rows": 1},
    )
    docs = await cursor.to_list(length=10)
    for d in docs:
        print(f"doc_id: {d.get('document_id')}")
        print(f"filename: {d.get('filename')}")
        print(f"total_rows: {d.get('total_rows')}")
        print()

asyncio.run(check())
