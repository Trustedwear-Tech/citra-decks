"""
LlamaIndex Query Engine for Unified Context Retrieval
=====================================================

This module implements LlamaIndex-based query engine for both personal and enterprise
context retrieval from Milvus vector database with entity and user-based filtering.

Features:
- Milvus integration for dense COSINE vector search
- User-based and entity-based data filtering
- LlamaIndex query engine for semantic retrieval
- Adaptive similarity threshold filtering
"""

import os
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from config.milvus_config import milvus_config

# LlamaIndex imports
from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.vector_stores.milvus import MilvusVectorStore
# Note: No longer using LlamaIndex LLM adapters - using llm_oss.py for all model calls
from llama_index.core.schema import QueryBundle
from llama_index.core.embeddings import BaseEmbedding
try:
    # Preferred import path in recent LlamaIndex versions
    from llama_index.core.vector_stores.types import (
        MetadataFilters,
        MetadataFilter,
        ExactMatchFilter,
        FilterCondition,  # modern enum name
        FilterOperator,
    )
except Exception:  # pragma: no cover - fallback for older versions
    try:
        # Older path (some versions)
        from llama_index.core.vector_stores import (  # type: ignore
            MetadataFilters,  # type: ignore
            MetadataFilter,  # type: ignore
            ExactMatchFilter,  # type: ignore
            FilterCondition,  # type: ignore
            FilterOperator,  # type: ignore
        )
    except Exception:
        # Final fallback to FilterOperator; we'll alias it to FilterCondition below
        from llama_index.core.vector_stores import (  # type: ignore
            MetadataFilters,  # type: ignore
            MetadataFilter,  # type: ignore
            ExactMatchFilter,  # type: ignore
            FilterOperator,  # type: ignore
        )
        class FilterCondition:  # type: ignore
            OR = getattr(FilterOperator, 'OR', 'or')
            AND = getattr(FilterOperator, 'AND', 'and')

import numpy as np

logger = logging.getLogger(__name__)




class CustomEmbedding(BaseEmbedding):
    """Custom embedding class for LlamaIndex that works with any compatible embedding API"""
    
    model_name: str
    task_type: str
    output_dimensionality: Optional[int]
    
    def __init__(
        self, 
        model_name: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        task_type: str = "RETRIEVAL_QUERY",
        output_dimensionality: Optional[int] = None,
        **kwargs
    ):
        """Initialize the custom embedding
        
        Args:
            model_name: Embedding model name (from EMBEDDING_MODEL env var)
            task_type: Task type (RETRIEVAL_QUERY or RETRIEVAL_DOCUMENT)
            output_dimensionality: Output dimension (defaults to full 1024)
        """
        super().__init__(
            model_name=model_name,
            task_type=task_type,
            output_dimensionality=output_dimensionality,
            **kwargs
        )
        
    def _get_query_embedding(self, query: str) -> List[float]:
        """Get embedding for a single query"""
        from utils import embed_text_sync
        try:
            # Use sync embedding from utils
            embedding = embed_text_sync(query, task_type=self.task_type)
            return embedding
        except Exception as e:
            logger.error(f"❌ [EMBEDDING] Query embedding failed: {e}")
            # Re-raise: a wrong-dimension fallback vector will silently mismatch the
            # Milvus collection and produce a confusing dim-mismatch error downstream.
            raise
    
    def _get_text_embedding(self, text: str) -> List[float]:
        """Get embedding for a single text"""
        return self._get_query_embedding(text)
    
    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts using batch API"""
        from utils import embed_texts_batch_sync
        try:
            # Use sync batch embedding from utils
            embeddings = embed_texts_batch_sync(texts, task_type=self.task_type)
            logger.debug(f"✅ [EMBEDDING] Batch embedding successful, {len(texts)} texts processed")
            return embeddings
        except Exception as e:
            logger.error(f"❌ [EMBEDDING] Batch embedding failed: {e}, falling back to individual requests")
            # Fallback to individual requests
            embeddings = []
            for text in texts:
                embeddings.append(self._get_text_embedding(text))
            return embeddings
    
    async def _aget_query_embedding(self, query: str) -> List[float]:
        """Async version of _get_query_embedding"""
        from utils import embed_text
        try:
            # Use async embedding from utils
            embedding = await embed_text(query, task_type=self.task_type)
            return embedding
        except Exception as e:
            logger.error(f"❌ [EMBEDDING] Async query embedding failed: {e}")
            # Re-raise: see _get_query_embedding for rationale.
            raise
    
    async def _aget_text_embedding(self, text: str) -> List[float]:
        """Async version of _get_text_embedding"""
        return await self._aget_query_embedding(text)
    
    async def _aget_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Async version of _get_text_embeddings"""
        from utils import embed_texts_batch
        try:
            # Use async batch embedding from utils
            embeddings = await embed_texts_batch(texts, task_type=self.task_type)
            logger.debug(f"✅ [EMBEDDING] Async batch embedding successful, {len(texts)} texts processed")
            return embeddings
        except Exception as e:
            logger.error(f"❌ [EMBEDDING] Async batch embedding failed: {e}")
            # Fallback to individual requests
            embeddings = []
            for text in texts:
                embeddings.append(await self._aget_text_embedding(text))
            return embeddings


