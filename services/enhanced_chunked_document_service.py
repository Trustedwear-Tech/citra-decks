# ============================  Enhanced Chunked Document Service  =============================
# Purpose: Complete document service with chunking, embedding, and vector storage
# Features: Store documents in MongoDB chunks, create embeddings, and store in Milvus
# Consolidates: document_manager.py + chunked_document_service.py + milvus_chunk_service.py
# ----------------------------------------------------------------------------------------

import logging
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path
import math
import asyncio
import os
import time
import re
from collections import Counter
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from fastapi import HTTPException, status

# LlamaIndex imports for advanced chunking
try:
    from llama_index.core.node_parser import (
        SentenceSplitter,
        HierarchicalNodeParser
    )
    from llama_index.core import Document as LlamaDocument
    from llama_index.core.schema import TextNode
    LLAMAINDEX_AVAILABLE = True
except ImportError:
    LLAMAINDEX_AVAILABLE = False
    logging.warning("LlamaIndex not available - falling back to simple chunking")

# Import the chunk models
from models.document_chunk import MongoDbChunkModel, DocumentMetadataModel
from models.milvus_chunk import MilvusChunkModel

# Import storage configuration
from config.document_storage_config import (
    get_storage_metadata
)

# Import Milvus configuration
from config.milvus_config import (
    get_collection_name,
    get_milvus_uri,
    get_milvus_api_key,
    is_hybrid_search_enabled
)

# Import utilities for embedding generation
from utils import embed_text, embed_texts_batch

# Milvus singleton
from config.milvus_config import get_milvus_client

# Import BM25 sparse embedding service
# NOTE: BM25 service import removed - Zilliz Cloud handles sparse vectors natively
# from services.milvus_sparse_service import get_bm25_service, bm25_service_enabled

# Import unified metadata schema (breaking change - no legacy support)
from models.unified_metadata_schema import UnifiedMetadataSchema, MetadataConstants, MetadataValidator

EMBED_DIM = 768  # OpenAI text-embedding-3-small dimension (768D)

