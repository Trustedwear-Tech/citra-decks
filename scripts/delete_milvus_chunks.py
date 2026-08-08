"""
Script to delete all Milvus chunks for a specific user_id
"""
import os
from dotenv import load_dotenv
from pymilvus import MilvusClient

# Load environment variables
load_dotenv()

def delete_user_chunks(user_id: str):
    """Delete all chunks for a specific user_id from Milvus collection"""

    # Initialize Milvus client
    client = MilvusClient(
        uri=os.getenv('ZILLIZ_CLOUD_URI'),
        token=os.getenv('ZILLIZ_CLOUD_API_KEY')
    )

    collection_name = os.getenv('MILVUS_COLLECTION', 'citra')

    print(f"🗄️ Connecting to Milvus collection: {collection_name}")
    print(f"👤 Processing chunks for user_id: {user_id}")

    # First, query chunks for this user to show what will be deleted
    try:
        query_results = client.query(
            collection_name=collection_name,
            filter=f'user_id == "{user_id}"',
            output_fields=["id", "chunk_id", "document_id", "topic_or_filename", "file_type", "user_id", "folder_id", "entity_id"],
            limit=16384  # Max allowed by Milvus
        )
        total_chunks = len(query_results)

        if total_chunks == 0:
            print("✅ No chunks found for this user. Nothing to delete.")
            return

        print(f"📊 Found {total_chunks} chunks to delete")
        print("\n🔍 Preview of chunks that will be deleted:")
        print("-" * 80)

        # Show first 10 chunks as preview
        for i, chunk in enumerate(query_results[:10]):
            chunk_id = chunk.get('chunk_id', 'unknown')
            doc_id = chunk.get('document_id', 'unknown')
            topic = chunk.get('topic_or_filename', chunk.get('topic', 'Unknown'))
            file_type = chunk.get('file_type', 'unknown')
            user_id_display = chunk.get('user_id', 'unknown')
            folder_id = chunk.get('folder_id', 'unknown')
            entity_id = chunk.get('entity_id', 'unknown')
            print(f"{i+1:2d}. Chunk ID: {chunk_id}")
            print(f"    Document ID: {doc_id}")
            print(f"    Topic/File: {topic}")
            print(f"    Type: {file_type}")
            print(f"    User ID: {user_id_display}")
            print(f"    Folder ID: {folder_id}")
            print(f"    Entity ID: {entity_id}")
            print()

        if total_chunks > 10:
            print(f"... and {total_chunks - 10} more chunks")
        print("-" * 80)

        # Confirm deletion
        confirm = input(f"\n⚠️  Are you sure you want to delete ALL {total_chunks} chunks for user '{user_id}'? (y/n) [default: n]: ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("❌ Deletion cancelled.")
            return

        print("\n🗑️  Deleting chunks...")

        # Delete the chunks
        delete_result = client.delete(
            collection_name=collection_name,
            filter=f'user_id == "{user_id}"'
        )

        print(f"✅ Successfully deleted {total_chunks} chunks for user '{user_id}'")
        print(f"🗑️ Delete operation result: {delete_result}")

    except Exception as e:
        print(f"❌ Error during deletion: {str(e)}")
        raise

if __name__ == "__main__":
    # Hardcoded user_id as requested
    target_user_id = "deeepakumar@gmail.com"
    delete_user_chunks(target_user_id)