class UnifiedQueryEngine:
    """
    LlamaIndex-based query engine for personal context retrieval.
    
    Access Control Strategy:
    - Personal data: Filtered by user_id and optional folder_id
    
    Features:
    - Dense COSINE vector search for personal data
    - Folder-based filtering for personal data
    - Adaptive similarity threshold filtering
    - JWT-based authentication
    
    Milvus Search:
    - Dense vectors: 768-dim embeddings (COSINE similarity)
    - Pure dense search (no BM25/sparse vectors)
    
    Model Management:
    - Uses query.py as single source of truth for all model calls
    - No LlamaIndex LLM adapters - ensures consistent configuration
    - Model configured via LLM_MODEL env var
    """
    
    def __init__(self):
        """Initialize the query engine for personal data"""
        self.milvus_client = None
        self.vector_store = None
        self.query_engine = None
        self.jwt_secret = os.getenv("JWT_SECRET")
        
        # Milvus configuration from milvus_config (single source of truth)
        self.milvus_uri = milvus_config.uri
        self.milvus_token = milvus_config.api_key
        self.collection_name = milvus_config.collection_name
        self.embed_dim = milvus_config.dense_vector_dim
        
        # Similarity threshold configuration from milvus_config (single source of truth)
        self.personal_similarity_threshold = milvus_config.personal_similarity_threshold
        
        # Validate required configuration
        # Token is optional for self-hosted Milvus, required for Zilliz Cloud
        is_cloud = not bool(os.getenv("MILVUS_URI"))
        if not self.milvus_uri:
            raise ValueError("Milvus URI not configured. Set MILVUS_URI (self-hosted) or ZILLIZ_CLOUD_URI (cloud).")
        if is_cloud and not self.milvus_token:
            raise ValueError("Zilliz Cloud API key not configured. Set MILVUS_TOKEN or ZILLIZ_CLOUD_API_KEY.")
        if not self.jwt_secret:
            raise ValueError("JWT_SECRET not found in environment variables")
        
        # Initialize components
        self._initialize_milvus()
        self._initialize_llamaindex()
        
        logger.info("🔧 Query Engine initialized successfully with Milvus")
    
    def _initialize_milvus(self):
        """Initialize Milvus client using the singleton.
        
        Note: pymilvus reuses gRPC connections for the same URI+token (deterministic
        alias), so creating a separate MilvusClient does NOT create a separate channel.
        Using the singleton with self-healing channel detection in get_milvus_client().
        """
        try:
            from config.milvus_config import get_milvus_client
            self.milvus_client = get_milvus_client()
            
            # Check if collection exists (refresh singleton for reliability)
            self.milvus_client = get_milvus_client()
            collections = self.milvus_client.list_collections(timeout=5)
            if self.collection_name not in collections:
                logger.warning(f"⚠️ Milvus collection '{self.collection_name}' not found. Available: {collections}")
                raise ValueError(f"Milvus collection '{self.collection_name}' does not exist")
            
            logger.info(f"✅ Connected to Milvus collection: {self.collection_name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Milvus: {e}")
            raise
    
    def _initialize_llamaindex(self):
        """Initialize LlamaIndex components"""
        try:
            # Initialize custom embeddings
            embed_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
            embed_task_type = os.getenv("EMBEDDING_TASK_TYPE", "RETRIEVAL_QUERY")
            embed_dim_str = os.getenv("EMBED_DIM")
            output_dim = int(embed_dim_str) if embed_dim_str else None
            
            Settings.embed_model = CustomEmbedding(
                model_name=embed_model,
                task_type=embed_task_type,
                output_dimensionality=output_dim
            )
            logger.info(f"🔧 [LLAMAINDEX] Configured custom embeddings: {embed_model}")
            
            # Use query.py for all model calls - single source of truth for LLM configuration
            # LLM model is configured via LLM_MODEL env var
            # NOTE: Milvus vector store will be created dynamically for queries
            # - Filter-based data isolation (user_id + is_enterprise)
            self.vector_store = None  # Will be created per query with appropriate filters
            self.index = None  # Will be created per query with appropriate filters
            
            logger.info("✅ LlamaIndex components initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize LlamaIndex: {e}")
            raise

    def _milvus_query(
        self, 
        vector: List[float], 
        filter_expr: Optional[str] = None, 
        top_k: int = 10, 
        output_fields: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Helper method to query Milvus with pure dense COSINE search.
        
        Args:
            vector: Dense query embedding vector
            filter_expr: Milvus filter expression (e.g., 'user_id == "user_123"')
            top_k: Number of results to return
            output_fields: Fields to include in results
            
        Returns:
            List of results in standardized format
        """
        # Type enforcement and validation
        if not isinstance(vector, (list, np.ndarray)):
            logger.error(f"❌ INVALID VECTOR TYPE: Expected list or ndarray, got {type(vector)}")
            raise ValueError(f"Dense vector must be a list of floats, got {type(vector)}")
        
        # Ensure vector is list of floats
        if isinstance(vector, np.ndarray):
            vector = vector.tolist()
        
        if len(vector) > 0 and not isinstance(vector[0], (float, int, np.floating, np.integer)):
            logger.error(f"❌ INVALID VECTOR ELEMENT TYPE: Got {type(vector[0])}")
            raise ValueError(f"Dense vector elements must be numeric, got {type(vector[0])}")

        try:
            if output_fields is None:
                # Use "*" to get ALL fields including all metadata
                output_fields = ["*"]
                logger.info("🔍 [MILVUS_QUERY] Using output_fields=['*'] to retrieve ALL fields including metadata")
            
            search_params = {
                "collection_name": self.collection_name,
                "limit": top_k,
                "output_fields": output_fields
            }
            
            if filter_expr:
                search_params["filter"] = filter_expr
            
            # DEBUG LOGGING FOR VECTOR TYPES
            logger.info(f"🔎 DEBUG MILVUS QUERY: vector={type(vector)} len={len(vector) if hasattr(vector, '__len__') else 'N/A'}")

            # Dense-only COSINE search
            search_params["data"] = [vector]
            search_params["anns_field"] = "dense_vector"  # CRITICAL: Must specify field name for Milvus
            search_params["search_params"] = {"metric_type": "COSINE"}
            logger.debug("📊 Using Milvus dense-only COSINE search")
            try:
                # Always fetch the fresh singleton to avoid stale gRPC references
                from config.milvus_config import get_milvus_client
                self.milvus_client = get_milvus_client()
                results = self.milvus_client.search(**search_params)
            except Exception as search_err:
                # gRPC channel may be dead — recreate singleton and retry once
                logger.warning(f"⚠️ Milvus search failed ({search_err}), recreating client and retrying...")
                from config.milvus_config import recreate_milvus_client
                self.milvus_client = recreate_milvus_client()
                results = self.milvus_client.search(**search_params)
            
            # Convert to standardized format
            formatted_results = []
            if results and len(results) > 0:
                for idx, hit in enumerate(results[0]):  # results[0] because we sent single query vector
                    # Extract entity data from nested structure
                    # Milvus search returns: {'primary_key': ..., 'distance': ..., 'entity': {...fields...}}
                    entity = hit.get('entity', {})
                    
                    # Debug: Log the actual hit structure for first result
                    if idx == 0:
                        logger.info(f"🔍 DEBUG: First Milvus hit keys: {list(hit.keys())}")
                        logger.info(f"🔍 DEBUG: Entity keys: {list(entity.keys())}")
                        if 'text' in entity:
                            text_preview = entity.get('text', '')[:100]
                            logger.info(f"🔍 DEBUG: text field found in entity, preview: {text_preview}...")
                        else:
                            logger.error(f"❌ DEBUG: text field MISSING from entity! Available fields: {list(entity.keys())}")
                    
                    # Use chunk_id (original UUID) as the ID, fallback to primary_key
                    result_id = entity.get('chunk_id', entity.get('id', hit.get('primary_key')))
                    
                    # Build metadata dict excluding system fields (but KEEP chunk_id for citations)
                    metadata = {}
                    exclude_fields = ['id', 'primary_key', 'distance', 'vector', 'dense_vector', 'sparse_vector']
                    for k, v in entity.items():
                        if k not in exclude_fields:
                            metadata[k] = v
                    
                    # Ensure chunk_id is always in metadata for citation generation
                    if 'chunk_id' not in metadata and result_id:
                        metadata['chunk_id'] = result_id
                    
                    # Check chunk_id presence for first result
                    if idx == 0:
                        logger.info(f"🔍 [METADATA_CHECK] First result metadata keys ({len(metadata)} fields): {list(metadata.keys())}")
                        chunk_id_value = metadata.get('chunk_id', 'NOT_FOUND')
                        logger.info(f"🆔 [CHUNK_ID_CHECK] chunk_id in metadata: {chunk_id_value[:50] if isinstance(chunk_id_value, str) else chunk_id_value}")
                    
                    formatted_results.append({
                        'id': result_id,
                        'score': hit.get('distance', 0.0),  # Milvus uses 'distance'
                        'metadata': metadata,
                        'values': []  # Vector values not returned in search
                    })
            
            # Score distribution logging for threshold calibration
            if formatted_results:
                scores = [r['score'] for r in formatted_results]
                min_s, max_s, mean_s = min(scores), max(scores), sum(scores) / len(scores)
                logger.info(f"📊 MILVUS_SCORES: count={len(scores)}, min={min_s:.4f}, max={max_s:.4f}, "
                            f"mean={mean_s:.4f}, scores=[{', '.join(f'{s:.4f}' for s in scores[:10])}{'...' if len(scores) > 10 else ''}]")
            
            # Defense-in-depth: absolute score floor (catches all search paths)
            abs_min = milvus_config.absolute_min_score
            if abs_min > 0:
                before_count = len(formatted_results)
                formatted_results = [r for r in formatted_results if r['score'] >= abs_min]
                if before_count > len(formatted_results):
                    logger.info(f"🔻 ABSOLUTE_FLOOR: Removed {before_count - len(formatted_results)} results below {abs_min}")
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"❌ Milvus query failed: {e}")
            return []

    def _convert_llamaindex_filter_to_milvus(self, llamaindex_filter: MetadataFilters) -> Optional[str]:
        """
        Convert LlamaIndex MetadataFilters to Milvus filter expression string
        
        Args:
            llamaindex_filter: LlamaIndex metadata filters
            
        Returns:
            Milvus-compatible filter expression string
        """
        try:
            if not llamaindex_filter or not llamaindex_filter.filters:
                return None
            
            filter_parts = []
            for f in llamaindex_filter.filters:
                if hasattr(f, 'key') and hasattr(f, 'value'):
                    # Escape string values
                    if isinstance(f.value, str):
                        filter_parts.append(f'{f.key} == "{f.value}"')
                    elif isinstance(f.value, bool):
                        filter_parts.append(f'{f.key} == {str(f.value).lower()}')
                    else:
                        filter_parts.append(f'{f.key} == {f.value}')
            
            if not filter_parts:
                return None
            
            # Combine with appropriate operator
            if llamaindex_filter.condition == FilterCondition.OR:
                return " or ".join(filter_parts)
            else:
                return " and ".join(filter_parts)
            
        except Exception as e:
            logger.warning(f"⚠️ Milvus filter conversion failed: {e}")
            return None

    def _create_namespace_index(self, user_id: str) -> VectorStoreIndex:
        """
        Create LlamaIndex VectorStoreIndex for Milvus collection
        
        Args:
            user_id: User ID (parameter kept for API compatibility)
            
        Returns:
            VectorStoreIndex configured for Milvus collection
        """
        try:
            # Create Milvus vector store
            vector_store = MilvusVectorStore(
                uri=self.milvus_uri,
                token=self.milvus_token,
                collection_name=self.collection_name,
                dim=int(os.getenv("EMBEDDING_DIMENSION", "768"))
            )
            
            # Create index from vector store
            index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
            
            logger.debug(f"✅ Created LlamaIndex for Milvus collection: {self.collection_name}")
            return index
            
        except Exception as e:
            logger.error(f"❌ Failed to create Milvus index: {e}")
            raise

    async def retrieve_personal_context(
        self,
        query: str,
        user_id: str,
        selected_folder_ids: Optional[List[str]] = None,
        folder_search_enabled: bool = False,
        top_k: int = 10,
        max_results: Optional[int] = None,  # Added to accept max_results from tools
        similarity_threshold: Optional[float] = None,
        user_email: Optional[str] = None,  # Added for embedding tracking
        milvus_fetch_k: Optional[int] = None,
        skip_rerank: bool = False,
        precomputed_embedding: Optional[List[float]] = None,  # Skip /embeddings RTT when caller supplies the vector
        adaptive_threshold: bool = False,   # Outline-only escape from strict threshold cuts
        adaptive_floor: int = 5,            # When adaptive is on, return at least this many chunks if Milvus returned any
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Retrieve personal context using LlamaIndex query engine with user namespace
        
        Args:
            query: Search query string
            user_id: User's device ID (used as namespace)
            selected_folder_ids: Optional folder filtering
            folder_search_enabled: Enable folder-based search
            top_k: Number of top results to return
            max_results: Alternative parameter name for top_k (takes precedence if provided)
            similarity_threshold: Minimum similarity score for results (uses PERSONAL_SIMILARITY_THRESHOLD from .env if None)
            user_email: User email for embedding credit tracking (optional)
            
        Returns:
            List of context documents with metadata
        """
        try:
            # Use max_results if provided (tools pass this parameter), otherwise use top_k
            if max_results is not None:
                top_k = max_results
                logger.info(f"🔧 Using max_results={max_results} as top_k for retrieval")
            
            # Use provided threshold or default from .env
            if similarity_threshold is None:
                similarity_threshold = self.personal_similarity_threshold
            
            logger.info(f"🔍 Starting personal context retrieval for user: {user_id}, query: '{query[:100]}...', threshold: {similarity_threshold}")
            
            # Create index for user's personal data
            personal_index = self._create_namespace_index(user_id)
            
            # Build folder filter if enabled
            filters = []
            if folder_search_enabled and selected_folder_ids:
                logger.info(f"🗂️ Adding folder filter: {selected_folder_ids}")
                # Create OR filter for multiple folders
                for folder_id in selected_folder_ids:
                    filters.append(ExactMatchFilter(key="folder_id", value=folder_id))
            
            # Create combined filter
            folder_filter = None
            if filters:
                folder_filter = MetadataFilters(
                    filters=filters, 
                    condition=FilterCondition.OR
                )
            
            # Perform query using direct Milvus dense COSINE search
            logger.info(f"📊 PERSONAL DENSE: Starting pure dense COSINE search for user: {user_id}")
            # Over-fetch when reranker is enabled so cross-encoder can pick better chunks
            from reranker import is_reranker_enabled, get_top_k_multiplier, rerank as rerank_chunks
            # ``skip_rerank`` is the lite-mode opt-out used by per-slide /
            # per-page / per-section flows. They send focused queries where
            # Milvus top-k is already good enough, and the reranker HTTP call
            # (10-30 s) is the dominant slowdown source.
            reranker_active = is_reranker_enabled() and not skip_rerank
            if skip_rerank:
                logger.info("🚫 [PERSONAL_LITE] skip_rerank=True — bypassing cross-encoder + over-fetch")
            if milvus_fetch_k:
                milvus_top_k = milvus_fetch_k
            else:
                milvus_top_k = top_k * get_top_k_multiplier() if reranker_active else top_k
            if reranker_active:
                logger.info(f"🔁 Reranker enabled — over-fetching {milvus_top_k} chunks from Milvus (final top_k={top_k})")
            raw_results = await self._perform_personal_direct_query(
                personal_index=personal_index,
                query=query,
                user_id=user_id,
                permission_filter=folder_filter,
                top_k=milvus_top_k,
                user_email=user_email,  # Pass user_email for embedding tracking
                precomputed_embedding=precomputed_embedding,
            )
            
            # Process and format results - APPLY SIMILARITY THRESHOLD FILTERING
            logger.info(f"📊 CHUNK_STATS: Fetched {len(raw_results)} raw results from Milvus for user {user_id}")
            
            # Sort raw results by score descending (should already be sorted, but ensure)
            raw_results.sort(key=lambda r: r.get('score', 0.0), reverse=True)
            
            # Simple threshold-based filtering
            effective_threshold = similarity_threshold
            if raw_results:
                all_scores = [r.get('score', 0.0) for r in raw_results]
                logger.info(f"📊 SCORE_DISTRIBUTION: count={len(all_scores)}, min={all_scores[-1]:.4f}, "
                            f"max={all_scores[0]:.4f}, scores={[round(s, 4) for s in all_scores[:10]]}")
            logger.info(f"🎯 THRESHOLD: Using similarity_threshold={effective_threshold}")
            
            context_results = []
            filtered_count = 0
            for idx, result in enumerate(raw_results):
                score = result.get('score', 0.0)
                
                # Simple threshold filter
                if score < effective_threshold:
                    filtered_count += 1
                    if filtered_count <= 3:
                        metadata = result.get('metadata', {})
                        if filtered_count == 1:
                            logger.info(f"🔍 DEBUG: Metadata keys available: {list(metadata.keys())}")
                        topic = metadata.get('topic_or_filename', metadata.get('topic', 'Unknown'))
                        logger.info(f"🚫 FILTERED #{filtered_count}: score={score:.4f} < effective_threshold={effective_threshold:.4f} | doc={topic[:50]}")
                    else:
                        logger.debug(f"🚫 FILTERED: Chunk #{idx+1} score={score:.4f} below threshold {effective_threshold:.4f}")
                    continue
                
                # Log accepted chunks at INFO level
                metadata = result.get('metadata', {})
                topic = metadata.get('topic_or_filename', metadata.get('topic', 'Unknown Document'))
                logger.info(f"✅ ACCEPTED #{len(context_results)+1}: score={score:.4f} >= {effective_threshold:.4f} | doc={topic[:50]}")
                
                document_id = metadata.get('document_id', '')
                chunk_id = metadata.get('chunk_id', '')  # For MongoDB correlation
                source_type = metadata.get('source_type', 'document')  # "document", "audio", or "video"
                
                # 🔍 DEBUG: Log document_id to verify it's being retrieved
                if len(context_results) < 3:
                    logger.info(f"🆔 [DOCUMENT_ID_DEBUG] Context #{len(context_results)+1}:")
                    logger.info(f"   - metadata keys: {list(metadata.keys())}")
                    logger.info(f"   - document_id value: '{document_id}'")
                    logger.info(f"   - topic value: '{topic[:100] if topic else 'EMPTY'}'")
                    logger.info(f"   - chunk_id value: '{chunk_id[:50] if chunk_id else 'EMPTY'}'")
                
                # BREAKING CHANGE: Text will be fetched from MongoDB in batch after all chunks processed
                # Store chunk metadata for now, text will be added later
                
                # ✅ ENHANCED CITATION: Create dual citation format with markers
                # - Document citation: DOC::topic--document_id (for document download)
                # - Chunk citation: CHUNK::topic--chunk_id (for chunk text retrieval)
                
                # 🔍 DEBUG: Log chunk_id for first few results
                if len(context_results) < 3:
                    logger.info(f"🆔 [CITATION_BUILD] Context #{len(context_results)+1}: chunk_id='{chunk_id[:50] if chunk_id else 'EMPTY'}'") 
                
                document_citation = f"DOC::{topic}--{document_id}" if document_id else f"DOC::{topic}"
                chunk_citation = f"CHUNK::{topic}--{chunk_id}" if chunk_id else None
                
                # 🔍 DEBUG: Log citation creation
                if len(context_results) < 3:
                    logger.info(f"📋 [CITATION_CREATED] Context #{len(context_results)+1}:")
                    logger.info(f"   - document_citation: {document_citation[:80]}")
                    logger.info(f"   - chunk_citation: {chunk_citation[:80] if chunk_citation else 'None'}")
                
                # Primary citation includes both for LLM to use
                citation = chunk_citation if chunk_id else document_citation
                
                context = {
                    "text": "",  # BREAKING CHANGE: Will be filled from MongoDB batch fetch
                    "score": float(score),
                    "metadata": metadata,
                    "node_id": chunk_id,
                    "chunk_id": chunk_id,  # Store for MongoDB batch fetch
                    "source_type": source_type,  # Store for routing to correct MongoDB collection
                    "source_type_retrieval": "personal_dense",
                    "retrieved_at": datetime.utcnow().isoformat(),
                    "citation": citation,  # Primary citation (chunk)
                    "document_citation": document_citation,  # Alternative document citation
                    "chunk_citation": chunk_citation,  # Chunk-specific citation
                    "document_id": document_id,
                    "topic": topic,
                    "user_id": user_id
                }
                context_results.append(context)

                # Continue processing all chunks that pass the threshold

            # ─────────────────────────────────────────────────────────────
            # Adaptive backfill — outline-only escape from over-strict cuts
            # ─────────────────────────────────────────────────────────────
            # Default behaviour (adaptive_threshold=False): strict threshold
            # wins. Per-slide / per-page retrieval keeps using this because
            # their queries are 80-120 char focused strings where top scores
            # naturally land in the 0.55-0.75 range, so the 0.35 floor is fine.
            #
            # Outline retrieval (adaptive_threshold=True) opts in to the
            # backfill because:
            #   - The query is the user's RAW deck goal — often short
            #     ("energy outlook"), sometimes typo'd, always low-info.
            #   - Short queries produce weak embeddings → score distributions
            #     compress into a narrow band (e.g. 0.30-0.39).
            #   - The 0.35 threshold then cuts through the middle of that
            #     band and returns 0-1 chunks, starving the outline LLM of
            #     grounding context.
            #
            # Three trigger conditions for backfill (any one fires):
            #   1. VAGUE QUERY      — < 25 chars OR ≤ 2 unique meaningful words
            #   2. NARROW SCORE BAND — max-min < 0.10 (threshold is noise)
            #   3. UNDER-FLOOR       — strict pass returned < adaptive_floor chunks
            if adaptive_threshold and raw_results and len(context_results) < adaptive_floor:
                _q = (query or "").strip()
                _q_chars = len(_q)
                _meaningful_words = [
                    w for w in _q.lower().split()
                    if len(w) >= 3 and w not in {"the", "and", "for", "with", "from", "into", "this", "that", "what", "how"}
                ]
                _is_vague = (_q_chars < 25) or (len(set(_meaningful_words)) <= 2)
                _score_band = (raw_results[0].get("score", 0.0) - raw_results[-1].get("score", 0.0))
                _is_narrow_band = (_score_band < 0.10)
                _under_floor = len(context_results) < adaptive_floor

                if _is_vague or _is_narrow_band or _under_floor:
                    _reasons = []
                    if _is_vague: _reasons.append(f"vague_query({_q_chars}c)")
                    if _is_narrow_band: _reasons.append(f"narrow_band({_score_band:.3f})")
                    if _under_floor: _reasons.append(f"under_floor({len(context_results)}/{adaptive_floor})")
                    logger.info(
                        f"🎯 [ADAPTIVE] backfill triggered for outline retrieval: {', '.join(_reasons)}; "
                        f"taking top-{adaptive_floor} from {len(raw_results)} raw results"
                    )
                    # Backfill: take the top-K of raw_results, skip ones we already accepted,
                    # then build context objects identical to the accept-path above.
                    _already_in = {ctx.get("chunk_id") for ctx in context_results if ctx.get("chunk_id")}
                    _added = 0
                    for result in raw_results:
                        if len(context_results) >= adaptive_floor:
                            break
                        _md = result.get("metadata", {})
                        _cid = _md.get("chunk_id", "")
                        if _cid in _already_in:
                            continue
                        _topic = _md.get("topic_or_filename", _md.get("topic", "Unknown Document"))
                        _did = _md.get("document_id", "")
                        _stype = _md.get("source_type", "document")
                        _document_citation = f"DOC::{_topic}--{_did}" if _did else f"DOC::{_topic}"
                        _chunk_citation = f"CHUNK::{_topic}--{_cid}" if _cid else None
                        context_results.append({
                            "text": "",  # filled by MongoDB batch fetch below
                            "score": float(result.get("score", 0.0)),
                            "metadata": _md,
                            "node_id": _cid,
                            "chunk_id": _cid,
                            "source_type": _stype,
                            "source_type_retrieval": "personal_dense_adaptive",
                            "retrieved_at": datetime.utcnow().isoformat(),
                            "citation": _chunk_citation if _cid else _document_citation,
                            "document_citation": _document_citation,
                            "chunk_citation": _chunk_citation,
                            "document_id": _did,
                            "topic": _topic,
                            "user_id": user_id,
                        })
                        _added += 1
                        logger.info(
                            f"✅ [ADAPTIVE] backfilled chunk: score={result.get('score', 0.0):.4f} | doc={_topic[:50]}"
                        )
                    if _added:
                        filtered_count = max(0, filtered_count - _added)

            # BREAKING CHANGE: Batch fetch chunk texts from MongoDB
            logger.info(f"📋 Batch fetching {len(context_results)} chunk texts from MongoDB...")
            if context_results:
                try:
                    # Import MongoDB service
                    from services.enhanced_chunked_document_service import EnhancedChunkedDocumentService
                    from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
                    
                    mongo_client = get_async_mongo_client()
                    doc_service = EnhancedChunkedDocumentService(mongo_client, MONGODB_DATABASE)
                    
                    # Extract chunk_ids and source_types
                    chunk_ids = [ctx['chunk_id'] for ctx in context_results if ctx.get('chunk_id')]
                    source_types = {ctx['chunk_id']: ctx['source_type'] for ctx in context_results if ctx.get('chunk_id') and ctx.get('source_type')}
                    
                    if chunk_ids:
                        # Batch fetch texts with source_type routing
                        chunk_texts = await doc_service.batch_fetch_chunk_texts(chunk_ids, user_id, source_types)
                        
                        # Merge texts into context results
                        for ctx in context_results:
                            chunk_id = ctx.get('chunk_id')
                            if chunk_id in chunk_texts:
                                ctx['text'] = chunk_texts[chunk_id]
                            else:
                                logger.warning(f"⚠️ Missing text for chunk_id: {chunk_id}")
                                ctx['text'] = ""  # Empty text as fallback
                        
                        logger.info(f"✅ MongoDB batch fetch complete: {len(chunk_texts)}/{len(chunk_ids)} texts retrieved")
                    else:
                        logger.warning("⚠️ No chunk_ids found for batch fetch")
                except Exception as batch_error:
                    logger.error(f"❌ MongoDB batch fetch failed: {batch_error}")
                    # Continue with empty texts rather than failing entirely
                    for ctx in context_results:
                        if not ctx.get('text'):
                            ctx['text'] = ""
            
            logger.info(f"📊 CHUNK_STATS: Processing complete - {len(context_results)} chunks passed threshold (filtered: {filtered_count})")
            logger.info(f"✅ Retrieved {len(context_results)} personal contexts for user {user_id} with threshold={similarity_threshold}")
            
            # ── Reranker: cross-encoder re-scoring ──
            if reranker_active and len(context_results) > 1:
                # Filter out chunks with empty text before reranking
                chunks_with_text = [c for c in context_results if c.get('text', '').strip()]
                chunks_no_text = [c for c in context_results if not c.get('text', '').strip()]
                if chunks_with_text:
                    logger.info(f"🔁 Reranking {len(chunks_with_text)} chunks (skipping {len(chunks_no_text)} with no text)")
                    context_results = rerank_chunks(query, chunks_with_text, top_k)
                else:
                    logger.warning("⚠️ All chunks have empty text — skipping reranker")
                    context_results.sort(key=lambda x: x.get('score', 0.0), reverse=True)
                    context_results = context_results[:top_k]
            else:
                # Fallback: sort by original COSINE similarity score
                try:
                    context_results.sort(key=lambda x: x["score"], reverse=True)
                    logger.info("📊 Using pure similarity-based ranking (reranker disabled or single result)")
                except Exception as e:
                    logger.warning(f"⚠️ Sorting failed: {e}")
                    context_results.sort(key=lambda x: x["score"], reverse=True)

            # 🛡️ Post-rerank min-score floor — drops low-confidence chunks before
            # they reach the LLM. Configured via MIN_CHUNK_SCORE env (default 0.0
            # = disabled to preserve current recall). Set higher (e.g. 0.35) to
            # tighten grounding for high-stakes deployments.
            try:
                _min_chunk_score = float(os.getenv("MIN_CHUNK_SCORE", "0.0"))
            except (TypeError, ValueError):
                _min_chunk_score = 0.0
            if _min_chunk_score > 0 and context_results:
                _before = len(context_results)
                context_results = [c for c in context_results if c.get('score', 0.0) >= _min_chunk_score]
                _dropped = _before - len(context_results)
                if _dropped:
                    logger.info(f"🔻 MIN_CHUNK_SCORE={_min_chunk_score}: dropped {_dropped} low-score chunks")
            
            return context_results
            
        except Exception as e:
            logger.error(f"❌ Personal context retrieval failed for user {user_id}: {e}")
            raise RuntimeError(f"Personal context retrieval failed: {str(e)}")

    async def _perform_personal_direct_query(
        self,
        personal_index: VectorStoreIndex,
        query: str,
        user_id: str,
        permission_filter: Optional[MetadataFilters],
        top_k: int,
        user_email: Optional[str] = None,  # Added for embedding tracking
        precomputed_embedding: Optional[List[float]] = None,  # Skip /embeddings RTT when caller already has the vector
    ) -> List[Dict[str, Any]]:
        """
        Perform direct Milvus dense COSINE search for personal data.
        
        Args:
            personal_index: LlamaIndex for user's personal namespace
            query: Search query string
            user_id: User's device ID
            permission_filter: LlamaIndex metadata filters (folder filtering)
            top_k: Number of results to return
            user_email: User email for embedding credit tracking (optional)
            
        Returns:
            List of search results with COSINE similarity scoring
        """
        try:
            # Get dense vector — caller can supply a precomputed one (batch
            # prefetch path) to skip the /embeddings RTT entirely.
            if precomputed_embedding is not None:
                dense_vector = precomputed_embedding
                _embed_was_precomputed = True
            else:
                dense_vector = Settings.embed_model._get_query_embedding(query)
                _embed_was_precomputed = False

            # 💳 Track embedding usage for query (only when we actually called the embed API).
            # Precomputed path was already tracked by the batch caller.
            if user_email and not _embed_was_precomputed:
                try:
                    from middleware.credit_check_middleware import get_usage_service
                    usage_service = get_usage_service()
                    
                    total_characters = len(query)
                    tracking_result = usage_service.track_embedding_usage(
                        user_id=user_id,
                        email=user_email,
                        total_characters=total_characters
                    )
                    
                    if tracking_result['success']:
                        tokens = tracking_result.get('cost_details', {}).get('estimated_tokens', 0)

                        if tracking_result.get('buffered'):
                            logger.info(
                                f"💠 Query embedding buffered: {user_email} | "
                                f"Chars: {total_characters} | Tokens: ~{tokens}"
                            )
                        else:
                            logger.info(
                                f"💠 Query embedding tracked: {user_email} | "
                                f"Chars: {total_characters} | Tokens: ~{tokens}"
                            )
                    else:
                        logger.warning(f"⚠️ Query embedding tracking failed: {tracking_result.get('error')}")
                except Exception as track_error:
                    logger.error(f"❌ Query embedding tracking error: {track_error}")
            
            # Pure dense COSINE search
            
            # Add folder filter if provided
            milvus_expr = None
            if permission_filter:
                # Convert LlamaIndex filter to Milvus expression
                milvus_expr = self._convert_llamaindex_filter_to_milvus(permission_filter)
                if milvus_expr:
                    logger.info(f"📁 PERSONAL DENSE: Added folder filter to query")
            
            # Add user_id filter for personal data
            logger.info(f"🔍 DEBUG: user_id parameter received: '{user_id}'")
            user_filter = f'user_id == "{user_id}"'
            logger.info(f"🔍 DEBUG: user_filter constructed: '{user_filter}'")
            
            # ✅ EXCLUDE KG NODES: Personal agent should NOT fetch knowledge graph nodes
            # KG nodes are handled by the dedicated KG agent
            kg_exclusion = 'chunk_type != "knowledge_graph_node"'
            logger.info(f"🔍 DEBUG: kg_exclusion: '{kg_exclusion}'")
            
            # ✅ EXCLUDE ENTERPRISE DATA: Personal agent should NOT fetch enterprise-marked data
            # Enterprise data is handled by the dedicated Enterprise agent when enterprise_enabled=True
            # Note: Using is_enterprise == false to explicitly get only personal data
            # This ensures personal data is returned regardless of entity_id field
            enterprise_exclusion = 'is_enterprise == false'
            logger.info(f"🔍 DEBUG: enterprise_exclusion: '{enterprise_exclusion}'")
            
            if milvus_expr:
                milvus_expr = f"({user_filter}) and ({kg_exclusion}) and ({enterprise_exclusion}) and ({milvus_expr})"
            else:
                milvus_expr = f"({user_filter}) and ({kg_exclusion}) and ({enterprise_exclusion})"
            
            logger.info(f"🔍 DEBUG: After construction, user_id still: '{user_id}'")
            logger.info(f"🔍 DEBUG: After construction, user_filter still: '{user_filter}'")
            logger.info(f"🔍 PERSONAL DENSE: Querying user {user_id} with pure dense COSINE search")
            logger.info(f"🚫 PERSONAL DENSE: Excluding KG nodes (chunk_type != 'knowledge_graph_node')")
            logger.info(f"🚫 PERSONAL DENSE: Only personal data (is_enterprise == false)")
            logger.info(f"✅ PERSONAL DENSE: No entity_id filtering - all personal data included")
            
            # Log filter details for debugging
            if milvus_expr:
                logger.info(f"⚖️ PERSONAL DENSE: Applied filter: {milvus_expr}")
            
            # Execute Milvus dense-only query in a thread to avoid SIGSEGV
            # gRPC sync calls on the asyncio event loop thread can crash the process
            logger.info(f"🚀 Calling _milvus_query with dense_vector (len {len(dense_vector)}), pure COSINE search")
            import functools
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                functools.partial(
                    self._milvus_query,
                    vector=dense_vector,
                    filter_expr=milvus_expr,
                    top_k=top_k
                )
            )
            
            # Log results for debugging
            logger.info(f"📊 PERSONAL DENSE: Query returned {len(results)} results")
            
            # Convert Milvus results to standard format
            formatted_results = []
            for match in results:
                formatted_results.append({
                    'id': match.get('id'),
                    'score': match.get('score', match.get('distance', 0.0)),
                    'metadata': match.get('metadata', {}),
                    'values': match.get('values', [])
                })
            
            logger.info(f"✅ PERSONAL DENSE: Retrieved {len(formatted_results)} results for user {user_id}")
            return formatted_results
            
        except Exception as e:
            logger.error(f"❌ PERSONAL DENSE: Dense query failed for user {user_id}: {e}")
            logger.info("🔄 PERSONAL DENSE: Falling back to LlamaIndex dense search")
            return await self._perform_personal_dense_query(personal_index, query, permission_filter, top_k, user_id, user_email)

    async def _perform_personal_dense_query(
        self,
        personal_index: VectorStoreIndex,
        query: str,
        permission_filter: Optional[MetadataFilters],
        top_k: int,
        user_id: str = None,  # Add user_id parameter for namespace filtering
        user_email: Optional[str] = None  # Added for embedding tracking
    ) -> List[Dict[str, Any]]:
        """
        Perform dense-only search for personal data as fallback
        
        Args:
            personal_index: LlamaIndex for user's personal namespace
            query: Search query string
            permission_filter: LlamaIndex metadata filters (folder filtering)
            top_k: Number of results to return
            user_id: User's device ID
            user_email: User email for embedding credit tracking (optional)
            
        Returns:
            List of search results
        """
        try:
            # 💳 Track embedding usage for query (dense query also generates embeddings)
            if user_email and user_id:
                try:
                    from middleware.credit_check_middleware import get_usage_service
                    usage_service = get_usage_service()
                    
                    total_characters = len(query)
                    tracking_result = usage_service.track_embedding_usage(
                        user_id=user_id,
                        email=user_email,
                        total_characters=total_characters
                    )
                    
                    if tracking_result['success']:
                        tokens = tracking_result.get('cost_details', {}).get('estimated_tokens', 0)

                        if tracking_result.get('buffered'):
                            logger.info(
                                f"💠 Query embedding buffered (dense): {user_email} | "
                                f"Chars: {total_characters} | Tokens: ~{tokens}"
                            )
                        else:
                            logger.info(
                                f"💠 Query embedding tracked (dense): {user_email} | "
                                f"Chars: {total_characters} | Tokens: ~{tokens}"
                            )
                    else:
                        logger.warning(f"⚠️ Query embedding tracking failed: {tracking_result.get('error')}")
                except Exception as track_error:
                    logger.error(f"❌ Query embedding tracking error: {track_error}")
            
            # Add namespace filter for personal data (namespace == user_id, not "enterprise_*")
            filters_to_add = []
            
            # KG node exclusion filter
            filters_to_add.append(
                MetadataFilter(
                    key="chunk_type",
                    operator=FilterOperator.NE,
                    value="knowledge_graph_node"
                )
            )
            
            # Enterprise data exclusion filter
            filters_to_add.append(
                MetadataFilter(
                    key="is_enterprise",
                    operator=FilterOperator.NE,
                    value=True
                )
            )
            
            # Namespace filter (personal data uses plain user_id as namespace)
            if user_id:
                filters_to_add.append(
                    MetadataFilter(
                        key="namespace",
                        operator=FilterOperator.EQ,
                        value=user_id
                    )
                )
                logger.info(f"📛 PERSONAL DENSE: Namespace filter (namespace == '{user_id}')")
            
            # Combine all filters with AND condition
            if permission_filter:
                # Merge with existing permission filter (folder filter)
                combined_filters = MetadataFilters(
                    filters=permission_filter.filters + filters_to_add,
                    condition=FilterCondition.AND
                )
            else:
                combined_filters = MetadataFilters(
                    filters=filters_to_add,
                    condition=FilterCondition.AND
                )
            
            logger.info(f"🚫 PERSONAL DENSE: Excluding KG nodes (chunk_type != 'knowledge_graph_node')")
            logger.info(f"🚫 PERSONAL DENSE: Excluding enterprise data (is_enterprise != true)")
            
            # Create retriever with combined filter
            retriever = VectorIndexRetriever(
                index=personal_index,
                similarity_top_k=top_k,
                filters=combined_filters
            )
            
            # Create query bundle
            query_bundle = QueryBundle(query_str=query)
            
            # Retrieve nodes
            nodes_with_scores = await asyncio.get_event_loop().run_in_executor(
                None,
                retriever.retrieve,
                query_bundle
            )
            
            # Convert to standard format
            formatted_results = []
            for node_with_score in nodes_with_scores:
                node = node_with_score.node
                formatted_results.append({
                    'id': node.node_id,
                    'score': node_with_score.score,
                    'metadata': node.metadata,
                    'text': node.text
                })
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"❌ PERSONAL DENSE: Dense query failed: {e}")
            return []

    async def retrieve_enterprise_context(
        self,
        query: str,
        user_info: Dict[str, Any],
        entity_id: Optional[str] = None,
        user_id: Optional[str] = None,  # Added for compatibility
        top_k: int = 10,
        max_results: Optional[int] = None,  # Added to accept max_results from tools
        similarity_threshold: Optional[float] = None,
        **kwargs  # Accept additional parameters
    ) -> List[Dict[str, Any]]:
        """
        DEPRECATED: Enterprise feature has been removed.
        This method now returns an empty list for backward compatibility.
        """
        logger.info("⚠️ Enterprise context retrieval is deprecated - returning empty results")
        return []

# Global instance
_unified_query_engine = None
_engine_lock = asyncio.Lock()

async def get_unified_query_engine() -> UnifiedQueryEngine:
    """
    Get or create singleton instance of UnifiedQueryEngine
    
    Returns:
        UnifiedQueryEngine instance
    """
    global _unified_query_engine
    
    if _unified_query_engine is None:
        async with _engine_lock:
            if _unified_query_engine is None:
                try:
                    _unified_query_engine = UnifiedQueryEngine()
                    logger.info("🚀 Unified Query Engine singleton created")
                except Exception as e:
                    logger.error(f"❌ Failed to create Unified Query Engine: {e}")
                    raise
    
    return _unified_query_engine