class EnhancedChunkedDocumentService:
    """
    Complete document service with chunking, embedding, and vector storage
    Consolidates functionality from multiple services into one unified service
    """
    
    def __init__(self, mongo_client: AsyncIOMotorClient, database_name: str = None,
                 collection_name: str = None):
        self.logger = logging.getLogger(__name__)
        self.client = mongo_client
        # Optional per-instance Milvus collection override. Default (None) uses
        # the deployment collection (get_collection_name → MILVUS_COLLECTION,
        # e.g. "citra"). The dept SOP Library passes its own per-dept collection
        # so uploads land where the dept-MCP queries. All insert/delete paths
        # read self.collection_name, so setting it here routes them uniformly.
        self._collection_override = collection_name
        # Always use database name from .env file (via mongodb_manager)
        if database_name is None:
            from citra_mongo import MONGODB_DATABASE
            database_name = MONGODB_DATABASE
        self.db = self.client[database_name]
        
        # Collections
        self.collection = self.db["document_chunked"]  # Main document chunks
        self.milvus_mapping_collection = self.db["milvus_chunks"]  # Vector ID mappings (renamed from Milvus_chunks)
        
        # Configuration
        self.chunk_size = int(os.getenv("DOCUMENT_CHUNK_SIZE_PAGES", 1))

        # Milvus configuration (from config/milvus_config.py)
        self.milvus_uri = get_milvus_uri()
        self.milvus_token = get_milvus_api_key()
        self.collection_name = self._collection_override or get_collection_name()
        
        # Initialize Milvus client (singleton - shared across all instances)
        # Token is optional for self-hosted Milvus, required for Zilliz Cloud
        is_cloud = not bool(os.getenv("MILVUS_URI"))
        if not self.milvus_uri:
            raise RuntimeError("Milvus URI not configured. Set MILVUS_URI (self-hosted) or ZILLIZ_CLOUD_URI (cloud).")
        if is_cloud and not self.milvus_token:
            raise RuntimeError("Zilliz Cloud API key not configured. Set MILVUS_TOKEN or ZILLIZ_CLOUD_API_KEY.")
        
        self.milvus_client = get_milvus_client()
        self.logger.info(f"🔧 Using singleton Milvus client for collection: {self.collection_name}")
        
        # Hybrid search configuration - always enabled
        self.enable_hybrid_search = is_hybrid_search_enabled()
        self.logger.info(f"🔀 Hybrid search (BM25 + Dense): {'Enabled' if self.enable_hybrid_search else 'Disabled'}")
        
        # Create indexes
        self._create_indexes()
    
    def _create_indexes(self):
        """Create MongoDB indexes for efficient querying"""
        self.logger.info("📋 MongoDB indexes will be created when first accessed")
        self._indexes_created = False
    
    async def create_indexes(self):
        """Public method to create indexes - called by startup sequence"""
        await self._ensure_indexes()
    
    async def generate_dense_embeddings_batch(self, chunks: List[str], topic: str) -> List[List[float]]:
        """
        Generate dense embeddings for a batch of text chunks using LLM with parallel processing.
        
        ✅ PARALLEL OPTIMIZATION: Processes up to 10 batches in parallel using asyncio.gather
        ✅ SERVER-SIDE BM25: This only generates dense embeddings
        Sparse vectors are auto-generated by Zilliz Cloud from the text field
        
        Strategy:
        - Split chunks into batches of 100 (LLM API limit)
        - Process up to 10 batches in parallel
        - Similar to OCR parallel batching for maximum speed
        
        Args:
            chunks: List of text chunks to embed
            topic: Topic/title for context (currently not used in embedding but kept for compatibility)
            
        Returns:
            List of embedding vectors (each vector is a list of floats)
        """
        try:
            total_chunks = len(chunks)
            if total_chunks == 0:
                return []
            
            # LLM batch API limit: 100 texts per request
            BATCH_SIZE = 100
            # Maximum parallel batches (similar to OCR processing)
            MAX_PARALLEL_BATCHES = 10
            
            # Single batch - process directly
            if total_chunks <= BATCH_SIZE:
                self.logger.debug(f"Generating {total_chunks} dense embeddings using LLM (single batch)")
                embeddings = await embed_texts_batch(chunks, task_type="RETRIEVAL_DOCUMENT")
                self.logger.debug(f"Successfully generated {len(embeddings)} dense embeddings")
                return embeddings
            
            # Multiple batches - process in parallel groups
            total_batches = (total_chunks + BATCH_SIZE - 1) // BATCH_SIZE
            self.logger.info(f"🚀 Parallel embedding generation with structured metadata headers: {total_chunks} chunks → {total_batches} batches (max {MAX_PARALLEL_BATCHES} parallel)")
            
            # Prepare all batches (chunks already have headers injected)
            batches = []
            for batch_idx in range(total_batches):
                start_idx = batch_idx * BATCH_SIZE
                end_idx = min(start_idx + BATCH_SIZE, total_chunks)
                batch_chunks = chunks[start_idx:end_idx]
                batches.append({
                    'batch_idx': batch_idx,
                    'chunks': batch_chunks,
                    'start_idx': start_idx,
                    'end_idx': end_idx
                })
            
            # Process batches in parallel groups
            all_embeddings = [None] * total_chunks  # Pre-allocate with correct size
            
            async def process_batch_group(batch_group):
                """Process a group of batches in parallel"""
                async def process_single_batch(batch_info):
                    try:
                        batch_embeddings = await embed_texts_batch(batch_info['chunks'], task_type="RETRIEVAL_DOCUMENT")
                        self.logger.debug(f"✅ Batch {batch_info['batch_idx']+1}/{total_batches} completed ({len(batch_embeddings)} embeddings)")
                        return batch_info['batch_idx'], batch_info['start_idx'], batch_embeddings
                    except Exception as e:
                        self.logger.error(f"❌ Batch {batch_info['batch_idx']+1}/{total_batches} failed: {e}")
                        raise
                
                # Process all batches in this group in parallel
                results = await asyncio.gather(
                    *[process_single_batch(batch_info) for batch_info in batch_group],
                    return_exceptions=False
                )
                return results
            
            # Split batches into groups of MAX_PARALLEL_BATCHES
            for group_start in range(0, total_batches, MAX_PARALLEL_BATCHES):
                group_end = min(group_start + MAX_PARALLEL_BATCHES, total_batches)
                batch_group = batches[group_start:group_end]
                
                self.logger.info(f"📦 Processing batch group {group_start//MAX_PARALLEL_BATCHES + 1}: batches {group_start+1}-{group_end} in parallel")
                
                # Process this group in parallel
                group_results = await process_batch_group(batch_group)
                
                # Merge results into all_embeddings at correct positions
                for batch_idx, start_idx, batch_embeddings in group_results:
                    for i, embedding in enumerate(batch_embeddings):
                        all_embeddings[start_idx + i] = embedding
            
            # Verify all embeddings were generated
            if None in all_embeddings:
                raise ValueError("Some embeddings failed to generate")
            
            self.logger.info(f"✅ Parallel embedding complete: {len(all_embeddings)} embeddings generated from {total_batches} batches")
            return all_embeddings
            
        except Exception as e:
            self.logger.error(f"Failed to generate dense embeddings: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Embedding generation failed: {str(e)}"
            )
    
    async def _ensure_indexes(self):
        """Ensure MongoDB indexes exist (called on first use)"""
        if hasattr(self, '_indexes_created') and self._indexes_created:
            return
        
        try:
            # Document chunks indexes
            await self.collection.create_index(
                [("document_id", 1), ("chunk_index", 1)], 
                unique=True,
                name="chunked_doc_chunk_unique_idx"
            )
            await self.collection.create_index("user_id", name="chunked_user_id_idx")
            await self.collection.create_index([("user_id", 1), ("folder_id", 1)], name="chunked_device_folder_idx")
            await self.collection.create_index("processing_status", name="chunked_processing_status_idx")
            await self.collection.create_index([("document_id", 1), ("start_page", 1)], name="chunked_doc_page_idx")
            await self.collection.create_index("file_type", name="chunked_file_type_idx")
            await self.collection.create_index("created_at", name="chunked_created_at_idx")
            
            # Milvus mapping indexes (renamed from Milvus_chunks)
            await self.milvus_mapping_collection.create_index(
                [("document_id", 1)], unique=True, name="milvus_document_id_unique_idx"
            )
            await self.milvus_mapping_collection.create_index([("user_id", 1)], name="milvus_user_id_idx")
            
            self._indexes_created = True
            self.logger.info("✅ MongoDB indexes created successfully")
            
        except Exception as idx_error:
            # Check for MongoDB error code 85 (IndexOptionsConflict) or duplicate index messages
            is_index_conflict = False
            if hasattr(idx_error, 'code') and idx_error.code == 85:
                is_index_conflict = True
            elif any(keyword in str(idx_error) for keyword in [
                "IndexOptionsConflict", "IndexKeySpecsConflict", "already exists", 
                "same name as the requested index"
            ]):
                is_index_conflict = True
            
            if is_index_conflict:
                self._indexes_created = True
                self.logger.info("📋 MongoDB indexes already exist or have conflicts - skipping creation")
            else:
                self.logger.warning(f"⚠️ Index creation warning: {idx_error}")

    # ==================== TEXT CHUNKING FUNCTIONS ====================
    
    # def safe_chunking(self, text: str, topic: str = "", doc_type: str = "document", source_info: Optional[Dict] = None) -> Tuple[List[str], List[dict]]:
    #     """
    #     Safe text chunking with memory limits
    #     Consolidated from document_manager.py
    #     """
    #     SAFE_LIMIT = 500_000  # chars
    #     if len(text) <= SAFE_LIMIT:
    #         return self.sentence_chunk(text, topic, doc_type, source_info)
        
    #     # For large text, split into rough paragraphs first
    #     paras = text.split('\n\n')
    #     all_chunks, all_metas = [], []
    #     for para in paras:
    #         if not para.strip():
    #             continue
    #         chunks, metas = self.sentence_chunk(para, topic, doc_type, source_info)
    #         all_chunks.extend(chunks)
    #         all_metas.extend(metas)
    #     return all_chunks, all_metas

    def simple_chunking_with_topic(self, text: str, topic: str = "", doc_type: str = "document", source_info: Optional[Dict] = None, include_topic_header: bool = False) -> Tuple[List[str], List[dict]]:
        """
        BREAKING CHANGE: Now uses unified 2048 token LlamaIndex chunking.
        This method is deprecated but kept for backward compatibility.
        All chunking now uses legal_document_chunking_with_llamaindex with 2048 tokens.
        
        Args:
            text: The text content to chunk
            topic: The topic/title of the content
            doc_type: Type of document (document, audio, video, etc.)
            source_info: Additional source information
            include_topic_header: Whether to prepend topic as header (True for audio/video, False for documents)
        """
        # BREAKING CHANGE: Always use LlamaIndex 2048 token chunking
        self.logger.info(f"⚠️ DEPRECATED: simple_chunking_with_topic redirecting to unified 2048 token chunking")
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # In async context, create task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return loop.run_in_executor(pool, self._sync_llamaindex_chunking, text, topic, doc_type, source_info, 2048, 300)
        else:
            # Sync context, run directly
            return loop.run_until_complete(self.legal_document_chunking_with_llamaindex(
                text=text, topic=topic, doc_type=doc_type, source_info=source_info,
                chunk_size=2048, chunk_overlap=300, user_id=None
            ))
    
    def _sync_llamaindex_chunking(self, text: str, topic: str, doc_type: str, source_info: Optional[Dict], chunk_size: int, chunk_overlap: int) -> Tuple[List[str], List[dict]]:
        """Synchronous wrapper for LlamaIndex chunking"""
        import asyncio
        return asyncio.run(self.legal_document_chunking_with_llamaindex(
            text=text, topic=topic, doc_type=doc_type, source_info=source_info,
            chunk_size=chunk_size, chunk_overlap=chunk_overlap, user_id=None
        ))
    
    def _simple_chunking_legacy(self, text: str, topic: str = "", doc_type: str = "document", source_info: Optional[Dict] = None, include_topic_header: bool = False) -> Tuple[List[str], List[dict]]:
        """
        LEGACY: Old character-based chunking (1000 chars).
        Kept for emergency rollback only. DO NOT USE.
        """
        max_chunk_size = 1000  # characters
        
        # Enhanced sentence splitting that handles multiple sentence endings
        import re
        sentence_endings = r'[.!?]+\s+'
        sentences = re.split(sentence_endings, text.strip())
        
        # Remove empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        
        chunks = []
        metas = []
        current_chunk = ""
        chunk_index = 0
        
        for i, sentence in enumerate(sentences):
            # Add appropriate punctuation back (except for last sentence)
            if i < len(sentences) - 1:
                sentence_with_punct = sentence + ". "
            else:
                sentence_with_punct = sentence
            
            # Check if adding this sentence would exceed the limit
            test_chunk = current_chunk + sentence_with_punct
            
            if len(test_chunk) > max_chunk_size and current_chunk:
                # Save current chunk (respects sentence boundaries)
                # Prepend topic as header only for audio/video content for semantic search
                if include_topic_header and topic:
                    chunk_with_header = f"Topic: {topic}\n\n{current_chunk.strip()}"
                else:
                    chunk_with_header = current_chunk.strip()
                chunks.append(chunk_with_header)
                
                # Simplified metadata - let LLM extract citations from content
                chunk_meta = {
                    'chunk_index': chunk_index,
                    'document_type': doc_type,
                    'topic_or_filename': topic,
                    # Remove estimated page/paragraph numbers - let LLM extract from content
                }
                
                # Add source_info if provided
                if source_info:
                    chunk_meta.update(source_info)
                
                metas.append(chunk_meta)
                
                # Check if current sentence is too long for a single chunk
                if len(sentence_with_punct) > max_chunk_size:
                    # Fall back to word-level chunking for oversized sentences
                    words = sentence_with_punct.split()
                    word_chunk = ""
                    
                    for word in words:
                        test_word_chunk = word_chunk + (" " + word if word_chunk else word)
                        if len(test_word_chunk) > max_chunk_size and word_chunk:
                            # Save word chunk with topic header only for audio/video
                            if include_topic_header and topic:
                                chunk_with_header = f"Topic: {topic}\n\n{word_chunk.strip()}"
                            else:
                                chunk_with_header = word_chunk.strip()
                            chunks.append(chunk_with_header)
                            chunk_meta = {
                                'chunk_index': chunk_index,
                                'document_type': doc_type,
                                'topic_or_filename': topic,
                            }
                            if source_info:
                                chunk_meta.update(source_info)
                            metas.append(chunk_meta)
                            chunk_index += 1
                            word_chunk = word
                        else:
                            word_chunk = test_word_chunk
                    
                    current_chunk = word_chunk
                else:
                    current_chunk = sentence_with_punct  # Start new chunk with current sentence
                
                chunk_index += 1
            else:
                # Add sentence to current chunk
                current_chunk = test_chunk
        
        # Add the last chunk if it has content
        if current_chunk.strip():
            # Prepend topic as header only for audio/video content for semantic search
            if include_topic_header and topic:
                chunk_with_header = f"Topic: {topic}\n\n{current_chunk.strip()}"
            else:
                chunk_with_header = current_chunk.strip()
            chunks.append(chunk_with_header)
            chunk_meta = {
                'chunk_index': chunk_index,
                'document_type': doc_type,
                'topic_or_filename': topic,
            }
            
            # Add source_info if provided
            if source_info:
                chunk_meta.update(source_info)
                
            metas.append(chunk_meta)
        
        # Update total chunks in all metadata
        for meta in metas:
            meta['total_chunks'] = len(chunks)
        
        self.logger.info(f"✅ Sentence-aware chunking: {len(text)} chars → {len(chunks)} sentence-boundary chunks")
        return chunks, metas

    async def legal_document_chunking_with_llamaindex(
        self,
        text: str,
        topic: str = "",
        doc_type: str = "document",
        source_info: Optional[Dict] = None,
        chunk_size: int = 2048,
        chunk_overlap: int = 300,
        user_id: Optional[str] = None
    ) -> Tuple[List[str], List[dict]]:
        """
        Advanced document chunking using LlamaIndex with structure awareness.
        
        Features:
        - Preserves citations (case law, statutes, regulations)
        - Maintains section hierarchy and numbering
        - Handles abbreviations correctly
        - Sentence-based chunking optimized for structured documents
        - Hierarchical structure preservation
        
        Args:
            text: The document text to chunk
            topic: Document title/case name
            doc_type: Type of document (pdf, docx, etc.)
            source_info: Additional metadata
            chunk_size: Target chunk size in tokens (default: 2048 - increased for better context)
            chunk_overlap: Overlap between chunks to preserve context (default: 300 - increased for reasoning continuity)
            user_id: Optional user ID for usage tracking
            
        Returns:
            Tuple of (chunks, metadata_list)
        """
        if not LLAMAINDEX_AVAILABLE:
            self.logger.warning("⚠️ LlamaIndex not available, falling back to simple chunking")
            return self.simple_chunking_with_topic(text, topic, doc_type, source_info)
        
        try:
            self.logger.info(f"🏛️ Using LlamaIndex document chunking: {len(text)} chars")
            
            # Preprocess text to preserve structure
            processed_text = self._preprocess_legal_text(text)
            
            # Create LlamaIndex document
            llama_doc = LlamaDocument(
                text=processed_text,
                metadata={
                    "topic_or_filename": topic,
                    "document_type": doc_type,
                }
            )
            
            # Use sentence-based splitting with structure-aware parameters
            # Optimized for structured documents with 2048 token chunks
            self.logger.info("📝 Using sentence splitting for document")
            node_parser = SentenceSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                paragraph_separator="\n\n",
                secondary_chunking_regex=r"[.!?;]\s+",  # Sentence endings
            )
            self.logger.info(f"📝 Sentence splitter configured: chunk_size={chunk_size} tokens, overlap={chunk_overlap} tokens")
            
            # Parse document into nodes
            nodes = node_parser.get_nodes_from_documents([llama_doc])
            
            # Convert nodes to chunks and metadata
            chunks = []
            metas = []
            
            for idx, node in enumerate(nodes):
                chunk_text = node.get_content()
                chunks.append(chunk_text)
                
                # Build chunk metadata
                chunk_meta = {
                    'chunk_index': idx,
                    'document_type': doc_type,
                    'topic_or_filename': topic,
                    'chunk_method': 'llamaindex_structured',
                    'node_id': node.node_id,
                }
                
                # Add source_info if provided
                if source_info:
                    chunk_meta.update(source_info)
                
                # Still extract citations for all chunks (fast regex)
                citations = self._extract_legal_citations(chunk_text)
                if citations:
                    chunk_meta['legal_citations'] = citations
                
                metas.append(chunk_meta)
            
            # Update total chunks
            for meta in metas:
                meta['total_chunks'] = len(chunks)
            
            self.logger.info(
                f"✅ LlamaIndex legal chunking complete: {len(text)} chars → "
                f"{len(chunks)} sentence-based chunks"
            )
            
            return chunks, metas
            
        except Exception as e:
            self.logger.error(f"❌ LlamaIndex chunking failed: {e}, falling back to simple chunking")
            return self.simple_chunking_with_topic(text, topic, doc_type, source_info)

    def _preprocess_legal_text(self, text: str) -> str:
        """
        Preprocess legal text to preserve important structure.
        
        - Protects common legal abbreviations (Indian & International)
        - Preserves citation formats
        - Maintains section numbering
        - Handles Indian Supreme Court judgment format
        """
        # Protect common legal abbreviations from sentence splitting
        legal_abbreviations = {
            # Indian Legal Abbreviations
            r'\bv\.': 'v_',  # versus
            r'\bVs\.': 'Vs_',
            r'\bSec\.': 'Sec_',
            r'\bArt\.': 'Art_',
            r'\bCl\.': 'Cl_',  # Clause
            r'\bPara\.': 'Para_',
            r'\bS\.': 'S_',  # Section (short form)
            r'\bSs\.': 'Ss_',  # Sections
            r'\bCh\.': 'Ch_',  # Chapter
            r'\bNo\.': 'No_',
            r'\bNos\.': 'Nos_',  # Numbers (plural)
            r'\bInc\.': 'Inc_',
            r'\bPvt\.': 'Pvt_',  # Private
            r'\bLtd\.': 'Ltd_',
            r'\bCo\.': 'Co_',
            r'\bR\.': 'R_',  # Respondent/Rule
            r'\bO\.': 'O_',  # Order
            r'\bO\.S\.': 'O_S_',  # Original Suit
            r'\bI\.A\.': 'I_A_',  # Interlocutory Application
            r'\bSch\.': 'Sch_',  # Schedule
            r'\bGovt\.': 'Govt_',
            r'\bDept\.': 'Dept_',
            r'\bMin\.': 'Min_',  # Ministry/Minister
            r'\bJ\.': 'J_',  # Justice/Judge
            r'\bCJI\.': 'CJI_',  # Chief Justice of India
            r'\bSri\.': 'Sri_',  # Honorific
            r'\bSmt\.': 'Smt_',  # Honorific for women
            r'\bDr\.': 'Dr_',
            r'\bMr\.': 'Mr_',
            r'\bMrs\.': 'Mrs_',
            r'\bMs\.': 'Ms_',
            r'\bM/s': 'M_s',  # Messrs
            
            # Indian Case Citations
            r'\bAIR': 'AIR_',  # All India Reporter
            r'\bSCC': 'SCC_',  # Supreme Court Cases
            r'\bSCR': 'SCR_',  # Supreme Court Reporter
            r'\bINSC': 'INSC_',  # Indian Supreme Court
            
            # US Legal Abbreviations (for reference/international cases)
            r'\bU\.S\.': 'U_S_',
            r'\bCir\.': 'Cir_',
            r'\bF\.Supp\.': 'F_Supp_',
            r'\bF\.2d': 'F_2d',
            r'\bF\.3d': 'F_3d',
            r'\bCal\.': 'Cal_',
            r'\bN\.Y\.': 'N_Y_',
            r'\bP\.': 'P_',  # Page
            
            # Common abbreviations
            r'\bId\.': 'Id_',
            r'\bIbid\.': 'Ibid_',
            r'\bCf\.': 'Cf_',
            r'\bEg\.': 'Eg_',
            r'\be\.g\.': 'e_g_',
            r'\bi\.e\.': 'i_e_',
            r'\bViz\.': 'Viz_',
            r'\bEtc\.': 'Etc_',
            r'\bp\.a\.': 'p_a_',  # per annum
        }
        
        processed = text
        for pattern, replacement in legal_abbreviations.items():
            processed = re.sub(pattern, replacement, processed)
        
        return processed

    def _restore_legal_abbreviations(self, text: str) -> str:
        """Restore protected legal abbreviations to original format."""
        restorations = {
            # Indian Legal Abbreviations
            'v_': 'v.',
            'Vs_': 'Vs.',
            'Sec_': 'Sec.',
            'Art_': 'Art.',
            'Cl_': 'Cl.',
            'Para_': 'Para.',
            'S_': 'S.',
            'Ss_': 'Ss.',
            'Ch_': 'Ch.',
            'No_': 'No.',
            'Nos_': 'Nos.',
            'Inc_': 'Inc.',
            'Pvt_': 'Pvt.',
            'Ltd_': 'Ltd.',
            'Co_': 'Co.',
            'R_': 'R.',
            'O_': 'O.',
            'O_S_': 'O.S.',
            'I_A_': 'I.A.',
            'Sch_': 'Sch.',
            'Govt_': 'Govt.',
            'Dept_': 'Dept.',
            'Min_': 'Min.',
            'J_': 'J.',
            'CJI_': 'CJI.',
            'Sri_': 'Sri.',
            'Smt_': 'Smt.',
            'Dr_': 'Dr.',
            'Mr_': 'Mr.',
            'Mrs_': 'Mrs.',
            'Ms_': 'Ms.',
            'M_s': 'M/s',
            
            # Indian Case Citations
            'AIR_': 'AIR',
            'SCC_': 'SCC',
            'SCR_': 'SCR',
            'INSC_': 'INSC',
            
            # US Legal Abbreviations
            'U_S_': 'U.S.',
            'Cir_': 'Cir.',
            'F_Supp_': 'F.Supp.',
            'F_2d': 'F.2d',
            'F_3d': 'F.3d',
            'Cal_': 'Cal.',
            'N_Y_': 'N.Y.',
            'P_': 'P.',
            
            # Common abbreviations
            'Id_': 'Id.',
            'Ibid_': 'Ibid.',
            'Cf_': 'Cf.',
            'Eg_': 'Eg.',
            'e_g_': 'e.g.',
            'i_e_': 'i.e.',
            'Viz_': 'Viz.',
            'Etc_': 'Etc.',
            'p_a_': 'p.a.',
        }
        
        restored = text
        for placeholder, original in restorations.items():
            restored = restored.replace(placeholder, original)
        
        return restored

    def _extract_legal_citations(self, text: str) -> List[str]:
        """
        Extract legal citations from text.
        
        Indian Citation Patterns:
        - Reporter Citations: "2024 INSC 859", "AIR 2023 SC 123", "2021 SCC 456"
        - Case Numbers: "Civil Appeal Nos. 7709-7710/2023"
        - Statutory: "Section 37 of the Indian Partnership Act, 1932"
        - Constitutional: "Article 14 of the Constitution"
        - Order References: "Order XX Rule 15 of the Code of Civil Procedure, 1908"
        
        International Citation Patterns:
        - Case citations: "Smith v. Jones, 123 U.S. 456"
        - Statutes: "42 U.S.C. § 1983"
        - Federal Rules: "Fed. R. Civ. P. 12(b)(6)"
        """
        citations = []
        
        # Indian Supreme Court citation patterns
        indian_patterns = [
            # Reporter citations: "2024 INSC 859", "AIR 2023 SC 123"
            r'\d{4}\s+(?:INSC|AIR|SCC|SCR)\s+(?:SC\s+)?\d+',
            
            # Case numbers: "Civil Appeal Nos. 7709-7710/2023"
            r'(?:Civil|Criminal|Special|Writ|Transfer)\s+(?:Appeal|Petition|Suit)\s+No[s]?\.?\s*[\d\-]+\s*(?:of|OF|/)\s*\d{4}',
            
            # Section references with Act name
            r'Section\s+\d+[A-Z]?(?:\(\d+\))?(?:\s+(?:read with|r/w|and)\s+Section\s+\d+[A-Z]?(?:\(\d+\))?)?\s+of\s+(?:the\s+)?[A-Za-z\s,]+(?:Act|Code)\s*,?\s*\d{4}',
            
            # Article references
            r'Article\s+\d+[A-Z]?(?:\(\d+\))?\s+of\s+(?:the\s+)?Constitution',
            
            # Order/Rule references: "Order XX Rule 15 of the Code of Civil Procedure"
            r'Order\s+[IVXLCDM]+\s+Rule\s+\d+[A-Z]?\s+of\s+(?:the\s+)?[A-Za-z\s,]+(?:Code|Act|Rules)',
            
            # Short form citations: "Section 302 IPC", "Article 21"
            r'(?:Section|Sec\.|S\.)\s+\d+[A-Z]?(?:\(\d+\))?\s+(?:IPC|CrPC|CPC)',
            r'Article\s+\d+[A-Z]?(?:\(\d+\))?',
            
            # Judgment/Order references: "judgment dated 19.11.2019"
            r'(?:judgment|judgement|order|decree)\s+(?:and\s+order\s+)?dated\s+\d{1,2}\.\d{1,2}\.\d{4}',
            
            # I.A. (Interlocutory Application) references
            r'I\.A\.\s*No\.\s*\d+\s+of\s+\d{4}',
            
            # Original Suit references
            r'(?:Original|O\.S\.)\s+Suit\s+No\.\s*\d+\s+of\s+\d{4}',
        ]
        
        # International citation patterns
        international_patterns = [
            # U.S. case citations: "Smith v. Jones, 123 U.S. 456 (1990)"
            r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+v\.\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s+\d+\s+[A-Z][a-z.]+\s+\d+',
            
            # Federal statute: "42 U.S.C. § 1983"
            r'\d+\s+U\.S\.C\.\s+§\s+\d+',
            
            # Federal Rules: "Fed. R. Civ. P. 12(b)(6)"
            r'Fed\.\s+R\.\s+(?:Civ|Crim)\.\s+P\.\s+\d+(?:\([a-z]\)(?:\(\d+\))?)?',
            
            # C.F.R. regulations
            r'\d+\s+C\.F\.R\.\s+§\s+[\d.]+(?:-\d+)?',
        ]
        
        # Combine all patterns
        all_patterns = indian_patterns + international_patterns
        
        for pattern in all_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                citation = match.group(0).strip()
                if citation not in citations:
                    citations.append(citation)
        
        return citations

    def _extract_section_info(self, text: str) -> Dict[str, Any]:
        """
        Extract section numbers and headings from legal text.
        Supports both Indian and International legal document structures.
        
        Indian Legal Document Patterns:
        - "Section 37 of the Indian Partnership Act"
        - "Article 14 of the Constitution"
        - Case Numbers: "Civil Appeal Nos.7709-7710 OF 2023"
        - Court Citations: "2024 INSC 859"
        - Party Names: "M/S CRYSTAL TRANSPORT PRIVATE LIMITED & ANR. ...APPELLANT(S)"
        
        International Legal Patterns:
        - "Section 1.2.3"
        - "Article IV"
        - "§ 42"
        - "PART A - GENERAL PROVISIONS"
        """
        section_info = {}
        
        # Indian Case Number Pattern
        # Pattern: "Civil Appeal No(s). XXXX/YYYY" or "CIVIL APPEAL NO(S) 4594-4595 OF 2017"
        case_number_patterns = [
            r'(?:CIVIL|CRIMINAL|SPECIAL|WRIT|TRANSFER|Civil|Criminal|Special|Writ|Transfer)\s+(?:APPEAL|PETITION|SUIT|Appeal|Petition|Suit)\s+NO?\(?[Ss]?\)?\.?\s*[\d\-]+\s*(?:of|OF)\s*\d{4}',
            r'\d{4}\s+INSC\s+\d+',  # Supreme Court citation
            r'\d{4}\s+(?:AIR|SCC|SCR)\s+\d+',  # Reporter citations
        ]
        
        for pattern in case_number_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                section_info['case_number'] = match.group(0)
                break
        
        # Extract Party Names (Indian Supreme Court format)
        # Pattern: "PARTY NAME ...APPELLANT(S)" or "… Appellant(s)"
        # Example 1: "M/S CRYSTAL TRANSPORT PRIVATE LIMITED & ANR. ...APPELLANT(S)"
        # Example 2: "Sunaina Sharma & Ors. … Appellant(s)"
        appellant_pattern = r'([A-Z][A-Za-z\s&./,\-()]+?)\s*(?:\.{2,}|…)\s*Appellant\(s\)'
        appellant_match = re.search(appellant_pattern, text, re.IGNORECASE)
        if appellant_match:
            appellant_name = appellant_match.group(1).strip()
            # Clean up the name (remove extra spaces, trailing &, etc.)
            appellant_name = re.sub(r'\s+', ' ', appellant_name)
            appellant_name = appellant_name.rstrip('& .').strip()
            section_info['appellant'] = appellant_name
        
        # Respondent pattern - make sure it doesn't capture the Vs. line
        # Match only after "Vs." or "VERSUS" line
        respondent_pattern = r'(?:Vs\.?|VERSUS|V\.)\s+([A-Z][A-Za-z\s&./,\-()]+?)\s*(?:\.{2,}|…\.?)\s*Respondent\(s\)'
        respondent_match = re.search(respondent_pattern, text, re.DOTALL | re.IGNORECASE)
        if respondent_match:
            respondent_name = respondent_match.group(1).strip()
            # Clean up the name
            respondent_name = re.sub(r'\s+', ' ', respondent_name)
            respondent_name = respondent_name.rstrip('& .').strip()
            section_info['respondent'] = respondent_name
        
        # Alternative pattern for case title format
        # "PARTY1 ...Appellant(s) Vs./VERSUS PARTY2 ...Respondent(s)"
        full_pattern = r'([A-Z][A-Za-z\s&./,\-()]+?)\s*(?:\.{2,}|…)?\s*Appellant\(s\)\s+(?:Vs\.?|VERSUS|V\.)\s+([A-Z][A-Za-z\s&./,\-()]+?)\s*(?:\.{2,}|…\.?)?\s*Respondent\(s\)'
        full_match = re.search(full_pattern, text, re.DOTALL | re.IGNORECASE)
        if full_match:
            # Override with better match
            section_info['appellant'] = re.sub(r'\s+', ' ', full_match.group(1).strip().rstrip('& .').strip())
            section_info['respondent'] = re.sub(r'\s+', ' ', full_match.group(2).strip().rstrip('& .').strip())
        
        # Extract Judge Name(s)
        # Pattern: "NAME, J." or "NAME, CJI." - search entire document, especially at the end
        judge_pattern = r'([A-Z][A-Za-z\s.]+?),\s+(?:J\.|CJI\.)'
        judge_matches = re.finditer(judge_pattern, text)  # Search entire text
        judges = []
        for match in judge_matches:
            judge_name = match.group(1).strip()
            # Clean up judge name
            judge_name = re.sub(r'\s+', ' ', judge_name)
            if len(judge_name) > 5 and judge_name not in judges:  # Avoid false positives
                judges.append(judge_name)
        if judges:
            section_info['judges'] = judges
        
        # Extract Court Name
        # Pattern: "IN THE SUPREME COURT OF INDIA" or "High Court of Judicature at..."
        court_patterns = [
            r'IN THE SUPREME COURT OF INDIA',
            r'SUPREME COURT OF INDIA',
            r'High Court of Judicature at ([A-Za-z\s]+)',
            r'HIGH COURT OF ([A-Z\s]+)',
        ]
        
        for pattern in court_patterns:
            court_match = re.search(pattern, text[:1000], re.IGNORECASE)
            if court_match:
                section_info['court'] = court_match.group(0).strip()
                break
        
        # Extract Jurisdiction (if mentioned)
        jurisdiction_pattern = r'(CIVIL|CRIMINAL|ORIGINAL|APPELLATE)\s+(?:APPELLATE\s+)?JURISDICTION'
        jurisdiction_match = re.search(jurisdiction_pattern, text[:1000], re.IGNORECASE)
        if jurisdiction_match:
            section_info['jurisdiction'] = jurisdiction_match.group(0).strip()
        
        # Indian Section Reference Pattern
        # Pattern: "Section 37 of the Indian Partnership Act" or "S. 42 of IPC"
        indian_section_patterns = [
            r'(?:Section|Sec\.|S\.)\s+(\d+[A-Z]?(?:\(\d+\))?)\s+(?:of\s+)?(?:the\s+)?([A-Za-z\s,]+(?:Act|Code|Constitution))',
            r'(?:Section|Sec\.|S\.)\s+(\d+[A-Z]?)',
        ]
        
        for pattern in indian_section_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if len(match.groups()) >= 2:
                    section_info['section_number'] = match.group(1)
                    section_info['section_statute'] = match.group(2).strip()
                else:
                    section_info['section_number'] = match.group(1)
                break
        
        # Article Reference (Constitution)
        article_pattern = r'Article\s+(\d+[A-Z]?(?:\(\d+\))?)\s+(?:of\s+)?(?:the\s+)?Constitution'
        article_match = re.search(article_pattern, text, re.IGNORECASE)
        if article_match:
            section_info['article_number'] = article_match.group(1)
            section_info['article_source'] = 'Constitution of India'
        
        # International Section number patterns
        international_section_patterns = [
            r'Section\s+([\d.]+)',
            r'§\s*([\d.]+)',
            r'Article\s+([IVXLCDM]+)',
            r'PART\s+([A-Z])',
        ]
        
        if 'section_number' not in section_info:
            for pattern in international_section_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    section_info['section_number'] = match.group(1)
                    break
        
        # Extract headings (ALL CAPS lines or specific Indian judgment headings)
        # Indian judgment headings: FACTUAL MATRIX, SUBMISSIONS, ANALYSIS, CONCLUSION
        indian_heading_patterns = [
            r'^(FACTUAL MATRIX|SUBMISSIONS?|ANALYSIS|CONCLUSION|FINDINGS?|ISSUES?|JUDGMENT|JUDGEMENT|ORDER|FACTS?)\s*$',
            r'^([A-Z][A-Z\s]{10,})\s*$'  # Generic ALL CAPS heading
        ]
        
        for pattern in indian_heading_patterns:
            heading_match = re.search(pattern, text, re.MULTILINE)
            if heading_match:
                section_info['section_heading'] = heading_match.group(1).strip()
                break
        
        # ✨ LEGISLATURE ACT METADATA EXTRACTION (Union Acts, State Acts)
        # Pattern for Act Title: "The [Name] Act, [Year]"
        # Example: "The Protection of Interests in Aircraft Objects Act, 2025"
        act_title_patterns = [
            r'The\s+([A-Za-z\s,\(\)]+?)\s+Act\s*,\s*(\d{4})',  # "The ... Act, 2025"
            r'([A-Za-z\s,\(\)]+?)\s+Act\s*,\s*(\d{4})',  # "... Act, 2025" (without "The")
            r'The\s+([A-Za-z\s,\(\)]+?)\s+Act\s+of\s+(\d{4})',  # "The ... Act of 2025"
        ]
        
        for pattern in act_title_patterns:
            match = re.search(pattern, text[:2000], re.IGNORECASE)
            if match:
                section_info['act_title'] = f"The {match.group(1).strip()} Act"
                section_info['act_year'] = match.group(2)
                break
        
        # Pattern for Act Number: "17 of 2025" or "No. 17 of 2025"
        # Example: "MINISTRYOFCIVILAVIATION 17 of 2025"
        act_number_patterns = [
            r'(?:No\.\s*)?(\d+)\s+of\s+(\d{4})',  # "17 of 2025" or "No. 17 of 2025"
            r'Act\s+No\.\s*(\d+)\s*,?\s*(\d{4})',  # "Act No. 17, 2025"
        ]
        
        for pattern in act_number_patterns:
            match = re.search(pattern, text[:2000], re.IGNORECASE)
            if match:
                section_info['act_number'] = f"{match.group(1)} of {match.group(2)}"
                if not section_info.get('act_year'):
                    section_info['act_year'] = match.group(2)
                break
        
        # Pattern for Ministry/Department
        # Example: "MINISTRYOFCIVILAVIATION" or "MINISTRY OF CIVIL AVIATION"
        ministry_patterns = [
            r'MINISTRY\s*OF\s*([A-Z\s]+?)(?:\s+\d+|\s+Act|\n)',  # "MINISTRY OF CIVIL AVIATION"
            r'MINISTRYOF([A-Z]+)',  # "MINISTRYOFCIVILAVIATION" (no spaces)
            r'Department\s+of\s+([A-Za-z\s]+?)(?:\s+\d+|\s+Act|\n)',  # "Department of ..."
        ]
        
        for pattern in ministry_patterns:
            match = re.search(pattern, text[:2000])
            if match:
                ministry_name = match.group(1).strip()
                # Add spaces between concatenated words (e.g., "CIVILAVIATION" → "CIVIL AVIATION")
                ministry_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', ministry_name)
                section_info['ministry'] = f"Ministry of {ministry_name.title()}"
                break
        
        # Pattern for Enacting Authority
        # Example: "UNION OF INDIA" or "STATE OF [STATE]" or "Parliament"
        authority_patterns = [
            r'(UNION OF INDIA)',
            r'(STATE OF [A-Z\s]+)',
            r'BE it enacted by (Parliament)',
            r'enacted by (the [A-Za-z\s]+ Legislature)',
        ]
        
        for pattern in authority_patterns:
            match = re.search(pattern, text[:2000], re.IGNORECASE)
            if match:
                section_info['enacting_authority'] = match.group(1).strip()
                break
        
        # Pattern for Gazette Reference
        # Example: "Published in Gazette of India Extraordinary 17 on 16 April 2025"
        gazette_patterns = [
            r'Published in (Gazette of India[^0-9]+\d+)',  # "Gazette of India Extraordinary 17"
            r'Gazette of India[^0-9]+(Part\s+[IVX]+[^0-9]+\d+)',  # "Part II Section 3 No. 17"
        ]
        
        for pattern in gazette_patterns:
            match = re.search(pattern, text[:2000], re.IGNORECASE)
            if match:
                section_info['gazette_reference'] = match.group(1).strip()
                break
        
        # Pattern for Gazette Date
        # Example: "Published in Gazette of India Extraordinary 17 on 16 April 2025"
        gazette_date_pattern = r'on\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})'
        gazette_date_match = re.search(gazette_date_pattern, text[:2000], re.IGNORECASE)
        if gazette_date_match:
            section_info['gazette_date'] = gazette_date_match.group(1).strip()
        
        # Pattern for Commencement Date
        # Example: "Commenced on 16 April 2025" or "come into force on such date"
        commencement_patterns = [
            r'Commenced on\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})',
            r'come into force on\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})',
            r'shall come into force on such date',  # Indicates date to be notified
        ]
        
        for pattern in commencement_patterns:
            match = re.search(pattern, text[:2000], re.IGNORECASE)
            if match:
                if match.groups():
                    section_info['commencement_date'] = match.group(1).strip()
                else:
                    section_info['commencement_date'] = "Date to be notified"
                break
        
        # Pattern for State/Territory (for state legislation)
        # Example: "State of Maharashtra", "Jammu and Kashmir"
        state_patterns = [
            r'State of ([A-Za-z\s]+)',
            r'in the State of ([A-Za-z\s]+)',
        ]
        
        for pattern in state_patterns:
            match = re.search(pattern, text[:1000], re.IGNORECASE)
            if match:
                section_info['state'] = match.group(1).strip()
                break
        
        # Determine Act Type (Union/Central vs State)
        if section_info.get('enacting_authority'):
            if 'UNION OF INDIA' in section_info['enacting_authority'].upper() or \
               'PARLIAMENT' in section_info['enacting_authority'].upper():
                section_info['act_type'] = 'Union Act (Central)'
            elif 'STATE' in section_info['enacting_authority'].upper():
                section_info['act_type'] = 'State Act'
        
        return section_info

    async def intelligent_chunking(
        self,
        text: str,
        topic: str = "",
        doc_type: str = "document",
        source_info: Optional[Dict] = None,
        include_topic_header: bool = False,
        user_id: Optional[str] = None
    ) -> Tuple[List[str], List[dict]]:
        """
        Intelligently choose the best chunking strategy based on document type and content.
        
        Decision logic:
        1. Structured documents (contains citations/structure) → LlamaIndex structured chunking
        2. Audio/video transcripts → Simple chunking with topic header
        3. General documents → Simple sentence-aware chunking
        
        Args:
            text: Document text
            topic: Document title/name
            doc_type: File type (pdf, docx, etc.)
            source_info: Additional metadata
            include_topic_header: Whether to prepend topic header
            user_id: Optional user ID for usage tracking
            
        Returns:
            Tuple of (chunks, metadata_list)
        """
        # LEGAL DOCUMENT DETECTION DISABLED - No longer checking document type
        # is_legal = self._is_legal_document(text, topic)
        # Always use simple chunking regardless of document type
        is_legal = False
        
        if is_legal and LLAMAINDEX_AVAILABLE:
            self.logger.info(f"🏛️ Detected structured document, using LlamaIndex structured chunking")
            
            # Using optimized sentence splitting with 2048 token chunks
            chunks, metas = await self.legal_document_chunking_with_llamaindex(
                text=text,
                topic=topic,
                doc_type=doc_type,
                source_info=source_info,
                chunk_size=2048,  # Increased from 1024 to 2048 tokens for better context preservation
                chunk_overlap=300,  # Increased from 200 to 300 tokens for better reasoning continuity
                user_id=user_id
            )
            
            # Restore legal abbreviations in chunks
            chunks = [self._restore_legal_abbreviations(chunk) for chunk in chunks]
            
            return chunks, metas
        else:
            # Fall back to simple chunking for non-legal documents
            self.logger.info(f"📄 Using standard chunking for general document")
            return await self.simple_chunking_with_topic(
                text=text,
                topic=topic,
                doc_type=doc_type,
                source_info=source_info,
                include_topic_header=include_topic_header
            )

    def _is_legal_document(self, text: str, topic: str = "") -> bool:
        """
        Detect if a document is a legal document based on content and title.
        Covers ALL types of legal documents:
        
        1. Court Documents (Indian & International):
           - Supreme Court/High Court judgments
           - Lower court orders and decrees
           
        2. Legal Pleadings & Filings:
           - Complaints, petitions, writs
           - Appeals, revisions, applications
           - Affidavits, counter-affidavits
           
        3. Client-Lawyer Documents:
           - Legal opinions and advice
           - Client instructions/briefs
           - Case summaries and research memos
           
        4. Legal Drafts:
           - Contracts, agreements, deeds
           - Legal notices, demands
           - Powers of attorney, wills
           - Commercial documents (MOUs, NDAs)
           
        5. Statutory Documents:
           - Acts, regulations, rules
           - Amendments, notifications
           - Government orders
        """
        # Check title for legal keywords (Comprehensive list)
        legal_title_keywords = [
            # Indian Court Documents
            'judgment', 'judgement', 'order', 'decree', 'award',
            'appeal', 'revision', 'review', 'suo motu', 'reference',
            
            # Indian Legal Filings
            'petition', 'writ', 'complaint', 'plaint', 'written statement',
            'affidavit', 'vakalatnama', 'counter', 'rejoinder', 'reply',
            'application', 'ia', 'interlocutory', 'caveat',
            'criminal', 'civil', 'family', 'commercial', 'arbitration',
            
            # Indian Courts & Authorities
            'supreme court', 'high court', 'district court', 'sessions',
            'magistrate', 'tribunal', 'commission', 'authority',
            
            # Indian Legal Codes
            'ipc', 'crpc', 'cpc', 'evidence act', 'constitution',
            'companies act', 'income tax', 'gst', 'fema', 'sebi',
            
            # Client-Lawyer Documents
            'legal opinion', 'legal advice', 'legal notice', 'demand letter',
            'case study', 'case analysis', 'research memo', 'brief',
            'instructions', 'consultation', 'retainer',
            
            # Legal Drafts
            'contract', 'agreement', 'mou', 'memorandum of understanding',
            'nda', 'non-disclosure', 'sale deed', 'lease deed',
            'partnership deed', 'power of attorney', 'poa',
            'will', 'testament', 'trust deed', 'indemnity',
            'guarantee', 'license', 'franchise', 'employment agreement',
            'service agreement', 'vendor agreement', 'loan agreement',
            
            # Statutory Documents
            'act', 'statute', 'regulation', 'rule', 'notification',
            'ordinance', 'amendment', 'bill', 'code', 'law',
            
            # International Legal
            'motion', 'pleading', 'memorandum', 'decision', 'ruling',
            'opinion', 'brief', 'discovery', 'deposition'
        ]
        
        topic_lower = topic.lower()
        if any(keyword in topic_lower for keyword in legal_title_keywords):
            return True
        
        # Check content for legal patterns (Comprehensive)
        legal_indicators = [
            # Indian Case Law & Citations
            r'\b[vV]s?\.\b',  # versus
            r'\bv/s\b',  # versus alternate
            r'\bSection\s+\d+',  # Section references
            r'\bS\.\s*\d+',  # Short section reference
            r'\bSec\.\s*\d+',
            r'\bArticle\s+\d+',  # Constitutional articles
            r'\bArt\.\s*\d+',
            r'\bAIR\s+\d{4}',  # All India Reporter
            r'\bSCC\s+\d{4}',  # Supreme Court Cases
            r'\bSCR\s+\d{4}',  # Supreme Court Reporter
            r'\bINSC\b',  # Indian Supreme Court
            
            # Indian Legal Codes
            r'\bIPC\b',  # Indian Penal Code
            r'\bCrPC\b',  # Criminal Procedure Code
            r'\bCPC\b',  # Civil Procedure Code
            r'\bEvidence Act\b',
            r'\bLimitation Act\b',
            r'\bNegotiable Instruments Act\b',
            
            # Legal Parties
            r'\bpetitioner\b',
            r'\brespondent\b',
            r'\bappellant\b',
            r'\bappellee\b',
            r'\baccused\b',
            r'\bcomplainant\b',
            r'\bplaintiff\b',
            r'\bdefendant\b',
            r'\bdefence\b',
            r'\bprosecution\b',
            
            # Legal Proceedings
            r'\bwrit petition\b',
            r'\bhabeas corpus\b',
            r'\bmandamus\b',
            r'\bcertiorari\b',
            r'\bquo warranto\b',
            r'\bprohibition\b',
            r'\bFIR\b',
            r'\bchargesheet\b',
            r'\bbail\b',
            r'\banticipatory\b',
            r'\bsummons\b',
            r'\bwarrant\b',
            
            # Legal Opinions & Analysis
            r'\blegal opinion\b',
            r'\bin my opinion\b',
            r'\bit is opined that\b',
            r'\badvised (?:that|to)\b',
            r'\blegal position\b',
            r'\bjudicial precedent\b',
            r'\bratio decidendi\b',
            r'\bobiter dicta\b',
            
            # Legal Drafting Language
            r'\bwhereas\b',
            r'\bhereinafter\b',
            r'\bforthwith\b',
            r'\baforesaid\b',
            r'\bhereby\b',
            r'\bhereto\b',
            r'\bhereof\b',
            r'\bhereunder\b',
            r'\bthereof\b',
            r'\bthereto\b',
            r'\btherein\b',
            r'\bnow therefore\b',
            r'\bWITNESSETH\b',
            r'\bIN WITNESS WHEREOF\b',
            r'\bTHIS DEED\b',
            r'\bTHIS AGREEMENT\b',
            r'\bPARTY OF THE FIRST PART\b',
            r'\bPARTY OF THE SECOND PART\b',
            
            # Legal Orders & Directions
            r'\bTHEREFORE\b.*\bORDERED\b',
            r'\bIT IS ORDERED\b',
            r'\bIT IS DIRECTED\b',
            r'\bIT IS HELD\b',
            r'\bheld that\b',
            r'\bobserved that\b',
            r'\bruled that\b',
            
            # Contract Language
            r'\bforce majeure\b',
            r'\bindemnify\b',
            r'\bindemnification\b',
            r'\bliability\b',
            r'\brepresentation and warrant\b',
            r'\btermination clause\b',
            r'\bjurisdiction clause\b',
            r'\barbitration clause\b',
            r'\bdispute resolution\b',
            r'\bgoverning law\b',
            
            # Legal Structure
            r'Article\s+[IVXLCDM]+',  # Roman numeral articles
            r'Section\s+\d+\.',  # Section numbering
            r'PART\s+[IVXLCDM]+',  # Parts with Roman numerals
            r'Chapter\s+[IVXLCDM]+',
            r'Clause\s+\d+',
            r'Para(?:graph)?\s+\d+',
            r'Schedule\s+[IVXLCDM]+',
            
            # Proviso & Legal Text Markers
            r'\bproviso\b',
            r'\bProvided that\b',
            r'\bProvided further\b',
            r'\bExplanation\b',
            r'\bIllustration\b',
            r'\bException\b',
            r'\bbare act\b',
            
            # US/International Legal
            r'\b\d+\s+U\.S\.C\.\s+§',  # U.S. Code
            r'\b\d+\s+C\.F\.R\.\s+§',  # Code of Federal Regulations
            r'\bFed\.\s+R\.',  # Federal Rules
        ]
        
        # Sample first 5000 chars for detection
        sample = text[:5000]
        matches = sum(1 for pattern in legal_indicators if re.search(pattern, sample, re.IGNORECASE))
        
        # If 3+ legal indicators found, consider it a legal document
        return matches >= 3

    def _is_case_law(self, text: str) -> bool:
        """
        Determine if document is case law (vs. statute/regulation).
        Supports both Indian Supreme Court judgments and International case law.
        
        Indian Supreme Court Judgment Format:
        - Citation at top: "2024 INSC 859"
        - Case number: "Civil Appeal Nos. 7709-7710/2023"
        - Party names: "APPELLANT(S)" vs "RESPONDENT(S)"
        - Judgment heading: "J U D G M E N T" or "J U D G E M E N T"
        - Judge name: "MANOJ MISRA, J."
        - Sections: "FACTUAL MATRIX", "SUBMISSIONS", "ANALYSIS", "CONCLUSION"
        
        All legal documents use optimized sentence splitting with 2048 token chunks.
        """
        case_law_indicators = [
            # Indian Supreme Court Judgment Structure
            r'\bINSC\b',  # Indian Supreme Court citation
            r'\bAPPELLANT\(S\)\b',
            r'\bRESPONDENT\(S\)\b',
            r'\bVERSUS\b',
            r'\bJ\s+U\s+D\s+G\s*[ME]\s*[EN]\s*T',  # "J U D G M E N T" or "J U D G E M E N T"
            r'[A-Z\s]+,\s+J\.',  # Judge signature like "MANOJ MISRA, J."
            r'\bFACTUAL MATRIX\b',
            r'\bSUBMISSIONS?\b',
            r'\bANALYSIS\b',
            r'\bCONCLUSION\b',
            
            # General Indian Case Law Indicators
            r'\bpetitioner\b',
            r'\brespondent\b',
            r'\bappellant\b',
            r'\bappellee\b',
            r'\baccused\b',
            r'\bcomplainant\b',
            r'\bheld that\b',
            r'\bobserved that\b',
            r'\blearned counsel\b',
            r'\bHon\'?ble(?:\s+Court)?\b',
            r'\bmy lord\b',
            r'\bAIR\s+\d{4}',
            r'\bSCC\s+\d{4}',
            r'\bSCR\s+\d{4}',
            r'\bHigh Court of Judicature\b',
            r'\bSupreme Court of India\b',
            r'\bfirst appellate court\b',
            r'\btrial court\b',
            r'\bpreliminary decree\b',
            r'\bfinal decree\b',
            r'\bcivil (?:appeal|revision|petition)\b',
            
            # US/International Case Law Indicators
            r'\bplaintiff\b',
            r'\bdefendant\b',
            r'\bCourt of Appeals\b',
            r'\bSupreme Court\b',
        ]
        
        # Check first 10000 characters for judgment structure
        sample = text[:10000]
        matches = sum(1 for pattern in case_law_indicators if re.search(pattern, sample, re.IGNORECASE))
        
        # Lower threshold (4) if we find strong indicators like INSC citation or judgment heading
        strong_indicators = [r'\bINSC\b', r'J\s+U\s+D\s+G\s*[ME]\s*[EN]\s*T', r'APPELLANT\(S\)', r'RESPONDENT\(S\)']
        has_strong_indicator = any(re.search(pattern, sample, re.IGNORECASE) for pattern in strong_indicators)
        
        threshold = 3 if has_strong_indicator else 4
        return matches >= threshold

    # def sentence_chunk(self, text: str, topic: str = "", doc_type: str = "document", source_info: Optional[Dict] = None) -> Tuple[List[str], List[dict]]:
    #     """
    #     Sentence-based chunking with metadata
    #     Consolidated from document_manager.py
    #     """
    #     # Simplified chunking logic - can be enhanced as needed
    #     max_chunk_size = 1000  # characters
    #     sentences = text.split('. ')
        
    #     chunks = []
    #     metas = []
    #     current_chunk = ""
    #     chunk_index = 0
        
    #     for sentence in sentences:
    #         if len(current_chunk) + len(sentence) > max_chunk_size and current_chunk:
    #             chunks.append(current_chunk.strip())
                
    #             # Create metadata for this chunk
    #             chunk_meta = {
    #                 'chunk_index': chunk_index,
    #                 'total_chunks': 0,  # Will be updated later
    #                 'document_type': doc_type,
    #                 'page_number': 1,
    #                 'paragraph_number': chunk_index + 1,
    #                 'filename': topic,
    #                 'document_title': topic,
    #                 'source': topic,
    #             }
                
    #             if source_info:
    #                 chunk_meta.update(source_info)
                
    #             metas.append(chunk_meta)
    #             current_chunk = sentence + '. '
    #             chunk_index += 1
    #         else:
    #             current_chunk += sentence + '. '
        
    #     # Add the last chunk
    #     if current_chunk.strip():
    #         chunks.append(current_chunk.strip())
    #         chunk_meta = {
    #             'chunk_index': chunk_index,
    #             'total_chunks': chunk_index + 1,
    #             'document_type': doc_type,
    #             'page_number': 1,
    #             'paragraph_number': chunk_index + 1,
    #             'filename': topic,
    #             'document_title': topic,
    #             'source': topic,
    #         }
    #         if source_info:
    #             chunk_meta.update(source_info)
    #         metas.append(chunk_meta)
        
    #     # Update total_chunks in all metadata
    #     for meta in metas:
    #         meta['total_chunks'] = len(chunks)
        
    #     return chunks, metas

    # ==================== TRUE HYBRID: VECTOR ID GENERATION ====================
    
    def _generate_vector_id(self, document_id: str, chunk_index: int) -> str:
        """Generate consistent Milvus vector ID for cross-referencing with MongoDB.
        
        Format: {document_id}_{chunk_index}
        Example: "doc_67890abcdef123456789_0"
        
        This matches the ID format used in build_hybrid_vectors() to ensure
        MongoDB chunks can be correlated with Milvus vectors.
        
        Args:
            document_id: MongoDB document ID
            chunk_index: 0-based chunk index
            
        Returns:
            Formatted vector ID string
        """
        return f"{document_id}_{chunk_index}"

    # ==================== EMBEDDING FUNCTIONS ====================
    
    def _build_structured_metadata_header(self, metadata: Dict[str, Any], topic: str = "") -> str:
        """
        Build a structured metadata header for embedding to improve semantic retrieval quality.
        
        This header is dynamically generated based on available metadata fields:
        - Judgments: case_number, parties, court, judges, judgment_date
        - Petitions/Cases: case_number, parties, court, jurisdiction, filing_date
        - Legislation: act_title, act_number, ministry, gazette_date, sections
        - General Legal: statutory references, section headings
        
        Only non-null fields are included to keep headers concise and relevant.
        
        Args:
            metadata: Chunk metadata dictionary with legal fields (only non-null values)
            topic: Document topic/filename
            
        Returns:
            Formatted metadata header string (empty if no metadata)
        """
        header_parts = []
        
        # Always include topic/filename first if available
        if topic:
            header_parts.append(f"Document: {topic}")
        
        # === CASE LAW METADATA (Judgments, Orders, Petitions) ===
        
        # Case number with parties
        if metadata.get('case_number'):
            case_line = f"Case: {metadata['case_number']}"
            # Add parties inline if available
            parties = []
            if metadata.get('appellant'):
                parties.append(metadata['appellant'])
            if metadata.get('respondent'):
                parties.append(metadata['respondent'])
            if parties:
                case_line += f" ({' vs '.join(parties)})"
            header_parts.append(case_line)
        elif metadata.get('appellant') or metadata.get('respondent'):
            # If no case number but parties exist, show parties only
            parties = []
            if metadata.get('appellant'):
                parties.append(metadata['appellant'])
            if metadata.get('respondent'):
                parties.append(metadata['respondent'])
            if parties:
                header_parts.append(f"Parties: {' vs '.join(parties)}")
        
        # Court and jurisdiction
        if metadata.get('court'):
            header_parts.append(f"Court: {metadata['court']}")
        
        if metadata.get('jurisdiction'):
            header_parts.append(f"Jurisdiction: {metadata['jurisdiction']}")
        
        # Judgment date (critical for temporal queries)
        if metadata.get('judgment_date'):
            header_parts.append(f"Judgment Date: {metadata['judgment_date']}")
        
        # Judges (bench composition)
        if metadata.get('judges'):
            if isinstance(metadata['judges'], list) and metadata['judges']:
                judges_str = ", ".join(str(j) for j in metadata['judges'])
                header_parts.append(f"Judges: {judges_str}")
            elif isinstance(metadata['judges'], str) and metadata['judges'].strip():
                header_parts.append(f"Judges: {metadata['judges']}")
        
        # === LEGISLATION METADATA (Acts, Ordinances, Rules) ===
        
        # Act title with number and year
        if metadata.get('act_title'):
            act_line = f"Act: {metadata['act_title']}"
            if metadata.get('act_number'):
                act_line += f" (No. {metadata['act_number']})"
            if metadata.get('act_year'):
                act_line += f" - {metadata['act_year']}"
            header_parts.append(act_line)
        
        # Act type (Union/State)
        if metadata.get('act_type'):
            header_parts.append(f"Type: {metadata['act_type']}")
        
        # Enacting authority (ministry or government)
        if metadata.get('ministry'):
            header_parts.append(f"Ministry: {metadata['ministry']}")
        elif metadata.get('enacting_authority'):
            header_parts.append(f"Authority: {metadata['enacting_authority']}")
        
        # State (for state legislation)
        if metadata.get('state'):
            header_parts.append(f"State: {metadata['state']}")
        
        # Gazette publication date
        if metadata.get('gazette_date'):
            header_parts.append(f"Gazette Date: {metadata['gazette_date']}")
        
        # Commencement date
        if metadata.get('commencement_date'):
            header_parts.append(f"Commencement: {metadata['commencement_date']}")
        
        # === STATUTORY REFERENCES ===
        
        # Section references (with statute name)
        if metadata.get('section_number'):
            if metadata.get('section_statute'):
                header_parts.append(f"Section: {metadata['section_number']} of {metadata['section_statute']}")
            else:
                header_parts.append(f"Section: {metadata['section_number']}")
        
        # Article references (constitutional)
        if metadata.get('article_number'):
            if metadata.get('article_source'):
                header_parts.append(f"Article: {metadata['article_number']} of {metadata['article_source']}")
            else:
                header_parts.append(f"Article: {metadata['article_number']}")
        
        # Section heading (document structure context)
        if metadata.get('section_heading'):
            header_parts.append(f"Heading: {metadata['section_heading']}")
        
        # === ADDITIONAL REFERENCES ===
        
        # Legal citations (if embedded as list)
        if metadata.get('legal_citations'):
            if isinstance(metadata['legal_citations'], list) and metadata['legal_citations']:
                citations_str = "; ".join(str(c) for c in metadata['legal_citations'][:3])  # Limit to 3
                header_parts.append(f"Citations: {citations_str}")
        
        # Join with newlines and add separator
        if header_parts:
            return "\n".join(header_parts) + "\n---\n"
        else:
            # No metadata available - return empty string (will use simple topic prefix)
            return ""
    
    async def create_embeddings_optimized(self, chunks: List[str], topic: str, metas: Optional[List[Dict]] = None) -> List[List[float]]:
        """
        Optimized single batch embedding generation with structured metadata header injection.
        
        For legal documents, injects a structured header with key metadata before each chunk
        to improve semantic retrieval quality for metadata-specific queries.
        
        Args:
            chunks: List of chunk texts
            topic: Document topic/filename
            metas: Optional list of metadata dicts aligned with chunks
        
        Returns:
            List of dense embeddings
        """
        # Prepare texts for embedding with structured metadata header + topic prefix
        texts_to_embed = []
        for i, chunk in enumerate(chunks):
            metadata = metas[i] if metas and i < len(metas) else {}
            
            # Build structured header with legal metadata + topic
            header = self._build_structured_metadata_header(metadata, topic)
            
            # Construct final text: header + chunk
            if header:
                text_to_embed = f"{header}{chunk}"
            elif topic:
                # Fallback to simple topic prefix if no metadata
                text_to_embed = f"{topic}\n\n{chunk}"
            else:
                text_to_embed = chunk
            
            texts_to_embed.append(text_to_embed)
        
        self.logger.info(f"Processing {len(texts_to_embed)} texts with structured metadata headers for embedding")
        
        try:
            # Send all texts in one batch - let embedding service handle memory management
            all_embeddings = await embed_texts_batch(
                texts_to_embed,
                task_type="RETRIEVAL_DOCUMENT",
            )
            self.logger.info(f"Successfully generated {len(all_embeddings)} embeddings in single batch")
            return all_embeddings
            
        except Exception as e:
            self.logger.error(f"Failed to generate embeddings: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate embeddings: {str(e)}"
            )

    # ==================== SPARSE EMBEDDING FUNCTIONS ====================
    # NOTE: Sparse vector generation removed - Zilliz Cloud auto-generates sparse_vector from text field
    # using server-side BM25 Function (FunctionType.BM25 in schema)
    # No client-side BM25 computation needed!
    
    # ==================== PARALLEL DENSE + SPARSE GENERATION ====================
    async def generate_dense_and_sparse_parallel(
        self,
        chunks: List[str],
        topic: str,
        user_id: str = "default",
        metas: Optional[List[Dict]] = None
    ) -> Tuple[List[List[float]], List[Optional[Dict[str, Any]]]]:
        """Generate dense embeddings and sparse vectors in parallel with structured metadata headers.

    Strategy:
    1. Prepare texts (with structured metadata header + topic prefix for dense semantic context).
    2. Launch dense embedding batch task (LLM) and sparse batch task (Milvus BM25) concurrently.
    3. Return parallel lists aligned by index. Sparse entries may be None if generation failed; caller can decide fallback.

    This reduces end-to-end ingestion latency by overlapping llm dense embeddings with Milvus BM25 inference instead of serializing them.

        Args:
            chunks: Raw chunk texts (already chunked)
            topic: Topic/title; added as prefix to dense embedding text for context
            user_id: Device identifier for per-namespace sparse generation (legacy)
            metas: Optional list of metadata dicts aligned with chunks for header injection

        Returns:
            (dense_embeddings, sparse_vectors)
        """
        # Prepare texts with structured metadata headers
        texts_to_process = []
        for i, chunk in enumerate(chunks):
            metadata = metas[i] if metas and i < len(metas) else {}
            
            # Build structured header with legal metadata + topic
            header = self._build_structured_metadata_header(metadata, topic)
            
            # Construct final text: header + chunk
            if header:
                text = f"{header}{chunk}"
            elif topic:
                # Fallback to simple topic prefix if no metadata
                text = f"{topic}\n\n{chunk}"
            else:
                text = chunk
            
            texts_to_process.append(text)

        # Generate dense embeddings only - Zilliz Cloud handles sparse vectors
        dense_result = await embed_texts_batch(texts_to_process, task_type="RETRIEVAL_DOCUMENT")

        # Error handling
        if isinstance(dense_result, Exception):
            self.logger.error(f"❌ Dense embedding batch failed: {dense_result}")
            raise HTTPException(status_code=500, detail=f"Dense embedding failure: {dense_result}")

        # Return dense embeddings and empty list for sparse (not needed - Zilliz auto-generates)
        # Keep return signature for backward compatibility
        sparse_result = [None] * len(dense_result)
        
        return dense_result, sparse_result

    def build_hybrid_vectors(
        self,
        document_id: str,
        user_id: str,
        dense_embeddings: List[List[float]],
        sparse_vectors: List[Optional[Dict[str, Any]]],
        metas: List[Dict[str, Any]],
        chunks: Optional[List[str]] = None,  # ⚠️ DEPRECATED - text not stored in Milvus
        source_type: str = "document"  # "document", "audio", "video", or "note"
    ) -> List[Dict[str, Any]]:
        """Construct Milvus-ready hybrid vector objects WITHOUT text in metadata.
        
        BREAKING CHANGE: Text is NO LONGER stored in Milvus metadata.
        Text is stored in MongoDB based on source_type:
        - "document" → document_chunked collection
        - "audio" → audio_transcripts collection
        - "video" → video_transcripts collection
        - "note" → Notes collection
        Milvus stores only vectors, chunk_id, and source_type for routing.

        Each vector:
            {
              'id': f"{document_id}_{i}",
              'values': dense_embedding,
              'metadata': meta (WITHOUT text field),
              'sparse_values': auto-generated by Zilliz BM25
            }

        Args:
            document_id: Source document ID
            user_id: Namespace device ID
            dense_embeddings: List of dense embedding lists (LLM)
            sparse_vectors: Aligned list of sparse dicts from BM25 (may be None)
            metas: Metadata list aligned with embeddings
            chunks: DEPRECATED - text not stored in Milvus

        Returns:
            List of vector dicts suitable for Milvus upsert (NO TEXT in metadata)
        """
        vectors: List[Dict[str, Any]] = []
        total = len(dense_embeddings)
        for i in range(total):
            meta = metas[i] if i < len(metas) else {}
            
            # BREAKING CHANGE: Generate chunk_id for MongoDB correlation
            chunk_id = f"{document_id}_{i}"
            
            # Build metadata WITHOUT text field (text only in MongoDB)
            milvus_metadata = {
                **{k: v for k, v in meta.items() if k != 'text'},  # Exclude text
                "document_id": document_id,
                "user_id": user_id,
                "chunk_index": i,
                "chunk_id": chunk_id,  # For MongoDB correlation
                "source_type": source_type,  # "document", "audio", "video", or "note" for text routing
            }
            
            vec: Dict[str, Any] = {
                "id": f"{document_id}_{i}",
                "values": dense_embeddings[i],
                "metadata": milvus_metadata
            }
            # NOTE: sparse_values removed - Zilliz Cloud auto-generates from text field
            vectors.append(vec)
        self.logger.info(f"🧪 Built {len(vectors)} hybrid vector objects (sparse auto-generated by Zilliz)")
        return vectors

    # ==================== MONGODB BATCH TEXT RETRIEVAL ====================
    
    async def _fetch_chunk_text_from_mongodb(
        self,
        chunk_id: str,
        source_type: str = "document"
    ) -> Optional[str]:
        """
        Fetch text for a single chunk from MongoDB based on source_type.
        
        Args:
            chunk_id: Chunk ID (format: {document_id}_{chunk_index} or {document_id}_chunk_{index})
            source_type: "document", "audio", "video", or "note"
            
        Returns:
            Chunk text or None if not found
        """
        try:
            if source_type == "document":
                # Fetch from document_chunked collection
                doc_coll = self.db["document_chunked"]
                doc = await doc_coll.find_one(
                    {"metadata.chunk_id": chunk_id},
                    {"metadata.text": 1, "_id": 0}
                )
                if doc and "metadata" in doc:
                    return doc["metadata"].get("text", "")
                    
            elif source_type == "audio":
                # Extract document_id from chunk_id
                document_id = chunk_id.rsplit('_', 1)[0]
                self.logger.info(f"🔍 [AUDIO_CHUNK_DEBUG] chunk_id: {chunk_id}")
                self.logger.info(f"🔍 [AUDIO_CHUNK_DEBUG] extracted document_id: {document_id}")
                
                # Audio transcripts are in "audio_transcripts" collection with "transcript" field
                audio_coll = self.db["audio_transcripts"]
                doc = await audio_coll.find_one(
                    {"_id": document_id},
                    {"transcript": 1, "_id": 0}
                )
                if doc:
                    return doc.get("transcript", "")
                else:
                    self.logger.warning(f"⚠️ [AUDIO_CHUNK_DEBUG] No document found in audio_transcripts with _id: {document_id}")
                    
            elif source_type == "video":
                # Extract document_id from chunk_id
                document_id = chunk_id.rsplit('_', 1)[0]
                video_coll = self.db["video_transcripts"]
                doc = await video_coll.find_one(
                    {"_id": document_id},
                    {"full_transcription": 1, "_id": 0}
                )
                if doc:
                    return doc.get("full_transcription", "")
                    
            elif source_type == "note":
                # Extract document_id from chunk_id
                document_id = chunk_id.rsplit('_', 1)[0]
                notes_coll = self.db["Notes"]
                doc = await notes_coll.find_one(
                    {"_id": document_id},
                    {"text": 1, "_id": 0}
                )
                if doc:
                    return doc.get("text", "")
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Failed to fetch text for chunk {chunk_id} from MongoDB: {e}")
            return None
    
    async def batch_fetch_chunk_texts(
        self,
        chunk_ids: List[str],
        user_id: str,
        source_types: Optional[Dict[str, str]] = None  # chunk_id → source_type mapping
    ) -> Dict[str, str]:
        """
        Batch fetch chunk texts from MongoDB (document_chunked, audio_transcripts, video_transcripts, or Notes).
        Routes to correct collection based on source_type.
        
        This is the SINGLE SOURCE OF TRUTH for chunk text retrieval.
        
        BREAKING CHANGE: Orchestrator must use this method to get text from MongoDB,
        NOT from Milvus metadata.
        
        Args:
            chunk_ids: List of chunk_id values (format: {document_id}_{chunk_index})
            user_id: User ID for security filtering
            source_types: Optional dict mapping chunk_id → "document"|"audio"|"video"|"note"
                         If not provided, defaults to "document" for all
            
        Returns:
            Dict mapping chunk_id → text
            
        Example:
            chunk_ids = ["doc_123_0", "audio_456_1", "video_789_2", "note_abc_0"]
            source_types = {"doc_123_0": "document", "audio_456_1": "audio", "video_789_2": "video", "note_abc_0": "note"}
            texts = await service.batch_fetch_chunk_texts(chunk_ids, "user_abc", source_types)
        """
        try:
            if not chunk_ids:
                return {}
            
            await self._ensure_indexes()
            
            # Group chunk_ids by source_type
            document_chunks = []
            audio_chunks = []
            video_chunks = []
            note_chunks = []
            
            for chunk_id in chunk_ids:
                source_type = source_types.get(chunk_id, "document") if source_types else "document"
                if source_type == "audio":
                    audio_chunks.append(chunk_id)
                elif source_type == "video":
                    video_chunks.append(chunk_id)
                elif source_type == "note":
                    note_chunks.append(chunk_id)
                else:
                    document_chunks.append(chunk_id)
            
            chunk_texts = {}
            
            # Fetch from document_chunked collection
            if document_chunks:
                projection = {
                    "metadata.chunk_id": 1, 
                    "metadata.text": 1, 
                    "document_id": 1, 
                    "file_type": 1,
                    "metadata.file_type": 1,
                    "_id": 0
                }
                
                cursor = self.collection.find(
                    {
                        "metadata.chunk_id": {"$in": document_chunks},
                        "user_id": user_id
                    },
                    projection
                )
                
                excel_docs_to_expand = set()
                
                async for doc in cursor:
                    metadata = doc.get("metadata", {})
                    chunk_id = metadata.get("chunk_id")
                    text = metadata.get("text", "")
                    
                    # Check for Excel file type
                    file_type = doc.get("file_type") or metadata.get("file_type")
                    document_id = doc.get("document_id")
                    
                    if chunk_id and text:
                        chunk_texts[chunk_id] = text
                        
                        # Mark Excel docs for full-content expansion
                        if file_type and str(file_type).lower().strip('.') in ['xlsx', 'xls', 'excel'] and document_id:
                            excel_docs_to_expand.add(document_id)
                
                self.logger.info(f"📄 Fetched {len([c for c in chunk_texts if c in document_chunks])}/{len(document_chunks)} chunks. Expanding {len(excel_docs_to_expand)} Excel docs.")
                
                # Expand Excel docs to return FULL content
                for doc_id in excel_docs_to_expand:
                    try:
                        # Fetch ALL chunks for this document sorted by index
                        all_chunks = await self.collection.find(
                            {"document_id": doc_id, "user_id": user_id},
                            {"metadata.text": 1},
                            sort=[("chunk_index", 1)]
                        ).to_list(None)
                        
                        if all_chunks:
                            full_text = "\n".join([c.get("metadata", {}).get("text", "") for c in all_chunks])
                            
                            # Update all requested chunk_ids that belong to this document
                            for cid in list(chunk_texts.keys()):
                                if cid.startswith(f"{doc_id}_"):
                                    chunk_texts[cid] = full_text
                            
                            self.logger.info(f"📊 Expanded Excel doc {doc_id} to full content ({len(full_text)} chars)")
                    except Exception as e:
                        self.logger.error(f"Failed to expand Excel doc {doc_id}: {e}")
            
            # Fetch from audio_transcripts collection
            if audio_chunks:
                # Extract document_ids from chunk_ids (format: {document_id}_{chunk_index})
                audio_doc_ids = list(set([cid.rsplit('_', 1)[0] for cid in audio_chunks]))
                # Audio transcripts are in "audio_transcripts" collection with "transcript" field
                audio_coll = self.db["audio_transcripts"]
                cursor = audio_coll.find(
                    {"_id": {"$in": audio_doc_ids}, "user_id": user_id},
                    {"_id": 1, "transcript": 1}
                )
                audio_texts = {}
                async for doc in cursor:
                    audio_texts[doc["_id"]] = doc.get("transcript", "")
                
                # Map chunk_ids to full transcription (audio doesn't chunk in MongoDB)
                for chunk_id in audio_chunks:
                    doc_id = chunk_id.rsplit('_', 1)[0]
                    if doc_id in audio_texts:
                        chunk_texts[chunk_id] = audio_texts[doc_id]
                self.logger.info(f"🎵 Fetched {len([c for c in chunk_texts if c in audio_chunks])}/{len(audio_chunks)} from audio_transcripts")
            
            # Fetch from video_transcripts collection
            if video_chunks:
                video_doc_ids = list(set([cid.rsplit('_', 1)[0] for cid in video_chunks]))
                video_coll = self.db["video_transcripts"]
                cursor = video_coll.find(
                    {"_id": {"$in": video_doc_ids}, "user_id": user_id},
                    {"_id": 1, "full_transcription": 1}
                )
                video_texts = {}
                async for doc in cursor:
                    video_texts[doc["_id"]] = doc.get("full_transcription", "")
                
                # Map chunk_ids to full transcription
                for chunk_id in video_chunks:
                    doc_id = chunk_id.rsplit('_', 1)[0]
                    if doc_id in video_texts:
                        chunk_texts[chunk_id] = video_texts[doc_id]
                self.logger.info(f"🎬 Fetched {len([c for c in chunk_texts if c in video_chunks])}/{len(video_chunks)} from video_transcripts")
            
            # Fetch from Notes collection
            if note_chunks:
                note_doc_ids = list(set([cid.rsplit('_', 1)[0] for cid in note_chunks]))
                notes_coll = self.db["Notes"]
                cursor = notes_coll.find(
                    {"_id": {"$in": note_doc_ids}, "user_id": user_id},
                    {"_id": 1, "text": 1}
                )
                note_texts = {}
                async for doc in cursor:
                    note_texts[doc["_id"]] = doc.get("text", "")
                
                # Map chunk_ids to full note text
                for chunk_id in note_chunks:
                    doc_id = chunk_id.rsplit('_', 1)[0]
                    if doc_id in note_texts:
                        chunk_texts[chunk_id] = note_texts[doc_id]
                self.logger.info(f"📝 Fetched {len([c for c in chunk_texts if c in note_chunks])}/{len(note_chunks)} from Notes")
            
            # Fetch from Notes collection
            if note_chunks:
                note_doc_ids = list(set([cid.rsplit('_', 1)[0] for cid in note_chunks]))
                notes_coll = self.db["Notes"]
                cursor = notes_coll.find(
                    {"_id": {"$in": note_doc_ids}, "user_id": user_id},
                    {"_id": 1, "text": 1}
                )
                note_texts = {}
                async for doc in cursor:
                    note_texts[doc["_id"]] = doc.get("text", "")
                
                # Map chunk_ids to full note text
                for chunk_id in note_chunks:
                    doc_id = chunk_id.rsplit('_', 1)[0]
                    if doc_id in note_texts:
                        chunk_texts[chunk_id] = note_texts[doc_id]
                self.logger.info(f"📝 Fetched {len([c for c in chunk_texts if c in note_chunks])}/{len(note_chunks)} from Notes")
            
            found_count = len(chunk_texts)
            missing_count = len(chunk_ids) - found_count
            
            if missing_count > 0:
                self.logger.warning(
                    f"⚠️ Batch text fetch: {found_count}/{len(chunk_ids)} found, {missing_count} missing"
                )
            else:
                self.logger.info(
                    f"✅ Batch text fetch: {found_count}/{len(chunk_ids)} chunks retrieved from MongoDB"
                )
            
            return chunk_texts
            
        except Exception as e:
            self.logger.error(f"❌ Batch text fetch failed: {e}")
            return {}
    
    # ==================== MILVUS OPERATIONS ====================
    
    async def upsert_to_milvus_optimized(self, vectors: List[Dict], user_id: str, document_id: str) -> int:
        """
        Optimized Milvus upsert with better batching
        Migrated from Milvus to Milvus
        """
        try:
            # Prepare data for Milvus insertion
            milvus_data = []
            for vector in vectors:
                data_point = {
                    "id": vector["id"],
                    "vector": vector["values"],
                    "user_id": user_id,
                    "document_id": document_id,
                }
                # Add all metadata fields
                if "metadata" in vector:
                    for key, value in vector["metadata"].items():
                        # Ensure values are JSON-serializable
                        if isinstance(value, (str, int, float, bool)) or value is None:
                            data_point[key] = value
                        else:
                            data_point[key] = str(value)
                
                milvus_data.append(data_point)
            
            # Insert into Milvus in batches
            batch_size = 100
            total_inserted = 0
            
            for i in range(0, len(milvus_data), batch_size):
                batch = milvus_data[i:i+batch_size]
                
                # Retry logic for transient failures
                for attempt in range(3):
                    try:
                        # Refresh from singleton to avoid stale gRPC channel
                        from config.milvus_config import get_milvus_client
                        self.milvus_client = get_milvus_client()
                        res = self.milvus_client.insert(
                            collection_name=self.collection_name,
                            data=batch
                        )
                        total_inserted += res.get("insert_count", len(batch))
                        self.logger.debug(f"Inserted batch {i//batch_size + 1}/{math.ceil(len(milvus_data)/batch_size)}")
                        break
                    except Exception as batch_error:
                        if attempt < 2 and ("closed channel" in str(batch_error).lower() or "connect first" in str(batch_error).lower()):
                            self.logger.warning(f"⚠️ Milvus channel dead, recreating client (attempt {attempt+1})...")
                            from config.milvus_config import recreate_milvus_client
                            self.milvus_client = recreate_milvus_client()
                        if attempt == 2:  # Last attempt
                            raise batch_error
                        await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
            
            self.logger.info(f"Successfully inserted {total_inserted} vectors to Milvus collection {self.collection_name}")
            return total_inserted
            
        except Exception as e:
            self.logger.error(f"[{document_id}] Failed to insert vectors to Milvus: {e}")
            raise

    async def upsert_to_milvus_hybrid_optimized(self, vectors: List[Dict], user_id: str, document_id: str, 
                                                folder_id: Optional[str] = None, is_enterprise: bool = False, 
                                                entity_id: Optional[str] = None, document_details: Optional[str] = None, 
                                                department: Optional[str] = None) -> int:
        """
        Optimized Milvus hybrid upsert with parallel batch uploads (up to 10 batches).
        Supports the new Milvus hybrid schema with required fields including folder_id and entity_id.
        
        ✅ PARALLEL OPTIMIZATION: Processes up to 10 batches in parallel using asyncio.gather
        Similar to OCR and embedding parallel batching for maximum upload speed
        """
        try:
            # Prepare data for Milvus insertion
            milvus_data = []
            for vector in vectors:
                # Convert string ID to int64 for Milvus primary_key field
                # Use hash of the ID string to generate a consistent integer
                id_string = vector["id"]
                id_hash = int(hashlib.sha256(id_string.encode()).hexdigest()[:15], 16)  # Use first 15 hex chars to fit in int64
                
                # Extract required fields from metadata
                metadata = vector.get("metadata", {})
                text = metadata.get("text", "")
                chunk_index = metadata.get("chunk_index", 0)
                total_chunks = metadata.get("total_chunks", 1)
                
                # Debug: Check if created_at exists in metadata (should be filtered out)
                if "created_at" in metadata:
                    self.logger.debug(f"Found created_at in metadata (will be filtered): {type(metadata['created_at'])}")
                
                # Build required schema fields
                data_point = {
                    "primary_key": id_hash,  # INT64 primary key
                    "chunk_id": id_string,  # VARCHAR(100) - original string ID
                    "dense_vector": vector["values"],  # FLOAT_VECTOR(768) - dense embedding
                    "user_id": user_id,  # VARCHAR(100) - indexed
                    "document_id": document_id,  # VARCHAR(100) - indexed
                    "folder_id": folder_id or "documents",  # VARCHAR(100) - indexed (default to "documents")
                    "entity_id": entity_id or "none",  # VARCHAR(100) - indexed (default to "none")
                    "text": text[:65535] if text else "",  # VARCHAR(65535) - chunk text
                    "chunk_index": int(chunk_index),  # INT64
                    "total_chunks": int(total_chunks),  # INT64
                    "created_at": int(time.time() * 1000),  # INT64 - epoch milliseconds
                }
                
                # ✅ ZILLIZ NATIVE BM25: sparse_vector is AUTO-GENERATED from text field
                # Schema has Function(name="text_bm25_emb", input=["text"], output=["sparse_vector"], type=BM25)
                # Just provide text field - Zilliz handles tokenization and sparse vector generation
                
                # Add optional enterprise fields as dynamic fields (for additional metadata beyond schema)
                if is_enterprise:
                    data_point["is_enterprise"] = is_enterprise
                if department:
                    data_point["department"] = department
                if document_details:
                    data_point["document_details"] = document_details
                
                # Add remaining metadata as dynamic fields
                if metadata:
                    for key, value in metadata.items():
                        # Skip fields already added to required schema
                        if key in ["text", "chunk_index", "total_chunks", "created_at"]:
                            continue
                        
                        # Add JSON-serializable values as dynamic fields
                        if isinstance(value, (str, int, float, bool)) or value is None:
                            data_point[key] = value
                        elif isinstance(value, (list, dict)):
                            data_point[key] = value  # Milvus supports JSON types
                        else:
                            data_point[key] = str(value)
                
                milvus_data.append(data_point)
            
            total_vectors = len(milvus_data)
            if total_vectors == 0:
                return 0
            
            # Server-side BM25: sparse vectors auto-generated by Zilliz Cloud from text field
            self.logger.info(f"[{document_id}] 📤 Uploading {total_vectors} vectors (sparse auto-generated by server-side BM25)")
            
            # Batch configuration
            BATCH_SIZE = 100
            MAX_PARALLEL_BATCHES = 10  # Process up to 10 batches in parallel
            RETRY_ATTEMPTS = 3
            
            # Single batch - process directly
            if total_vectors <= BATCH_SIZE:
                for attempt in range(RETRY_ATTEMPTS):
                    try:
                        # Refresh from singleton to avoid stale gRPC channel
                        from config.milvus_config import get_milvus_client as _get_client
                        self.milvus_client = _get_client()
                        res = self.milvus_client.insert(
                            collection_name=self.collection_name,
                            data=milvus_data
                        )
                        total_inserted = res.get("insert_count", len(milvus_data))
                        self.logger.info(f"[{document_id}] ✅ Successfully inserted {total_inserted} vectors to Milvus (single batch)")
                        return total_inserted
                    except Exception as e:
                        if attempt < RETRY_ATTEMPTS - 1 and ("closed channel" in str(e).lower() or "connect first" in str(e).lower()):
                            self.logger.warning(f"[{document_id}] ⚠️ Milvus channel dead, recreating client (attempt {attempt+1})...")
                            from config.milvus_config import recreate_milvus_client
                            self.milvus_client = recreate_milvus_client()
                        if attempt == RETRY_ATTEMPTS - 1:
                            raise
                        await asyncio.sleep(0.5 * (attempt + 1))
            
            # Multiple batches - process in parallel groups
            total_batches = (total_vectors + BATCH_SIZE - 1) // BATCH_SIZE
            self.logger.info(f"🚀 Parallel Milvus upload: {total_vectors} vectors → {total_batches} batches (max {MAX_PARALLEL_BATCHES} parallel)")
            
            # Prepare all batches
            batches = []
            for batch_idx in range(total_batches):
                start_idx = batch_idx * BATCH_SIZE
                end_idx = min(start_idx + BATCH_SIZE, total_vectors)
                batch_data = milvus_data[start_idx:end_idx]
                batches.append({
                    'batch_idx': batch_idx,
                    'data': batch_data
                })
            
            # Process batches in parallel groups
            total_inserted = 0
            
            async def process_batch_group(batch_group):
                """Process a group of batches in parallel"""
                async def upload_single_batch(batch_info):
                    batch_idx = batch_info['batch_idx']
                    batch_data = batch_info['data']
                    
                    # Retry logic for transient failures
                    for attempt in range(RETRY_ATTEMPTS):
                        try:
                            # Refresh from singleton to avoid stale gRPC channel
                            from config.milvus_config import get_milvus_client as _get_client
                            self.milvus_client = _get_client()
                            res = self.milvus_client.insert(
                                collection_name=self.collection_name,
                                data=batch_data
                            )
                            inserted = res.get("insert_count", len(batch_data))
                            self.logger.debug(f"[{document_id}] ✅ Batch {batch_idx+1}/{total_batches} uploaded ({inserted} vectors)")
                            return inserted
                        except Exception as e:
                            if attempt < RETRY_ATTEMPTS - 1 and ("closed channel" in str(e).lower() or "connect first" in str(e).lower()):
                                self.logger.warning(f"[{document_id}] ⚠️ Milvus channel dead, recreating client (attempt {attempt+1})...")
                                from config.milvus_config import recreate_milvus_client
                                self.milvus_client = recreate_milvus_client()
                            if attempt == RETRY_ATTEMPTS - 1:
                                self.logger.error(f"[{document_id}] ❌ Batch {batch_idx+1}/{total_batches} failed after {RETRY_ATTEMPTS} attempts: {e}")
                                raise
                            await asyncio.sleep(0.5 * (attempt + 1))
                
                # Process all batches in this group in parallel
                results = await asyncio.gather(
                    *[upload_single_batch(batch_info) for batch_info in batch_group],
                    return_exceptions=False
                )
                return sum(results)
            
            # Split batches into groups of MAX_PARALLEL_BATCHES
            for group_start in range(0, total_batches, MAX_PARALLEL_BATCHES):
                group_end = min(group_start + MAX_PARALLEL_BATCHES, total_batches)
                batch_group = batches[group_start:group_end]
                
                self.logger.info(f"📦 Uploading batch group {group_start//MAX_PARALLEL_BATCHES + 1}: batches {group_start+1}-{group_end} in parallel")
                
                # Process this group in parallel
                group_inserted = await process_batch_group(batch_group)
                total_inserted += group_inserted
            
            self.logger.info(f"[{document_id}] ✅ Successfully inserted {total_inserted} vectors to Milvus using parallel upload ({total_batches} batches)")
            return total_inserted
            
        except Exception as e:
            self.logger.error(f"[{document_id}] Failed to insert hybrid vectors to Milvus: {e}")
            raise

    async def store_vector_mapping(self, document_id: str, user_id: str, vector_ids: List[str], 
                                 topic: str = "", file_type: str = "", folder_id: Optional[str] = None,
                                 page_number: Optional[int] = None, paragraph_number: Optional[int] = None,
                                 chunk_index: Optional[int] = None, total_chunks: Optional[int] = None) -> bool:
        """
        Store the mapping between a document and its Milvus vector IDs with metadata.
        Stores in MongoDB for tracking and batch deletion.
        
        Args:
            document_id: Document identifier
            user_id: User identifier
            vector_ids: List of vector IDs in Milvus (format: {document_id}_{chunk_index})
        
        Returns:
            True if storage successful, False otherwise
        """
        try:
            # Delete existing mapping if it exists
            await self.delete_vector_mapping(document_id, user_id)
            
            # Create new mapping with complete metadata including citation fields
            mapping = MilvusChunkModel(
                document_id=document_id,
                user_id=user_id,
                vector_ids=vector_ids,
                total_vectors=len(vector_ids),
                topic=topic,
                topic_or_filename=topic,
                file_type=file_type,
                folder_id=folder_id,
                source=topic,  # topic is used for source attribution
                
                # Citation fields for source attribution
                page_number=page_number,
                paragraph_number=paragraph_number,
                chunk_index=chunk_index,
                total_chunks=total_chunks,
                
                created_at=datetime.utcnow()
            )
            
            # Store in MongoDB
            mapping_dict = mapping.model_dump(by_alias=True)
            if "_id" in mapping_dict and mapping_dict["_id"] is None:
                mapping_dict.pop("_id", None)
                
            await self.milvus_mapping_collection.insert_one(mapping_dict)
            
            self.logger.info(f"📋 Stored Milvus mapping for document {document_id}: {len(vector_ids)} vector IDs")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error storing Milvus mapping for document {document_id}: {e}")
            return False

    async def get_vector_ids(self, document_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get all Milvus vector IDs for a document and user.
        Returns dict with 'vector_ids' key, or None if not found.
        Handles both single-doc (array of vector_ids) and multi-doc (individual vector_ids) approaches.
        
        Args:
            document_id: Document identifier
            user_id: User identifier
        
        Returns:
            Dict with key: vector_ids (List[str])
            None if not found
        """
        try:
            # First try single document approach (array of vector_ids)
            mapping_doc = await self.milvus_mapping_collection.find_one({
                "document_id": document_id,
                "user_id": user_id,
                "vector_ids": {"$exists": True}  # Document with vector_ids array
            })
            
            if mapping_doc and "vector_ids" in mapping_doc:
                vector_ids = mapping_doc.get("vector_ids", [])
                self.logger.info(f"📋 Found {len(vector_ids)} Milvus vector IDs for document {document_id} (user: {user_id})")
                return {"vector_ids": vector_ids}
            
            # If not found, try multi-document approach (individual vector_ids)
            mapping_docs = self.milvus_mapping_collection.find({
                "document_id": document_id,
                "user_id": user_id,
                "vector_id": {"$exists": True}  # Documents with individual vector_id
            })
            
            vector_ids = []
            async for doc in mapping_docs:
                if "vector_id" in doc:
                    vector_ids.append(doc["vector_id"])
            
            if vector_ids:
                self.logger.info(f"📋 Found {len(vector_ids)} Milvus vector IDs for document {document_id} (user: {user_id})")
                return {"vector_ids": vector_ids}
            else:
                self.logger.warning(f"📋 No Milvus mapping found for document {document_id}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Error retrieving Milvus vector IDs for document {document_id}: {e}")
            return None

    async def delete_vector_mapping(self, document_id: str, user_id: str) -> bool:
        """
        Delete ALL Milvus vector mappings for a document and user from MongoDB.
        Uses delete_many to handle both single-doc and multi-doc mapping approaches.
        
        Args:
            document_id: Document identifier
            user_id: User identifier
        
        Returns:
            True if deletion successful or no mappings found, False on error
        """
        try:
            result = await self.milvus_mapping_collection.delete_many({
                "document_id": document_id,
                "user_id": user_id
            })
            
            if result.deleted_count > 0:
                self.logger.info(f"🗑️ Deleted {result.deleted_count} Milvus mapping entries for document {document_id}")
                return True
            else:
                self.logger.debug(f"🗑️ No Milvus mappings found to delete for document {document_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error deleting Milvus mappings for document {document_id}: {e}")
            return False

    async def delete_from_milvus(self, document_id: str, user_id: str, is_enterprise: bool = False, document_details: Optional[str] = None, department: Optional[str] = None) -> bool:
        """
        Delete all embeddings for a document from Milvus using document_id filter
        Migrated from Milvus namespace-based deletion
        """
        try:
            # Build filter expression for Milvus
            filter_expr = f'document_id == "{document_id}" and user_id == "{user_id}"'
            
            self.logger.info(f"🗑️ Deleting vectors for document {document_id} with filter: {filter_expr}")
            
            # Refresh from singleton to avoid stale gRPC channel
            from config.milvus_config import get_milvus_client
            self.milvus_client = get_milvus_client()
            
            # Delete vectors from Milvus using filter
            res = self.milvus_client.delete(
                collection_name=self.collection_name,
                filter=filter_expr
            )
            
            delete_count = res.get("delete_count", 0)
            self.logger.info(f"🗑️ ✅ Deleted {delete_count} vector embeddings for document '{document_id}'")
            
            # Delete the vector mapping after successful Milvus deletion
            await self.delete_vector_mapping(document_id, user_id)
            self.logger.info(f"🗑️ ✅ Deleted vector mapping from MongoDB")
            
            return True
            
        except Exception as e:
            self.logger.warning(f"🗑️ Failed to delete embeddings from Milvus for document {document_id}: {e}")
            return False

    # ==================== UNIFIED DOCUMENT PROCESSING ====================
    # These methods combine operations for single-threaded processing (not for parallel)
    
    # ==================== EXISTING SERVICE METHODS ====================
    # (Include all other methods from the original chunked_document_service.py)
    
    async def get_document_metadata(self, document_id: str) -> Optional[DocumentMetadataModel]:
        """Get document metadata from first chunk"""
        try:
            query = {"document_id": document_id, "chunk_index": 0}
            self.logger.info(f"🔍 Querying for document metadata: {query}")
            
            doc = await self.collection.find_one(query)
            self.logger.info(f"📊 Found metadata document: {doc is not None}")
            
            if doc:
                self.logger.info(f"📄 Document metadata fields: {list(doc.keys())}")
                # Handle ObjectId conversion for _id field
                if "_id" in doc and doc["_id"]:
                    doc["_id"] = str(doc["_id"])
                    
                # Ensure datetime fields have proper defaults if missing
                created_at = doc.get("created_at") or datetime.utcnow()
                updated_at = doc.get("updated_at") or datetime.utcnow()
                
                # Get metadata dict for fallback lookups
                doc_metadata = doc.get("metadata", {})
                
                # Safe field access with fallback to metadata
                file_type = doc.get("file_type") or doc_metadata.get("file_type", "unknown")
                topic_or_filename = doc.get("topic_or_filename") or doc_metadata.get("topic_or_filename", "unknown")
                
                # Calculate total chunks for this document (get from any chunk)
                total_chunks_in_doc = doc.get("total_chunks")
                if not total_chunks_in_doc:
                    # Count total chunks for this document if not stored in the chunk
                    total_chunks_in_doc = await self.collection.count_documents({"document_id": document_id})
                    self.logger.info(f"📊 Calculated total_chunks from count: {total_chunks_in_doc}")
                
                return DocumentMetadataModel(
                    document_id=doc["document_id"],
                    file_type=file_type,
                    total_pages=doc.get("total_pages", 1),
                    total_chunks=total_chunks_in_doc,
                    chunk_size=doc.get("chunk_size", 1),
                    file_size=doc.get("file_size", 0),
                    user_id=doc["user_id"],
                    folder_id=doc.get("folder_id", "documents"),
                    topic_or_filename=topic_or_filename,
                    processing_status=doc.get("processing_status", "completed"),
                    extracted_metadata=doc.get("extracted_metadata", {}),
                    created_at=created_at,
                    updated_at=updated_at,
                    is_enterprise=doc.get("is_enterprise", False),
                    entity_id=doc.get("entity_id"),
                    fileUrl=doc.get("fileUrl")  # Legacy field, now using files_service for S3 URL
                )
            return None
        except Exception as e:
            self.logger.error(f"❌ Error getting document metadata: {e}")
            return None

        except Exception as e:
            self.logger.error(f"❌ Error getting document blob path: {e}")
            return None

    async def document_exists(self, document_id: str) -> bool:
        """Check if a document already exists"""
        try:
            count = await self.collection.count_documents({"document_id": document_id}, limit=1)
            return count > 0
        except Exception as e:
            self.logger.error(f"❌ Error checking document existence: {e}")
            return False

    async def get_document_chunks(
        self,
        document_id: str,
        page: int = 1,
        per_page: int = 20
    ) -> Tuple[List, int]:
        """Get chunks for a document with pagination"""
        try:
            await self._ensure_indexes()
            
            # Build query
            match_query = {"document_id": document_id}
            self.logger.info(f"🔍 Querying for document chunks: {match_query}")
            
            # Get total count
            total = await self.collection.count_documents(match_query)
            self.logger.info(f"📊 Found {total} total chunks for document {document_id}")
            
            # If no chunks found, let's check if any documents exist in the collection
            if total == 0:
                all_docs_count = await self.collection.count_documents({})
                self.logger.info(f"🔍 Total documents in collection: {all_docs_count}")
                if all_docs_count > 0:
                    # Sample a few document IDs to see what's in the collection
                    sample_docs = await self.collection.find({}, {"document_id": 1, "_id": 0}).limit(5).to_list(length=None)
                    sample_ids = [doc.get("document_id") for doc in sample_docs]
                    self.logger.info(f"📄 Sample document IDs in collection: {sample_ids}")
            
            # Get paginated chunks, sorted by chunk_index
            skip = (page - 1) * per_page
            cursor = self.collection.find(match_query).sort("chunk_index", 1).skip(skip).limit(per_page)
            
            chunks = []
            chunk_count = 0
            async for chunk_doc in cursor:
                chunk_count += 1
                self.logger.info(f"📄 Processing chunk {chunk_count}: chunk_index={chunk_doc.get('chunk_index')}, content_length={len(chunk_doc.get('chunk_text', ''))}")
                
                # Convert MongoDB document to chunk model
                # Handle ObjectId conversion for _id field
                if "_id" in chunk_doc and chunk_doc["_id"]:
                    chunk_doc["_id"] = str(chunk_doc["_id"])
                
                # Ensure required fields have proper defaults
                chunk_text = chunk_doc.get("chunk_text", "")
                chunk_doc["content_length"] = chunk_doc.get("content_length") or len(chunk_text)
                chunk_doc["metadata"] = chunk_doc.get("metadata") or {}
                
                # Fix missing total_chunks field by calculating from total document count
                if not chunk_doc.get("total_chunks"):
                    chunk_doc["total_chunks"] = total
                
                # Ensure datetime fields are present
                if "created_at" not in chunk_doc:
                    chunk_doc["created_at"] = datetime.utcnow()
                
                chunks.append(MongoDbChunkModel(**chunk_doc))
            
            self.logger.info(f"✅ Returning {len(chunks)} chunks out of {total} total for document {document_id}")
            return chunks, total
            
        except Exception as e:
            self.logger.error(f"❌ Error getting document chunks: {e}")
            return [], 0

    async def get_chunks_hybrid(
        self,
        document_id: str,
        user_id: str,
        page: int = 1,
        limit: int = 10,
        namespace: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get document chunks using True Hybrid approach.
        
        Strategy:
        1. Query MongoDB for schema + pagination (fast, indexed)
        2. Extract vector_ids from MongoDB results
        3. Batch fetch text from Milvus using vector_ids
        4. Merge text back into chunks
        
        Performance:
        - MongoDB query: ~10ms (indexed)
        - Milvus batch fetch: ~50-80ms (network + DB)
        - Merge operation: ~1ms
        - Total: ~65-95ms (6-9x slower than MongoDB-only)
        
        Args:
            document_id: Document ID to fetch
            user_id: User ID for namespace
            page: Page number (1-based)
            limit: Chunks per page
            namespace: Override namespace (optional)
        
        Returns:
            (chunks_with_text, total_count)
        """
        try:
            # Step 1: MongoDB query for schema (fast, indexed)
            skip = (page - 1) * limit
            query = {"document_id": document_id, "user_id": user_id}
            
            # Fetch chunks WITHOUT text (lightweight)
            cursor = self.collection.find(query).skip(skip).limit(limit).sort("chunk_index", 1)
            chunks = await cursor.to_list(length=None)
            
            if not chunks:
                self.logger.info(f"[{document_id}] No chunks found in MongoDB")
                return [], 0
            
            # Get total count for pagination
            total_count = await self.collection.count_documents(query)
            
            # Step 2: Extract vector_ids
            vector_ids = []
            chunk_map = {}  # Map vector_id → chunk
            
            for chunk in chunks:
                vector_id = chunk.get("vector_id")
                if not vector_id:
                    # Fallback for legacy chunks without vector_id
                    vector_id = self._generate_vector_id(document_id, chunk["chunk_index"])
                    self.logger.warning(f"[{document_id}] Legacy chunk missing vector_id: chunk_index={chunk['chunk_index']}")
                
                vector_ids.append(vector_id)
                chunk_map[vector_id] = chunk
            
            self.logger.info(f"[{document_id}] 🔄 Hybrid fetch: {len(vector_ids)} chunks from MongoDB, fetching text from Milvus...")
            
            # Step 3: Batch fetch from Milvus (network call)
            try:
                # Build filter to fetch specific vectors by ID
                # Milvus filter: id in [id1, id2, ...]
                ids_str = '", "'.join(vector_ids)
                filter_expr = f'id in ["{ids_str}"]'
                
                # Fetch vectors from Milvus with output fields including text
                self.logger.debug(f"[{document_id}] Fetching {len(vector_ids)} vectors from Milvus")
                
                # Use query with filter to get vectors
                # Use a fresh (non-singleton) connection for query operations
                from config.milvus_config import create_new_milvus_client
                _query_client = create_new_milvus_client()
                try:
                    fetch_results = _query_client.query(
                        collection_name=self.collection_name,
                        filter=filter_expr,
                        output_fields=["id", "text", "user_id", "document_id"]
                    )
                finally:
                    try:
                        _query_client.close()
                    except Exception:
                        pass
                
                # Step 4: Create mapping of vector_id -> text
                vector_text_map = {result["id"]: result.get("text", "") for result in fetch_results}
                
                # Step 5: Merge text back into chunks
                vectors_found = 0
                vectors_missing = 0
                
                for chunk in chunks:
                    vector_id = chunk.get("vector_id")
                    if not vector_id:
                        vector_id = self._generate_vector_id(document_id, chunk["chunk_index"])
                    
                    # Get text from Milvus response
                    if vector_id in vector_text_map:
                        chunk["content"] = vector_text_map[vector_id]
                        vectors_found += 1
                    else:
                        # Vector not found in Milvus
                        chunk["content"] = "[Content not found in Milvus]"
                        vectors_missing += 1
                        self.logger.error(f"[{document_id}] Vector not found: {vector_id}")
                    
                    # Convert ObjectId to string for JSON serialization
                    if "_id" in chunk and chunk["_id"]:
                        chunk["_id"] = str(chunk["_id"])
                
                self.logger.info(f"[{document_id}] ✅ Hybrid fetch complete: {vectors_found} found, {vectors_missing} missing")
                
            except Exception as milvus_error:
                self.logger.error(f"[{document_id}] Milvus fetch failed: {milvus_error}")
                # Fallback: Return chunks without text
                for chunk in chunks:
                    chunk["content"] = f"[Error fetching from Milvus: {str(milvus_error)}]"
                    if "_id" in chunk and chunk["_id"]:
                        chunk["_id"] = str(chunk["_id"])
            
            return chunks, total_count
            
        except Exception as e:
            self.logger.error(f"[{document_id}] Hybrid fetch failed: {e}")
            raise

    async def search_documents(
        self,
        user_id: str,
        search_query: str,
        folder_id: Optional[str] = None,
        page: int = 1,
        per_page: int = 20
    ) -> Tuple[List[DocumentMetadataModel], int]:
        """Search documents by query text"""
        try:
            await self._ensure_indexes()
            
            # Build search query using text search and regex
            match_query = {
                "user_id": user_id,
                "chunk_index": 0,  # Only get metadata from first chunk
                # Exclude enterprise uploads from regular search results (same as list_documents_for_device)
                "is_enterprise": {
                    "$ne": True
                },
                "$or": [
                    {"is_enterprise": {"$exists": False}},
                    {"is_enterprise": False}
                ],
                "$and": [
                    {
                        "$or": [
                            {"metadata.source": {"$regex": search_query, "$options": "i"}},
                            {"metadata.topic": {"$regex": search_query, "$options": "i"}},
                            {"metadata.text": {"$regex": search_query, "$options": "i"}}  # ✅ BREAKING CHANGE: Search in metadata
                        ]
                    }
                ]
            }
            
            if folder_id:
                match_query["folder_id"] = folder_id
            
            # DEBUG: Log the search query
            print(f"🔍 SEARCH DEBUG: user_id={user_id}, search_query='{search_query}', folder_id={folder_id}")
            print(f"🔍 SEARCH DEBUG: match_query={match_query}")
            
            # DEBUG: First check if any documents exist for this user/folder without search
            base_query = {
                "user_id": user_id,
                "chunk_index": 0,
                "is_enterprise": {
                    "$ne": True
                }
            }
            if folder_id:
                base_query["folder_id"] = folder_id
            
            total_base = await self.collection.count_documents(base_query)
            print(f"🔍 SEARCH DEBUG: total documents in folder (no search) = {total_base}")
            
            # Get total count
            total = await self.collection.count_documents(match_query)
            print(f"🔍 SEARCH DEBUG: total matching documents = {total}")
            
            # Get paginated results
            skip = (page - 1) * per_page
            cursor = self.collection.find(match_query).sort("created_at", -1).skip(skip).limit(per_page)
            
            documents = []
            async for doc in cursor:
                # Handle ObjectId conversion for _id field
                if "_id" in doc and doc["_id"]:
                    doc["_id"] = str(doc["_id"])
                    
                # Ensure datetime fields have proper defaults if missing
                created_at = doc.get("created_at") or datetime.utcnow()
                updated_at = doc.get("updated_at") or datetime.utcnow()
                
                metadata = DocumentMetadataModel(
                    document_id=doc["document_id"],
                    file_type=doc["file_type"],
                    total_pages=doc.get("total_pages", 1),  # Use correct field name
                    total_chunks=doc.get("total_chunks", 1),  # Use correct field name
                    chunk_size=doc.get("chunk_size", 1),
                    file_size=doc.get("file_size", 0),
                    user_id=doc["user_id"],
                    folder_id=doc.get("folder_id", "documents"),
                    topic_or_filename=doc.get("topic_or_filename"),
                    processing_status=doc.get("processing_status", "completed"),
                    extracted_metadata=doc.get("extracted_metadata", {}),
                    created_at=created_at,
                    updated_at=updated_at
                )
                documents.append(metadata)
            
            return documents, total
            
        except Exception as e:
            self.logger.error(f"❌ Error searching documents: {e}")
            return [], 0

    # async def search_document_chunks(
    #     self,
    #     document_id: str,
    #     search_query: str,
    #     page: int = 1,
    #     per_page: int = 20
    # ) -> Tuple[List[MongoDbChunkModel], int]:
    #     """
    #     Search within a specific document's chunks using MongoDB regex.
    #     This provides a "Ctrl+F" style search within a document.
    #     
    #     Args:
    #         document_id: Document to search within
    #         search_query: Text to search for
    #         page: Page number
    #         per_page: Results per page
    #         
    #     Returns:
    #         Tuple of (list of chunks, total count)
    #     """
    #     try:
    #         await self._ensure_indexes()
    #         
    #         # Build search query for this specific document
    #         match_query = {
    #             "document_id": document_id,
    #             # Regex search on metadata.text (where chunk text is stored)
    #             "metadata.text": {"$regex": search_query, "$options": "i"}
    #         }
    #         
    #         # Get total matching chunks
    #         total = await self.collection.count_documents(match_query)
    #         
    #         # Get paginated results
    #         skip = (page - 1) * per_page
    #         cursor = self.collection.find(match_query).sort("chunk_index", 1).skip(skip).limit(per_page)
    #         
    #         chunks = []
    #         async for chunk_doc in cursor:
    #             # Handle ObjectId conversion
    #             if "_id" in chunk_doc and chunk_doc["_id"]:
    #                 chunk_doc["_id"] = str(chunk_doc["_id"])
    #             
    #             # Ensure datetime fields
    #             if "created_at" not in chunk_doc:
    #                 chunk_doc["created_at"] = datetime.utcnow()
    #             
    #             # Convert content_length to int if needed (handled by model)
    #             if "content_length" not in chunk_doc:
    #                  chunk_doc["content_length"] = len(chunk_doc.get("chunk_text", ""))
    #                  
    #             chunks.append(MongoDbChunkModel(**chunk_doc))
    #         
    #         return chunks, total
    #         
    #     except Exception as e:
    #         self.logger.error(f"❌ Error searching document chunks: {e}")
    #         return [], 0

    async def delete_document(self, document_id: str, user_id: str = None) -> bool:
        """
        Delete a document from all storage locations (MongoDB, Milvus, S3)
        API compatibility method that performs complete deletion with security check
        """
        metadata = None
        # If user_id is provided, verify ownership before deletion
        if user_id:
            metadata = await self.get_document_metadata(document_id)
            if not metadata:
                self.logger.warning(f"🗑️ Document {document_id} not found for deletion")
                return False
            
            if metadata.user_id != user_id:
                self.logger.error(f"🚫 Access denied: User {user_id} cannot delete document {document_id} owned by {metadata.user_id}")
                return False
                
        return await self.delete_document_complete(document_id, metadata=metadata)

    async def delete_document_complete(self, document_id: str, metadata=None) -> bool:
        """
        Complete document deletion from MongoDB, Milvus, and S3
        Enhanced version that handles all storage locations
        """
        try:
            # Get document metadata (reuse if already fetched by caller)
            if metadata is None:
                metadata = await self.get_document_metadata(document_id)
            if not metadata:
                self.logger.warning(f"🗑️ Document {document_id} metadata not found")
                return False
            
            deleted_locations = []
            
            # 1. Delete from MongoDB
            result = await self.collection.delete_many({"document_id": document_id})
            if result.deleted_count > 0:
                deleted_locations.append(f"MongoDB ({result.deleted_count} chunks)")
            
            # 2. Delete from Milvus (regular document chunks)
            try:
                # Check if document has enterprise metadata to use correct namespace
                is_enterprise = getattr(metadata, 'is_enterprise', False)
                document_details = getattr(metadata, 'document_details', None)
                department = getattr(metadata, 'department', None)  # Get department from metadata if available
                milvus_deleted = await self.delete_from_milvus(document_id, metadata.user_id, is_enterprise, document_details, department)
                if milvus_deleted:
                    deleted_locations.append("Milvus (document embeddings)")
            except Exception as milvus_error:
                self.logger.warning(f"🗑️ Milvus deletion failed: {milvus_error}")
            
            # 2b. Delete KG embeddings from Milvus (document-specific)
            # Note: We only delete Milvus KG embeddings, NOT graph nodes
            # Graph nodes are shared across documents (e.g., same court/act referenced by multiple cases)
            try:
                from graph.embedding_service import KGEmbeddingService
                kg_service = KGEmbeddingService()
                kg_deleted_count = await kg_service.delete_document_embeddings(
                    user_id=metadata.user_id,
                    document_id=document_id
                )
                if kg_deleted_count > 0:
                    deleted_locations.append(f"Milvus (KG: {kg_deleted_count} entities)")
                    self.logger.info(f"🗑️ ✅ Deleted {kg_deleted_count} KG embeddings for document {document_id}")
            except Exception as kg_error:
                self.logger.warning(f"🗑️ KG embedding deletion failed: {kg_error}")
            
            # 3. Delete from S3 using files_service
            try:
                # ✅ Get S3 URL from files collection (single source of truth)
                from services.files_service import FilesService
                files_service = FilesService(self.client, self.db.name)
                
                file_resources = await files_service.get_file_resources(
                    file_id=metadata.document_id,
                    user_id=metadata.user_id
                )
                
                if file_resources and file_resources.get("s3_url"):
                    from document_manager import delete_file_from_s3_storage
                    from utils import get_user_id
                    
                    unique_code = get_user_id(metadata.user_id)
                    s3_url = file_resources["s3_url"]
                    s3_deleted = delete_file_from_s3_storage(s3_url, unique_code)
                    
                    if s3_deleted:
                        deleted_locations.append("S3")
                        self.logger.info(f"🗑️ ✅ Deleted S3 object: {s3_url}")
                    else:
                        self.logger.warning(f"🗑️ ⚠️ S3 object deletion failed or not found: {s3_url}")
                    
                    # 4. Delete from files collection registry
                    try:
                        registry_deleted = await files_service.delete_file(
                            file_id=metadata.document_id,
                            user_id=metadata.user_id
                        )
                        if registry_deleted:
                            deleted_locations.append("Files Registry")
                            self.logger.info(f"🗑️ ✅ Deleted file from registry: {metadata.document_id}")
                    except Exception as registry_error:
                        self.logger.warning(f"🗑️ Files registry deletion failed: {registry_error}")
                else:
                    # Fallback: reconstruct S3 path from document metadata
                    self.logger.warning(f"🗑️ ⚠️ No S3 URL in files collection - attempting S3 deletion via path reconstruction")
                    try:
                        from document_manager import delete_document_from_s3_storage
                        fallback_deleted = delete_document_from_s3_storage(
                            document_id=metadata.document_id,
                            user_id=metadata.user_id,
                            file_type=metadata.file_type or "",
                            topic_or_filename=metadata.topic_or_filename,
                            is_enterprise=getattr(metadata, 'is_enterprise', False),
                            entity_id=getattr(metadata, 'entity_id', None),
                            folder_id=metadata.folder_id
                        )
                        if fallback_deleted:
                            deleted_locations.append("S3 (reconstructed path)")
                            self.logger.info(f"🗑️ ✅ Deleted S3 object via path reconstruction for {metadata.document_id}")
                    except Exception as fallback_err:
                        self.logger.warning(f"🗑️ ⚠️ S3 fallback deletion also failed: {fallback_err}")
                    
                    # Still clean up files registry if it exists
                    try:
                        registry_deleted = await files_service.delete_file(
                            file_id=metadata.document_id,
                            user_id=metadata.user_id
                        )
                        if registry_deleted:
                            deleted_locations.append("Files Registry")
                    except Exception:
                        pass
                    
            except Exception as s3_error:
                self.logger.warning(f"🗑️ S3 deletion failed: {s3_error}")
            
            # 5. Delete structured-file schema metadata (Excel/JSON/CSV uploads)
            try:
                from document_manager import _delete_document_structured_metadata
                cleanup_result = await _delete_document_structured_metadata(document_id, metadata.user_id)
                if cleanup_result.get('deleted_count', 0) > 0:
                    deleted_locations.append(f"structured_file_metadata ({cleanup_result['deleted_count']} entries)")
                    self.logger.info(f"🗑️ ✅ Deleted {cleanup_result['deleted_count']} structured metadata entries for document {document_id}")
            except Exception as cleanup_error:
                self.logger.warning(f"🗑️ Structured metadata cleanup failed (non-blocking): {cleanup_error}")
            
            self.logger.info(f"🗑️ Document {document_id} deletion complete. Removed from: {', '.join(deleted_locations)}")
            return result.deleted_count > 0
            
        except Exception as e:
            self.logger.error(f"❌ Error deleting document: {e}")
            return False

    async def list_documents_for_device(
        self,
        user_id: str,
        folder_id: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        team_id: Optional[str] = None
    ) -> Tuple[List[DocumentMetadataModel], int]:
        """List documents for a device with pagination and optional team filtering"""
        try:
            await self._ensure_indexes()
            
            # Build query based on team_id
            if team_id:
                # Team workspace: Show only team documents
                match_query = {
                    "team_id": team_id,
                    "chunk_index": 0
                }
            else:
                # Personal workspace: Show user's personal documents (no team_id or null team_id)
                match_query = {
                    "user_id": user_id, 
                    "chunk_index": 0,
                    "$or": [
                        {"team_id": {"$exists": False}},
                        {"team_id": None}
                    ]
                }
            
            if folder_id:
                match_query["folder_id"] = folder_id
            
            # Debug logging to trace the query
            self.logger.info(f"📊 list_documents_for_device query: {match_query}")
            
            # Get total count
            total_pipeline = [{"$match": match_query}, {"$count": "total"}]
            total_result = await self.collection.aggregate(total_pipeline).to_list(length=None)
            total = total_result[0]["total"] if total_result else 0
            
            # Get paginated results
            skip = (page - 1) * per_page
            pipeline = [
                {"$match": match_query},
                {"$sort": {"created_at": -1}},
                {"$skip": skip},
                {"$limit": per_page}
            ]
            
            documents = []
            cursor = self.collection.aggregate(pipeline)
            async for doc in cursor:
                # Handle ObjectId conversion for _id field
                if "_id" in doc and doc["_id"]:
                    doc["_id"] = str(doc["_id"])
                    
                # Ensure datetime fields have proper defaults if missing
                created_at = doc.get("created_at") or datetime.utcnow()
                updated_at = doc.get("updated_at") or datetime.utcnow()
                
                # Get metadata dict for fallback lookups
                doc_metadata = doc.get("metadata", {})
                
                # Safe field access with fallback to metadata
                file_type = doc.get("file_type") or doc_metadata.get("file_type", "unknown")
                topic_or_filename = doc.get("topic_or_filename") or doc_metadata.get("topic_or_filename", "unknown")
                
                metadata = DocumentMetadataModel(
                    document_id=doc["document_id"],
                    file_type=file_type,
                    total_pages=doc.get("total_pages", 1),
                    total_chunks=doc.get("total_chunks", 1),
                    chunk_size=doc.get("chunk_size", 1),
                    file_size=doc.get("file_size", 0),
                    user_id=doc["user_id"],
                    folder_id=doc.get("folder_id", "documents"),
                    topic_or_filename=topic_or_filename,
                    processing_status=doc.get("processing_status", "completed"),
                    extracted_metadata=doc.get("extracted_metadata", {}),
                    created_at=created_at,
                    updated_at=updated_at
                )
                documents.append(metadata)
            
            return documents, total
            
        except Exception as e:
            self.logger.error(f"❌ Error listing documents: {e}")
            return [], 0

    async def list_enterprise_documents_for_device(
        self,
        user_id: str,
        page: int = 1,
        per_page: int = 20,
        search_query: Optional[str] = None,
        entity_id: Optional[str] = None
    ) -> Tuple[List[DocumentMetadataModel], int]:
        """List enterprise documents for a device with pagination"""
        try:
            await self._ensure_indexes()
            
            match_query = {
                "user_id": user_id, 
                "chunk_index": 0,
                # Include only enterprise uploads
                "is_enterprise": True
            }
            
            # Add entity filtering if provided
            if entity_id == 'none':
                match_query["entity_id"] = {"$in": [None, "none"]}
            elif entity_id:
                match_query["entity_id"] = entity_id
            
            # Add search functionality if provided
            if search_query:
                search_regex = {"$regex": search_query, "$options": "i"}
                match_query["$or"] = [
                    {"topic_or_filename": search_regex}
                ]
            
            # Debug logging to trace the query
            self.logger.info(f"🏢 list_enterprise_documents_for_device query: {match_query}")
            
            # Get total count
            total_pipeline = [{"$match": match_query}, {"$count": "total"}]
            total_result = await self.collection.aggregate(total_pipeline).to_list(length=None)
            total = total_result[0]["total"] if total_result else 0
            
            # Get paginated results
            skip = (page - 1) * per_page
            pipeline = [
                {"$match": match_query},
                {"$sort": {"created_at": -1}},
                {"$skip": skip},
                {"$limit": per_page}
            ]
            
            results = await self.collection.aggregate(pipeline).to_list(length=None)
            
            # Convert to DocumentMetadataModel
            documents = []
            for doc in results:
                created_at = doc.get("created_at")
                updated_at = doc.get("updated_at")
                
                # Convert to datetime objects if they're strings
                if isinstance(created_at, str):
                    try:
                        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    except (ValueError, TypeError) as exc:
                        # Do NOT fabricate a timestamp. A stored value that won't
                        # parse is real data corruption; stamping utcnow() would
                        # make a corrupt doc look freshly created and silently
                        # break incremental sync and date sorting.
                        raise ValueError(
                            f"Corrupt created_at {created_at!r} on document "
                            f"{doc.get('_id') or doc.get('document_id')!r}"
                        ) from exc
                elif created_at is None:
                    created_at = datetime.utcnow()

                if isinstance(updated_at, str):
                    try:
                        updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                    except (ValueError, TypeError) as exc:
                        raise ValueError(
                            f"Corrupt updated_at {updated_at!r} on document "
                            f"{doc.get('_id') or doc.get('document_id')!r}"
                        ) from exc
                elif updated_at is None:
                    updated_at = created_at
                
                # Get metadata dict for fallback lookups
                doc_metadata = doc.get("metadata", {})
                
                # Safe field access with fallback to metadata
                file_type = doc.get("file_type") or doc_metadata.get("file_type", "unknown")
                topic_or_filename = doc.get("topic_or_filename") or doc_metadata.get("topic_or_filename", "unknown")
                
                metadata = DocumentMetadataModel(
                    document_id=doc.get("document_id", str(doc.get("_id", ""))),
                    file_type=file_type,
                    total_pages=doc.get("total_pages", 0),
                    total_chunks=doc.get("total_chunks", 0),
                    chunk_size=doc.get("chunk_size", 0),
                    user_id=doc.get("user_id", ""),
                    folder_id=doc.get("folder_id"),
                    processing_status=doc.get("processing_status", "completed"),
                    topic_or_filename=topic_or_filename,
                    file_size=doc.get("file_size", 0),
                    extracted_metadata=doc.get("extracted_metadata", {}),
                    created_at=created_at,
                    updated_at=updated_at
                )
                documents.append(metadata)
            
            self.logger.info(f"🏢 Found {len(documents)} enterprise documents (total: {total})")
            return documents, total
            
        except Exception as e:
            self.logger.error(f"❌ Error listing enterprise documents: {e}")
            return [], 0
    
    # =================== HELPER METHODS ===================
    
    # def _extract_topic_category(self, topic: str, text: str) -> str:
    #     """Extract topic category for better organization"""
    #     topic_lower = topic.lower()
    #     if any(word in topic_lower for word in ['meeting', 'notes', 'agenda']):
    #         return 'meeting'
    #     elif any(word in topic_lower for word in ['report', 'analysis', 'summary']):
    #         return 'report'
    #     elif any(word in topic_lower for word in ['manual', 'guide', 'documentation']):
    #         return 'documentation'
    #     else:
    #         return 'document'

    # def _extract_page_number_from_chunk(self, chunk_text: str) -> Optional[int]:
    #     """Extract page number from chunk text if available"""
    #     import re
    #     page_match = re.search(r'\[Page (\d+)\]', chunk_text)
    #     if page_match:
    #         return int(page_match.group(1))
    #     return None

    # async def _store_vectors_in_Milvus(self, vectors: List[Dict], user_id: str) -> int:
    #     """Store vectors in Milvus with error handling"""
    #     try:
    #         if not vectors:
    #             return 0
                
    #         # Use the enhanced service's optimized upsert method
    #         return await self.upsert_to_Milvus_optimized(vectors, user_id, "batch_processing")
            
    #     except Exception as e:
    #         self.logger.error(f"❌ Failed to store vectors in Milvus: {e}")
    #         return 0

    # ====================== PARALLEL PROCESSING METHODS ======================
    # These methods keep MongoDB and Milvus operations strictly separate for parallel processing
    
    async def create_embeddings_and_store_Milvus_only(
        self,
        document_id: str,
        text: str,
        topic: str,
        user_id: str,
        utc_date: str,
        file_metadata: Optional[Dict] = None,
        folder_id: Optional[str] = None,
        include_topic_header: bool = False,
        is_enterprise: bool = False,
        entity_id: Optional[str] = None,
        entity_name: Optional[str] = None,
        document_details: Optional[str] = None,
        department: Optional[str] = None,
        store_chunks_in_mongodb: bool = True,
        team_id: Optional[str] = None
    ) -> Dict:
        """
        Milvus-only embedding creation and storage for parallel processing.
        Uses enhanced MilvusChunkModel with citation fields.
        DOES NOT touch MongoDB - strictly Milvus operations only.
        
        Args:
            document_id: Unique document identifier
            text: Document text content
            topic: Document topic/title
            user_id: User device identifier
            utc_date: Upload timestamp
            file_metadata: Complete file metadata including page_count
            folder_id: Optional folder identifier
            include_topic_header: Whether to prepend topic as header (True for audio/video, False for documents)
            
        Returns:
            Dict with vectors_created, chunks, metas, base_id, file_type, vector_ids
        """
        start_time = time.time()
        
        try:
            if not text.strip():
                self.logger.warning(f"[{document_id}] No text provided for Milvus embedding")
                return {'vectors_created': 0, 'chunks': [], 'metas': [], 'base_id': document_id, 'vector_ids': []}

            self.logger.info(f"[{document_id}] 🚀 Milvus-only embedding creation: {len(text)} characters")
            
            # Extract file metadata for citation fields
            file_type = file_metadata.get("file_type", "unknown") if file_metadata else "unknown"
            total_pages = file_metadata.get("page_count", 1) if file_metadata else 1
            # Use original filename from metadata, fallback to topic
            original_filename = file_metadata.get("filename", topic) if file_metadata else topic
            
            # Use the original filename as-is (no parsing or modification)
            filename = original_filename
            
            # Enhanced chunking with citation fields - use topic for source as well
            # file_type is already without dot
            source_info = {
                'file_type': file_type,
                'upload_date': utc_date,
                'folder_id': folder_id,
                'total_pages': total_pages,
                'display_name': f"{topic}.{file_type}" if topic else filename,
                'filename': filename
            }
            
            # 🏢 ENTERPRISE FIX: For enterprise entity uploads, use entity_name + document_details as effective topic
            # This allows searching by descriptions like "Mary Johnson - Medical Report" instead of filename
            # Entity name is REQUIRED for enterprise entity uploads
            effective_topic = topic
            if is_enterprise and entity_id and entity_name and document_details and document_details.strip():
                # Combine entity_name with document_details (remove filename from topic for entity uploads)
                effective_topic = f"{entity_name.strip()} - {document_details.strip()}"
                self.logger.info(f"[{document_id}] 🏢 Enterprise entity upload: Using entity-based topic for chunking: '{effective_topic}'")
            
            # Use intelligent chunking to automatically choose best strategy
            chunks, metas = await self.intelligent_chunking(
                text=text,
                topic=effective_topic,
                doc_type=file_type,
                source_info=source_info,
                include_topic_header=include_topic_header,
                user_id=user_id
            )
            self.logger.info(f"[{document_id}] Created {len(chunks)} chunks for Milvus")
            # 🏢 ENTERPRISE FIX: For enterprise entity uploads, use entity_name + document_details as effective topic
            if not chunks:
                return {'vectors_created': 0, 'chunks': [], 'metas': [], 'base_id': document_id, 'vector_ids': []}

            # ✅ SERVER-SIDE BM25: Only generate dense embeddings
            # Sparse vectors are auto-generated by Zilliz Cloud from the text field
            self.logger.info(f"[{document_id}] 🚀 Generating dense embeddings with structured metadata headers (sparse auto-generated by server)")
            embeddings = await self.generate_dense_embeddings_batch(chunks, effective_topic)
            self.logger.info(f"[{document_id}] ✅ Generated {len(embeddings)} dense embeddings with structured metadata headers")
            
            # 💳 CREDIT TRACKING: Deduct credits for embedding generation
            try:
                from middleware.credit_check_middleware import get_usage_service
                usage_service = get_usage_service()
                
                # Use original text length (more accurate than sum of chunks due to no overlap/trimming)
                total_characters = len(text)
                
                # Get user email (use user_id as fallback)
                user_email = user_id  # Assuming user_id is email; adjust if needed
                
                # Track embedding usage and deduct credits
                tracking_result = usage_service.track_embedding_usage(
                    user_id=user_id,
                    email=user_email,
                    total_characters=total_characters,
                    document_id=document_id,
                    chunk_count=len(chunks)
                )
                
                if tracking_result['success']:
                    cost = tracking_result['cost']
                    balance = tracking_result.get('balance_after', 0)  # Buffer path doesn't return balance
                    tokens = tracking_result.get('cost_details', {}).get('estimated_tokens', 0)
                    
                    if tracking_result.get('buffered'):
                        self.logger.info(
                            f"[{document_id}] 💳 Embedding credits buffered: "
                            f"{cost:.4f} credits (~{tokens} tokens)"
                        )
                    else:
                        self.logger.info(
                            f"[{document_id}] 💳 Embedding credits deducted: "
                            f"{cost:.4f} credits (~{tokens} tokens) | Balance: {balance:.2f} credits"
                        )
                else:
                    # Insufficient credits - should not happen if pre-check was done
                    self.logger.error(
                        f"[{document_id}] ❌ Embedding credit tracking failed: {tracking_result.get('error')}"
                    )
                    raise HTTPException(
                        status_code=402,
                        detail=f"Insufficient credits for embedding generation. Required: {tracking_result.get('cost', 0):.2f} credits"
                    )
            except ImportError as e:
                self.logger.warning(f"[{document_id}] ⚠️ Could not import usage tracking service: {e}")
            except HTTPException:
                raise  # Re-raise HTTP exceptions
            except Exception as e:
                self.logger.error(f"[{document_id}] ⚠️ Embedding credit tracking error: {e}")
                # Continue processing even if tracking fails (non-blocking)
            
            # Build hybrid vectors for Milvus with unified metadata schema
            vectors = []
            vector_ids = []
            base_id = document_id
            
            # Determine source_type based on file_type
            # This tells orchestrator which MongoDB collection to fetch text from
            if file_type == 'audio':
                source_type = 'audio'
            elif file_type == 'video':
                source_type = 'video'
            elif file_type == 'notes':
                source_type = 'note'
            else:
                source_type = 'document'
            
            for idx, embedding_values in enumerate(embeddings):
                if not isinstance(embedding_values, list):
                    continue
                
                chunk_meta = metas[idx] if idx < len(metas) else {}
                vector_id = f"{base_id}_chunk_{idx:04d}"
                chunk_id = f"{document_id}_{idx}"  # For MongoDB correlation
                vector_ids.append(vector_id)
                
                # ✅ SERVER-SIDE BM25: No sparse vector needed here
                # Zilliz Cloud auto-generates sparse_vector from the text field
                
                # Create unified metadata using breaking change schema (no legacy support)
                # BREAKING CHANGE: Do NOT include text in Milvus metadata
                vector_metadata = UnifiedMetadataSchema.create_full_metadata(
                    document_id=document_id,
                    user_id=user_id,
                    chunk_index=idx,
                    total_chunks=len(chunks),
                    text="",  # BREAKING CHANGE: Text stored in MongoDB, not Milvus
                    topic_or_filename=topic,
                    file_type=file_type,
                    created_at=utc_date,
                    page_number=int(float(chunk_meta.get('page_number', 1))),
                    paragraph_number=chunk_meta.get('paragraph_number', idx + 1),
                    folder_id=folder_id if not is_enterprise else None,  # No folder_id for enterprise
                    is_enterprise=is_enterprise,
                    entity_id=entity_id,
                    department=department
                )
                
                # Add source_type and chunk_id for text routing (BREAKING CHANGE)
                vector_metadata['source_type'] = source_type
                vector_metadata['chunk_id'] = chunk_id
                
                # Merge legal metadata fields from chunk_meta into vector_metadata
                # Legal metadata fields: case_number, appellant, respondent, court, jurisdiction, judges, judgment_date, etc.
                legal_metadata_fields = [
                    'case_number', 'appellant', 'respondent', 'court', 'jurisdiction', 
                    'judges', 'judgment_date', 'section_number', 'section_statute', 
                    'section_heading', 'legal_citations', 'case_type', 'bench_strength'
                ]
                for field in legal_metadata_fields:
                    if field in chunk_meta:
                        vector_metadata[field] = chunk_meta[field]
                
                # Create hybrid vector with both dense and sparse components
                vector_data = {
                    "id": vector_id,
                    "values": embedding_values,
                    "metadata": vector_metadata
                }
                
                # ✅ SERVER-SIDE BM25: No sparse_values needed
                # Zilliz Cloud automatically generates sparse vectors from the text field
                    
                vectors.append(vector_data)
            
            # Store hybrid vectors in Milvus with folder_id and entity_id
            vectors_created = await self.upsert_to_milvus_hybrid_optimized(
                vectors, user_id, document_id, folder_id, is_enterprise, entity_id, document_details, department
            )
            
            # Store chunks in MongoDB if requested (documents only, not audio/video/notes)
            if vectors_created > 0 and store_chunks_in_mongodb:
                self.logger.info(f"[{document_id}] 📥 Storing {len(chunks)} chunks in MongoDB document_chunked collection")
                await self.store_mongodb_chunks_enhanced(
                    document_id=document_id,
                    text=text,
                    topic=topic,
                    user_id=user_id,
                    file_metadata=file_metadata,
                    folder_id=folder_id,
                    is_enterprise=is_enterprise,
                    entity_id=entity_id,
                    department=department,
                    team_id=team_id
                )
            
            # Update has_vectors field in MongoDB chunks after successful vector creation
            # Skip for audio/video - they don't store chunks in document_chunked collection
            if vectors_created > 0 and store_chunks_in_mongodb:
                try:
                    await self.collection.update_many(
                        {
                            "document_id": document_id,
                            "user_id": user_id,
                            "is_enterprise": is_enterprise
                        },
                        {
                            "$set": {
                                "has_vectors": True,
                                "updated_at": datetime.utcnow()
                            }
                        }
                    )
                    self.logger.info(f"[{document_id}] ✅ Updated has_vectors=True for {vectors_created} vectors in MongoDB")
                except Exception as e:
                    self.logger.warning(f"[{document_id}] ⚠️ Failed to update has_vectors in MongoDB: {e}")
            elif vectors_created > 0:
                self.logger.info(f"[{document_id}] ⏭️ Skipping MongoDB chunk storage (audio/video use separate collections)")
            
            # Store vector mapping using enhanced MilvusChunkModel
            first_page = metas[0].get('page_number', 1) if metas else 1
            await self.store_vector_mapping(
                document_id=document_id,
                user_id=user_id,
                vector_ids=vector_ids,
                topic=topic,
                file_type=file_type,
                folder_id=folder_id,
                page_number=first_page,
                paragraph_number=1,
                chunk_index=0,
                total_chunks=len(chunks)
            )
            
            total_time = time.time() - start_time
            self.logger.info(f"[{document_id}] ✅ Milvus-only processing complete: {total_time:.3f}s, {vectors_created} vectors")
            
            return {
                'vectors_created': vectors_created,
                'chunks': chunks,
                'metas': metas,
                'base_id': base_id,
                'file_type': file_type,
                'vector_ids': vector_ids,
                'total_pages': total_pages,
                'processing_time': total_time,
                'unified_metadata': True  # Flag to indicate new schema
            }
            
        except Exception as e:
            self.logger.error(f"[{document_id}] ❌ Milvus-only processing failed: {e}")
            raise

    async def store_mongodb_chunks_enhanced(
        self,
        document_id: str,
        text: str,
        topic: str,
        user_id: str,
        file_metadata: Optional[Dict] = None,
        folder_id: Optional[str] = None,
        is_enterprise: bool = False,
        entity_id: Optional[str] = None,
        entity_name: Optional[str] = None,
        document_details: Optional[str] = None,
        department: Optional[str] = None,
        team_id: Optional[str] = None
    ) -> Dict:
        """
        MongoDB-only chunk storage for parallel processing.
        Uses enhanced MongoDbChunkModel with citation fields.
        DOES NOT touch Milvus - strictly MongoDB operations only.
        
        Args:
            document_id: Unique document identifier
            text: Document text content
            topic: Document topic/title
            user_id: User device identifier
            file_metadata: Complete file metadata including page_count
            folder_id: Optional folder identifier
            
        Returns:
            Dict with total_chunks, total_pages, status
        """
        start_time = time.time()
        
        try:
            await self._ensure_indexes()
            
            if not text.strip():
                self.logger.warning(f"[{document_id}] No text provided for MongoDB storage")
                return {'total_chunks': 0, 'total_pages': 0, 'status': 'failed'}

            self.logger.info(f"[{document_id}] 🗄️ MongoDB-only storage: {len(text)} characters")
            
            # Extract file metadata for citation fields
            file_type = file_metadata.get("file_type", "unknown") if file_metadata else "unknown"
            file_size = file_metadata.get("file_size", len(text.encode('utf-8'))) if file_metadata else len(text.encode('utf-8'))
            total_pages = file_metadata.get("page_count", 1) if file_metadata else 1

            display_label = topic or (file_metadata.get("filename") if file_metadata else document_id)

            # Enhanced chunking with citation fields - retain display context for UI
            source_info = {
                'file_type': file_type,
                'total_pages': total_pages,
                'display_name': display_label,
                'topic_or_filename': topic or display_label,
            }
            
            # Use intelligent chunking to automatically choose best strategy
            chunks, metas = await self.intelligent_chunking(
                text=text,
                topic=topic,
                doc_type=file_type,
                source_info=source_info,
                include_topic_header=False,  # Don't include header for document storage
                user_id=user_id
            )
            self.logger.info(f"[{document_id}] Created {len(chunks)} chunks for MongoDB")
            
            if not chunks:
                return {'total_chunks': 0, 'total_pages': total_pages, 'status': 'no_content'}
            
            # Create enhanced document chunks using MongoDbChunkModel
            bulk_operations = []
            
            for idx, chunk_text in enumerate(chunks):
                chunk_meta = metas[idx] if idx < len(metas) else {}
                
                # Calculate page range for this chunk
                # For simple text chunking, distribute pages across chunks evenly
                pages_per_chunk = max(1, total_pages // len(chunks))
                start_page = (idx * pages_per_chunk) + 1
                end_page = min(start_page + pages_per_chunk - 1, total_pages)
                
                # For the last chunk, ensure it covers all remaining pages
                if idx == len(chunks) - 1:
                    end_page = total_pages
                
                # Generate vector ID for cross-referencing
                vector_id = self._generate_vector_id(document_id, idx)
                
                # ALWAYS store text in MongoDB metadata (rollback from True Hybrid)
                text_location = "mongodb"
                chunk_text_for_metadata = chunk_text
                
                # Create enhanced MongoDbChunkModel using unified metadata schema
                # BREAKING CHANGE: Store chunk_id in metadata for Milvus correlation
                # Text is ALWAYS stored in MongoDB metadata (single source of truth)
                chunk_id = f"{document_id}_{idx}"
                
                unified_metadata = {
                    "chunk_id": chunk_id,  # For Milvus correlation
                    "text": chunk_text_for_metadata,  # Text content (only in metadata)
                    "created_at": datetime.utcnow().isoformat(),
                    "page_number": int(float(chunk_meta.get('page_number', start_page))),
                    "paragraph_number": chunk_meta.get('paragraph_number', idx + 1)
                }
                
                # Add enterprise fields to unified metadata BEFORE chunk_data creation
                if is_enterprise:
                    unified_metadata[MetadataConstants.IS_ENTERPRISE] = True
                    if entity_id:
                        unified_metadata[MetadataConstants.ENTITY_ID] = entity_id
                    if department:
                        unified_metadata[MetadataConstants.DEPARTMENT] = department
                
                # Create chunk data compatible with MongoDbChunkModel but using unified metadata
                # Root level keeps only essential query/indexing fields
                chunk_data = {
                    # Core indexing fields (required for queries)
                    "document_id": document_id,
                    "chunk_index": idx,
                    "user_id": user_id,
                    "folder_id": folder_id or "documents",
                    
                    # Cross-reference fields
                    "vector_id": vector_id,  # Milvus vector ID for correlation
                    "text_location": text_location,  # Always "mongodb"
                    
                    # Required page range fields for MongoDbChunkModel
                    "start_page": chunk_meta.get('start_page', start_page),
                    "end_page": chunk_meta.get('end_page', end_page),
                    "total_pages": end_page - start_page + 1,
                    
                    # Content statistics (not duplicate content)
                    "content_length": len(chunk_text),
                    "chunk_size": len(chunk_text),
                    "word_count": len(chunk_text.split()),
                    
                    # Database storage size (lightweight: char_count * 3 for UTF-8 estimate)
                    "db_size_bytes": len(chunk_text) * 3,  # UTF-8 average multiplier
                    
                    # Metadata with text always included
                    "metadata": unified_metadata,
                    
                    # Document metadata (not in unified_metadata)
                    "file_size": file_size,
                    "total_chunks": len(chunks),
                    
                    # Document listing fields at root level (for backward compatibility)
                    "file_type": file_type,  # Store file_type at root for document listing
                    "topic_or_filename": display_label,  # Use display_label directly for consistency
                    
                    # Processing metadata
                    "processing_status": "completed",
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    
                    # Storage metadata
                    "has_vectors": False,  # Will be updated separately by vector processing
                    "unified_schema": True  # Flag to indicate new schema usage
                }
                
                # Add enterprise fields from unified metadata
                if unified_metadata.get(MetadataConstants.IS_ENTERPRISE):
                    chunk_data["is_enterprise"] = True
                    if unified_metadata.get(MetadataConstants.ENTITY_ID):
                        chunk_data["entity_id"] = unified_metadata[MetadataConstants.ENTITY_ID]
                    if unified_metadata.get(MetadataConstants.DEPARTMENT):
                        chunk_data["department"] = unified_metadata[MetadataConstants.DEPARTMENT]
                
                # Add team_id for workspace filtering
                if team_id:
                    chunk_data["team_id"] = team_id
                
                chunk = MongoDbChunkModel(**chunk_data)
                chunk_dict = chunk.model_dump(by_alias=True)
                if "_id" in chunk_dict and chunk_dict["_id"] is None:
                    chunk_dict.pop("_id", None)
                
                from pymongo import ReplaceOne
                bulk_operations.append(
                    ReplaceOne(
                        {"document_id": document_id, "chunk_index": idx},
                        chunk_dict,
                        upsert=True
                    )
                )
            
            # Execute bulk MongoDB operations only
            # Initialize total_db_size before conditional block
            total_db_size = 0
            chunks_stored = 0
            
            if bulk_operations:
                result = await self.collection.bulk_write(bulk_operations, ordered=False)
                chunks_stored = result.upserted_count + result.modified_count
                self.logger.info(f"[{document_id}] ✅ Stored {chunks_stored} enhanced chunks in MongoDB with text in metadata")
                
            total_time = time.time() - start_time
            self.logger.info(f"[{document_id}] ✅ MongoDB storage complete: {total_time:.3f}s")
            
            # Knowledge graph creation removed (DGraph integration disabled)
            kg_success = False
            # self.logger.info(f"[{document_id}] ⚠️ Knowledge graph creation skipped (DGraph removed)")
            
            return {
                'total_chunks': len(chunks),
                'total_pages': total_pages,
                'status': 'completed',
                'chunks_stored': chunks_stored if bulk_operations else 0,
                'processing_time': total_time,
                'knowledge_graph_created': kg_success,
                'db_size_bytes': total_db_size  # Return for files collection storage
            }
            
        except Exception as e:
            self.logger.error(f"[{document_id}] ❌ MongoDB-only storage failed: {e}")
            return {'total_chunks': 0, 'total_pages': 0, 'status': 'failed', 'error': str(e)}

    async def store_text_content_in_chunks(
        self,
        text_content: str,
        document_id: str,
        filename: str,
        file_type: str,
        user_id: str,
        folder_id: Optional[str] = None,
        topic: str = "",
        file_size: int = 0
    ) -> Dict:
        """
        COMPATIBILITY METHOD: Redirects to store_mongodb_chunks_enhanced()
        This method exists to maintain compatibility with query.py calls.
        
        Args:
            text_content: Document text content
            document_id: Unique document identifier
            filename: Original filename
            file_type: File type (pdf, docx, txt, etc.)
            user_id: User device identifier
            folder_id: Optional folder identifier
            topic: Document topic/title (defaults to filename if empty)
            file_size: File size in bytes
            
        Returns:
            Dict with total_chunks, total_pages, status
        """
        # Use filename as topic if topic is empty
        actual_topic = topic or filename
        
        # Prepare file metadata for enhanced storage
        file_metadata = {
            'filename': filename,
            'file_type': file_type,
            'file_size': file_size,
            'page_count': 1  # Default for text content
        }
        
        # Call the enhanced storage method
        return await self.store_mongodb_chunks_enhanced(
            document_id=document_id,
            text=text_content,
            topic=actual_topic,
            user_id=user_id,
            file_metadata=file_metadata,
            folder_id=folder_id,
            is_enterprise=False,  # Compatibility method assumes personal data
            entity_id=None,
            document_details=None,
            department=None
        )
    
    async def get_chunk_by_vector_id(
        self,
        vector_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve chunk text and metadata by chunk_id (vector_id).
        
        BREAKING CHANGE: Text is stored in MongoDB, not Milvus.
        1. Fetch routing metadata from Milvus (source_type, document_id)
        2. Fetch text from MongoDB based on source_type
        
        Args:
            vector_id: Chunk ID (chunk_id in Milvus, used as vector_id in UI)
            user_id: User ID for filtering
            
        Returns:
            Dict with chunk text and metadata, or None if not found
        """
        try:
            self.logger.info(f"🔍 Retrieving chunk by chunk_id: {vector_id} for user: {user_id}")
            
            # Step 1: Fetch routing metadata from Milvus
            try:
                # Use a fresh (non-singleton) connection for query operations
                from config.milvus_config import create_new_milvus_client
                _query_client = create_new_milvus_client()
                try:
                    fetch_results = _query_client.query(
                        collection_name=self.collection_name,
                        filter=f'chunk_id == "{vector_id}" and user_id == "{user_id}"',
                        output_fields=["chunk_id", "source_type", "document_id", "topic_or_filename", "filename", "chunk_index", "file_type", "user_id"]
                    )
                finally:
                    try:
                        _query_client.close()
                    except Exception:
                        pass
                
                if not fetch_results or len(fetch_results) == 0:
                    self.logger.warning(f"❌ No chunk found in Milvus for chunk_id: {vector_id}")
                    return None
                
                vector_data = fetch_results[0]
                source_type = vector_data.get('source_type', 'document')  # Default to document for legacy data
                
                self.logger.info(f"📋 Found chunk in Milvus: {vector_id}, source_type={source_type}")
                
                # Step 2: Fetch text from MongoDB based on source_type
                chunk_text = await self._fetch_chunk_text_from_mongodb(vector_id, source_type)
                
                if not chunk_text:
                    self.logger.warning(f"⚠️ No text found in MongoDB for chunk_id: {vector_id}, source_type: {source_type}")
                    return None
                
                # Prepare response with chunk information
                chunk_info = {
                    "vector_id": vector_id,
                    "text": chunk_text,
                    "metadata": vector_data,
                    "document_id": vector_data.get('document_id', ''),
                    "topic_or_filename": vector_data.get('topic_or_filename', ''),
                    "filename": vector_data.get('filename', vector_data.get('topic_or_filename', '')),
                    "chunk_index": vector_data.get('chunk_index', 0),
                    "file_type": vector_data.get('file_type', ''),
                }
                
                self.logger.info(f"✅ Successfully retrieved chunk: {vector_id}, text length: {len(chunk_text)}")
                return chunk_info
                
            except Exception as milvus_error:
                self.logger.error(f"❌ Milvus query failed for vector ID {vector_id}: {milvus_error}")
                return None
            
            
        except Exception as e:
            self.logger.error(f"❌ Failed to retrieve chunk by vector ID {vector_id}: {e}")
            return None

    async def delete_document_with_cleanup(
        self,
        document_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Delete document and all associated resources (chunks, vectors, S3, KG embeddings).
        
        Args:
            document_id: Document identifier
            user_id: User identifier
            
        Returns:
            Dict with deletion status
        """
        try:
            self.logger.info(f"[{document_id}] 🗑️ Deleting document...")
            
            # Step 1: Get file record from files collection
            files_collection = self.db["files"]
            file_record = await files_collection.find_one({"_id": document_id, "user_id": user_id})
            
            if not file_record:
                self.logger.warning(f"[{document_id}] No file record found for deletion")
                return {
                    "success": False,
                    "document_id": document_id,
                    "reason": "not_found",
                    "chunks_deleted": 0
                }
            
            # Step 2: Delete chunks from MongoDB
            delete_result = await self.collection.delete_many({"document_id": document_id, "user_id": user_id})
            chunks_deleted = delete_result.deleted_count
            
            # Step 3: Delete vectors from Milvus
            try:
                # Delete from Milvus using document_id filter
                milvus_filter = f'document_id == "{document_id}" && user_id == "{user_id}"'
                # Refresh from singleton to avoid stale gRPC channel
                from config.milvus_config import get_milvus_client
                self.milvus_client = get_milvus_client()
                self.milvus_client.delete(
                    collection_name=self.collection_name,
                    filter=milvus_filter
                )
                self.logger.info(f"[{document_id}] ✅ Deleted vectors from Milvus")
            except Exception as milvus_error:
                self.logger.error(f"[{document_id}] ⚠️ Milvus deletion failed (non-blocking): {milvus_error}")
            
            # Step 4: Delete from milvus_chunks mapping collection
            try:
                await self.milvus_mapping_collection.delete_one({"document_id": document_id, "user_id": user_id})
                self.logger.info(f"[{document_id}] ✅ Deleted from milvus_chunks mapping")
            except Exception as mapping_error:
                self.logger.error(f"[{document_id}] ⚠️ Mapping deletion failed (non-blocking): {mapping_error}")
            
            # Step 5: Delete from files collection
            try:
                # Get S3 URL before deleting the file record
                s3_url = file_record.get("s3_url") if file_record else None
                
                await files_collection.delete_one({"_id": document_id, "user_id": user_id})
                self.logger.info(f"[{document_id}] ✅ Deleted from files collection")
            except Exception as files_error:
                s3_url = None
                self.logger.error(f"[{document_id}] ⚠️ Files collection deletion failed (non-blocking): {files_error}")
            
            # Step 6: Delete from S3
            try:
                if s3_url:
                    from document_manager import delete_file_from_s3_storage
                    from utils import get_user_id
                    unique_code = get_user_id(user_id)
                    s3_deleted = delete_file_from_s3_storage(s3_url, unique_code)
                    if s3_deleted:
                        self.logger.info(f"[{document_id}] ✅ Deleted S3 object: {s3_url}")
                    else:
                        self.logger.warning(f"[{document_id}] ⚠️ S3 object deletion failed or not found: {s3_url}")
                else:
                    # Fallback: try to get S3 URL from files_service
                    from services.files_service import FilesService
                    files_service = FilesService(self.client, self.db.name)
                    file_resources = await files_service.get_file_resources(file_id=document_id, user_id=user_id)
                    if file_resources and file_resources.get("s3_url"):
                        from document_manager import delete_file_from_s3_storage
                        from utils import get_user_id
                        unique_code = get_user_id(user_id)
                        delete_file_from_s3_storage(file_resources["s3_url"], unique_code)
                        self.logger.info(f"[{document_id}] ✅ Deleted S3 object (fallback): {file_resources['s3_url']}")
                    else:
                        self.logger.warning(f"[{document_id}] ⚠️ No S3 URL found - skipping S3 deletion")
            except Exception as s3_error:
                self.logger.warning(f"[{document_id}] ⚠️ S3 deletion failed (non-blocking): {s3_error}")
            
            # Step 7: Delete KG embeddings from Milvus
            try:
                from graph.embedding_service import KGEmbeddingService
                kg_service = KGEmbeddingService()
                kg_deleted_count = await kg_service.delete_document_embeddings(
                    user_id=user_id,
                    document_id=document_id
                )
                if kg_deleted_count > 0:
                    self.logger.info(f"[{document_id}] ✅ Deleted {kg_deleted_count} KG embeddings")
            except Exception as kg_error:
                self.logger.warning(f"[{document_id}] ⚠️ KG embedding deletion failed (non-blocking): {kg_error}")
            
            # Step 8: Delete structured-file schema metadata (Excel/JSON/CSV uploads)
            try:
                from document_manager import _delete_document_structured_metadata
                cleanup_result = await _delete_document_structured_metadata(document_id, user_id)
                if cleanup_result.get('deleted_count', 0) > 0:
                    self.logger.info(f"[{document_id}] ✅ Deleted {cleanup_result['deleted_count']} structured metadata entries")
            except Exception as cleanup_error:
                self.logger.warning(f"[{document_id}] ⚠️ Structured metadata cleanup failed (non-blocking): {cleanup_error}")
            
            self.logger.info(f"[{document_id}] ✅ Document deleted successfully")
            
            return {
                "success": True,
                "document_id": document_id,
                "chunks_deleted": chunks_deleted
            }
            
        except Exception as e:
            self.logger.error(f"[{document_id}] ❌ Document deletion failed: {e}")
            return {
                "success": False,
                "document_id": document_id,
                "reason": "error",
                "error": str(e),
                "chunks_deleted": 0
            }


