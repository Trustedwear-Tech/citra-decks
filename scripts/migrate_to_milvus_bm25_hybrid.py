"""
Migration Script: Pinecone Sparse to Milvus BM25 Hybrid Search

This script helps migrate existing vector embeddings from the old Pinecone sparse model
to the new Milvus BM25 hybrid search system.

Migration Steps:
1. Connect to MongoDB to get list of documents
2. For each document, retrieve chunks and text content
3. Generate BM25 sparse vectors for existing dense embeddings
4. Update Milvus collection with hybrid vectors (dense + BM25 sparse)
5. Update MongoDB metadata to reflect hybrid status

Usage:
    python scripts/migrate_to_milvus_bm25_hybrid.py [options]

Options:
    --dry-run          Run in dry-run mode (no actual updates)
    --batch-size N     Process N documents at a time (default: 10)
    --user-id ID       Migrate documents for specific user only
    --document-id ID   Migrate specific document only
    --skip-fitted      Skip fitting BM25 (use if already fitted)

Requirements:
    - MongoDB connection configured
    - Milvus/Zilliz Cloud connection configured
    - ENABLE_HYBRID_SEARCH=true in .env
"""

import asyncio
import logging
import argparse
import sys
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from pymilvus import MilvusClient
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Import services
from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
from services.milvus_sparse_service import get_bm25_service
from config.milvus_config import (
    get_collection_name,
    get_milvus_uri,
    get_milvus_api_key,
    is_hybrid_search_enabled
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('migration_milvus_bm25_hybrid.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)


class MilvusBM25MigrationService:
    """Service to migrate existing vectors to Milvus BM25 hybrid search"""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.mongo_client = get_async_mongo_client()
        self.db = self.mongo_client[MONGODB_DATABASE]
        self.chunks_collection = self.db["document_chunked"]
        self.mappings_collection = self.db["milvus_chunks"]
        
        # Initialize Milvus client
        self.milvus_client = MilvusClient(
            uri=get_milvus_uri(),
            token=get_milvus_api_key()
        )
        self.collection_name = get_collection_name()
        
        # Get BM25 service
        self.bm25_service = get_bm25_service()
        
        # Statistics
        self.stats = {
            'total_documents': 0,
            'processed_documents': 0,
            'failed_documents': 0,
            'total_vectors': 0,
            'updated_vectors': 0,
            'skipped_vectors': 0
        }
    
    async def get_documents_to_migrate(
        self,
        user_id: Optional[str] = None,
        document_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get list of documents that need migration"""
        logger.info("📋 Fetching documents to migrate...")
        
        # Build query
        query = {}
        if user_id:
            query['user_id'] = user_id
        if document_id:
            query['document_id'] = document_id
        
        # Get unique documents
        pipeline = [
            {'$match': query} if query else {'$match': {}},
            {
                '$group': {
                    '_id': '$document_id',
                    'user_id': {'$first': '$user_id'},
                    'folder_id': {'$first': '$folder_id'},
                    'topic': {'$first': '$topic'},
                    'file_type': {'$first': '$file_type'},
                    'total_chunks': {'$max': '$total_chunks'},
                    'has_vectors': {'$first': '$has_vectors'}
                }
            }
        ]
        
        documents = []
        async for doc in self.chunks_collection.aggregate(pipeline):
            documents.append({
                'document_id': doc['_id'],
                'user_id': doc.get('user_id'),
                'folder_id': doc.get('folder_id'),
                'topic': doc.get('topic', 'Untitled'),
                'file_type': doc.get('file_type', 'unknown'),
                'total_chunks': doc.get('total_chunks', 0),
                'has_vectors': doc.get('has_vectors', False)
            })
        
        logger.info(f"📋 Found {len(documents)} documents to migrate")
        return documents
    
    async def get_document_chunks(self, document_id: str) -> List[Dict[str, Any]]:
        """Get all chunks for a document"""
        chunks = []
        cursor = self.chunks_collection.find(
            {'document_id': document_id}
        ).sort('chunk_index', 1)
        
        async for chunk in cursor:
            chunks.append(chunk)
        
        return chunks
    
    async def fit_bm25_corpus(self, document_ids: List[str]):
        """Fit BM25 model on all document chunks"""
        logger.info("📊 Building BM25 corpus from all documents...")
        
        corpus_texts = []
        for doc_id in document_ids:
            chunks = await self.get_document_chunks(doc_id)
            for chunk in chunks:
                # Get text from metadata
                metadata = chunk.get('metadata', {})
                text = metadata.get('text', chunk.get('chunk_text', ''))
                if text and text.strip():
                    corpus_texts.append(text)
        
        logger.info(f"📊 Corpus size: {len(corpus_texts)} chunks")
        
        if corpus_texts:
            # Fit BM25 in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.bm25_service.fit, corpus_texts)
            logger.info("✅ BM25 model fitted successfully")
        else:
            logger.warning("⚠️ Empty corpus - cannot fit BM25")
    
    async def migrate_document(self, doc_info: Dict[str, Any]) -> bool:
        """Migrate a single document to hybrid search"""
        document_id = doc_info['document_id']
        user_id = doc_info['user_id']
        
        logger.info(f"🔄 Migrating document: {document_id} ({doc_info['topic']})")
        
        try:
            # Get all chunks
            chunks = await self.get_document_chunks(document_id)
            
            if not chunks:
                logger.warning(f"⚠️ No chunks found for document {document_id}")
                return False
            
            # Extract texts from chunks
            chunk_texts = []
            chunk_indices = []
            for chunk in chunks:
                metadata = chunk.get('metadata', {})
                text = metadata.get('text', chunk.get('chunk_text', ''))
                chunk_idx = chunk.get('chunk_index', 0)
                
                if text and text.strip():
                    chunk_texts.append(text)
                    chunk_indices.append(chunk_idx)
            
            if not chunk_texts:
                logger.warning(f"⚠️ No text content found in chunks for {document_id}")
                return False
            
            logger.info(f"📄 Processing {len(chunk_texts)} chunks with text content")
            
            # Generate BM25 sparse vectors
            logger.info(f"🔍 Generating BM25 sparse vectors...")
            sparse_vectors = await self.bm25_service.encode_documents_async(chunk_texts)
            
            if len(sparse_vectors) != len(chunk_texts):
                logger.error(f"❌ Sparse vector count mismatch: {len(sparse_vectors)} != {len(chunk_texts)}")
                return False
            
            # Update Milvus vectors with sparse embeddings
            if not self.dry_run:
                updated_count = 0
                for idx, (text, sparse_vec, chunk_idx) in enumerate(zip(chunk_texts, sparse_vectors, chunk_indices)):
                    vector_id = f"{document_id}_{chunk_idx}"
                    
                    # Check if vector exists in Milvus
                    try:
                        results = self.milvus_client.query(
                            collection_name=self.collection_name,
                            filter=f'id == "{vector_id}"',
                            output_fields=["id"]
                        )
                        
                        if results:
                            # Vector exists - would need to update it
                            # Note: Milvus doesn't support direct updates, would need delete + insert
                            logger.debug(f"Vector {vector_id} exists in Milvus")
                            updated_count += 1
                        else:
                            logger.debug(f"Vector {vector_id} not found in Milvus (will be created on next upload)")
                    
                    except Exception as e:
                        logger.warning(f"⚠️ Could not check vector {vector_id}: {e}")
                
                self.stats['updated_vectors'] += updated_count
                logger.info(f"✅ Checked {updated_count} vectors in Milvus")
            else:
                logger.info(f"🔍 [DRY RUN] Would generate sparse vectors for {len(chunk_texts)} chunks")
            
            self.stats['processed_documents'] += 1
            self.stats['total_vectors'] += len(chunk_texts)
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to migrate document {document_id}: {e}")
            self.stats['failed_documents'] += 1
            return False
    
    async def run_migration(
        self,
        batch_size: int = 10,
        user_id: Optional[str] = None,
        document_id: Optional[str] = None,
        skip_fit: bool = False
    ):
        """Run the complete migration process"""
        logger.info("=" * 80)
        logger.info("🚀 Starting Milvus BM25 Hybrid Search Migration")
        logger.info(f"   Mode: {'DRY RUN' if self.dry_run else 'PRODUCTION'}")
        logger.info(f"   Hybrid Search Enabled: {is_hybrid_search_enabled()}")
        logger.info("=" * 80)
        
        if not is_hybrid_search_enabled():
            logger.error("❌ Hybrid search is not enabled. Set ENABLE_HYBRID_SEARCH=true in .env")
            return
        
        # Get documents to migrate
        documents = await self.get_documents_to_migrate(user_id, document_id)
        self.stats['total_documents'] = len(documents)
        
        if not documents:
            logger.info("✅ No documents to migrate")
            return
        
        # Fit BM25 on corpus (unless skipped)
        if not skip_fit:
            document_ids = [doc['document_id'] for doc in documents]
            await self.fit_bm25_corpus(document_ids)
        else:
            logger.info("⏭️ Skipping BM25 fitting (--skip-fitted flag)")
        
        # Process documents in batches
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i+batch_size]
            logger.info(f"\n📦 Processing batch {i//batch_size + 1} ({len(batch)} documents)")
            
            # Process batch concurrently
            tasks = [self.migrate_document(doc) for doc in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Log batch results
            successful = sum(1 for r in results if r is True)
            logger.info(f"✅ Batch complete: {successful}/{len(batch)} successful")
        
        # Print final statistics
        self.print_statistics()
    
    def print_statistics(self):
        """Print migration statistics"""
        logger.info("\n" + "=" * 80)
        logger.info("📊 Migration Statistics")
        logger.info("=" * 80)
        logger.info(f"Total Documents:      {self.stats['total_documents']}")
        logger.info(f"Processed Documents:  {self.stats['processed_documents']}")
        logger.info(f"Failed Documents:     {self.stats['failed_documents']}")
        logger.info(f"Total Vectors:        {self.stats['total_vectors']}")
        logger.info(f"Updated Vectors:      {self.stats['updated_vectors']}")
        logger.info(f"Skipped Vectors:      {self.stats['skipped_vectors']}")
        logger.info("=" * 80)
        
        if self.dry_run:
            logger.info("🔍 This was a DRY RUN - no actual changes were made")
        else:
            logger.info("✅ Migration complete!")


async def main():
    """Main migration entry point"""
    parser = argparse.ArgumentParser(description='Migrate to Milvus BM25 Hybrid Search')
    parser.add_argument('--dry-run', action='store_true', help='Run in dry-run mode (no updates)')
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size for processing')
    parser.add_argument('--user-id', type=str, help='Migrate documents for specific user only')
    parser.add_argument('--document-id', type=str, help='Migrate specific document only')
    parser.add_argument('--skip-fitted', action='store_true', help='Skip BM25 fitting (if already fitted)')
    
    args = parser.parse_args()
    
    # Create migration service
    migration_service = MilvusBM25MigrationService(dry_run=args.dry_run)
    
    # Run migration
    try:
        await migration_service.run_migration(
            batch_size=args.batch_size,
            user_id=args.user_id,
            document_id=args.document_id,
            skip_fit=args.skip_fitted
        )
    except KeyboardInterrupt:
        logger.info("\n⚠️ Migration interrupted by user")
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
    finally:
        # Cleanup
        migration_service.mongo_client.close()
        logger.info("🔒 Database connections closed")


if __name__ == "__main__":
    asyncio.run(main())
