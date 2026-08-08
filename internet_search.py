"""
Internet Search Integration for Citra AI RAG System
Provides hybrid context from both Milvus (uploaded data) and internet search results.
"""

import os
import requests
import logging
from typing import List, Dict, Any, Optional
import asyncio
import json
from dataclasses import dataclass
import time
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from utils import embed_text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    """Structure for internet search results"""
    title: str
    snippet: str
    url: str
    score: float = 0.0

class InternetSearchService:
    """Service for performing internet searches and ranking results by relevance"""
    
    def __init__(self):
        self.api_key = os.getenv("SERPER_API_KEY")
        self.api_url = os.getenv("SERPER_API_URL", "https://google.serper.dev/search")
        self.backup_search_enabled = os.getenv("DUCKDUCKGO_FALLBACK", "true").lower() == "true"
        # Initialize embedder (should match the one used for Milvus)
    # Note: Using embeddings via utils.embed_text for consistency with existing RAG system
    logger.info("🌐 Internet search service initialized with embeddingss")
    
    async def search_serper(self, query: str, num_results: int = 6) -> List[SearchResult]:
        """
        Perform search using Serper.dev API (free tier: 100 req/day)
        Sign up at: https://serper.dev/
        """
        if not self.api_key:
            logger.warning("🌐 SERPER_API_KEY not configured, skipping internet search")
            return []
        
        try:
            headers = {
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "q": query,
                "num": num_results,
                "gl": "us",  # Country
                "hl": "en"   # Language
            }
            
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            # Extract organic search results
            for item in data.get("organic", [])[:num_results]:
                if item.get("snippet"):  # Only include results with snippets
                    result = SearchResult(
                        title=item.get("title", ""),
                        snippet=item.get("snippet", ""),
                        url=item.get("link", "")
                    )
                    results.append(result)
            
            logger.info(f"🌐 Serper search returned {len(results)} results for: {query[:50]}...")
            return results
            
        except Exception as e:
            logger.error(f"❌ Serper search failed: {e}")
            # Internet search required - fail fast
            raise RuntimeError(f"Serper search failed: {e}")
    
    async def search_duckduckgo_fallback(self, query: str, num_results: int = 6) -> List[SearchResult]:
        """
        Fallback search using DuckDuckGo Instant Answer API (free, no key required)
        Limited functionality but provides basic results
        """
        try:
            # Simple DuckDuckGo search (limited results)
            params = {
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1"
            }
            
            response = requests.get(
                "https://api.duckduckgo.com/",
                params=params,
                timeout=8
            )
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            # Extract results from DuckDuckGo response
            if data.get("Abstract"):
                result = SearchResult(
                    title=data.get("AbstractText", "DuckDuckGo Result"),
                    snippet=data.get("Abstract", ""),
                    url=data.get("AbstractURL", "")
                )
                results.append(result)
            
            # Add related topics if available
            for topic in data.get("RelatedTopics", [])[:num_results-1]:
                if isinstance(topic, dict) and topic.get("Text"):
                    result = SearchResult(
                        title=topic.get("Text", "")[:100] + "...",
                        snippet=topic.get("Text", ""),
                        url=topic.get("FirstURL", "")
                    )
                    results.append(result)
            
            logger.info(f"🌐 DuckDuckGo fallback returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"❌ DuckDuckGo fallback failed: {e}")
            return []
    
    async def rank_results_by_relevance(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        """Rank search results by semantic similarity using embeddings."""
        if not results:
            return results
        
        try:
            # Embed the query with LLM retrieval query settings
            query_embedding = await embed_text(query, task_type="RETRIEVAL_QUERY")
            
            # ✅ OPTIMIZATION: Batch embeddings for all snippets
            snippet_texts = [result.snippet for result in results]
            try:
                from utils import embed_texts_batch
                snippet_embeddings = await embed_texts_batch(
                    snippet_texts, task_type="RETRIEVAL_DOCUMENT"
                )
                logger.info(
                    f"🚀 BATCH_EMBED: Generated embeddings for {len(snippet_texts)} search snippets with LLM"
                )
            except Exception as e:
                logger.error(f"❌ Batch embedding failed: {e}")
                # Embedding required - fail fast
                raise RuntimeError(f"Batch embedding failed for search results: {e}")
            
            # Calculate cosine similarities
            query_array = np.array(query_embedding).reshape(1, -1)
            snippet_arrays = np.array(snippet_embeddings)
            
            similarities = cosine_similarity(query_array, snippet_arrays)[0]
            
            # Assign scores and sort
            for i, result in enumerate(results):
                result.score = float(similarities[i])
            
            # Sort by relevance score (highest first)
            ranked_results = sorted(results, key=lambda x: x.score, reverse=True)
            
            logger.info(
                f"🌐 Ranked {len(ranked_results)} results by relevance using embeddings"
            )
            return ranked_results
            
        except Exception as e:
            logger.error(f"❌ Failed to rank results: {e}")
            return results
    
    async def get_internet_context(self, query: str, max_results: int = 3) -> List[Dict[str, Any]]:
        """
        Get internet search results formatted as context for RAG
        
        Args:
            query: User's search query
            max_results: Maximum number of results to return
            
        Returns:
            List of context dictionaries compatible with Milvus format
        """
        # Skip if internet search is disabled
        if os.getenv("INTERNET_SEARCH_ENABLED", "true").lower() == "false":
            logger.info("🌐 Internet search disabled via environment variable")
            return []
        
        try:
            # Perform search
            results = await self.search_serper(query, num_results=max_results * 2)  # Get extra for filtering
            
            if not results:
                logger.info("🌐 No internet search results found")
                return []
            
            # Rank by relevance
            ranked_results = await self.rank_results_by_relevance(query, results)
            
            # Convert to context format
            contexts = []
            for i, result in enumerate(ranked_results[:max_results]):
                context = {
                    "text": result.snippet,
                    "topic": f"{result.title}--{result.url}",
                    "source": f"🌐 {result.title} ({result.url})",
                    "score": result.score,
                    "metadata": {
                        "type": "internet",
                        "title": result.title,  # Include title in metadata for InternetSearchTool
                        "url": result.url,
                        "rank": i + 1
                    }
                }
                contexts.append(context)
            
            logger.info(f"🌐 Generated {len(contexts)} internet contexts")
            return contexts
            
        except Exception as e:
            logger.error(f"❌ Failed to get internet context: {e}")
            return []

# Global internet search service instance
_internet_service = None

def get_internet_service() -> InternetSearchService:
    """Get the global internet search service instance"""
    global _internet_service
    if _internet_service is None:
        _internet_service = InternetSearchService()
    return _internet_service

async def get_hybrid_context(query: str, Milvus_contexts: List[Dict], use_internet: bool, max_internet_results: int = 3) -> List[Dict]:
    """
    Combine Milvus contexts with internet search results for hybrid RAG
    
    Args:
        query: User's query
        Milvus_contexts: Existing contexts from Milvus (can be strings or dicts)
        use_internet: Whether to include internet results
        max_internet_results: Maximum number of internet results to include
        
    Returns:
        Combined and ranked context list
    """
    # Start with Milvus contexts - normalize to dict format
    all_contexts = []
    if Milvus_contexts:
        for ctx in Milvus_contexts:
            if isinstance(ctx, dict):
                all_contexts.append(ctx)
            elif isinstance(ctx, str):
                # Convert string context to dict format
                all_contexts.append({
                    "text": ctx,
                    "source": "Milvus",
                    "score": 0.8  # Default score for string contexts
                })
            else:
                logger.warning(f"Unknown context type: {type(ctx)}, skipping")
    
    # Add internet contexts if requested
    if use_internet:
        internet_service = get_internet_service()
        internet_contexts = await internet_service.get_internet_context(query, max_internet_results)
        
        # Add internet contexts without prioritization - balanced approach
        all_contexts.extend(internet_contexts)
        
        logger.info(f"🔄 Hybrid context: {len(Milvus_contexts)} Milvus + {len(internet_contexts)} Internet = {len(all_contexts)} total")
    else:
        logger.info(f"🔄 Using only Milvus context: {len(all_contexts)} results")
    
    # Sort by relevance score with balanced ordering
    try:
        # Sort all contexts by score without source type prioritization
        all_contexts.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        logging.info(f"🔄 Sorted {len(all_contexts)} contexts by relevance score (balanced approach)")
        
    except (KeyError, TypeError):
        logger.debug("Context items don't have comparable scores, keeping original order")
    
    # Apply context limit
    context_limit = int(os.getenv("HYBRID_CONTEXT_LIMIT", "15"))
    if len(all_contexts) > context_limit:
        all_contexts = all_contexts[:context_limit]
        logger.info(f"🔄 Limited hybrid context to {context_limit} items")
    
    return all_contexts
