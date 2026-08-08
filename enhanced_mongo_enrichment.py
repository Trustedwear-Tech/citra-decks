"""
Enhanced MongoDB Query Enrichment with Semantic Relevance Checking
================================================================

This module provides advanced MongoDB query enrichment that uses semantic similarity
to ensure only relevant enrichments are applied, preventing issues like getting
"Citra AI Software" when searching for "US-India tariffs".

Features:
- Semantic relevance checking with embeddingss
- Cosine similarity filtering (threshold 0.5)
- Smart acronym expansion with contextual validation
- Robust error handling and fallbacks
"""

import logging
import re
import numpy as np
from typing import Optional


async def enrich_query_from_mongo_with_relevance(original_query: str, user_id: str) -> str:
    """
    Enhanced MongoDB query enrichment with semantic relevance checking.
    Only uses enrichment if it's actually relevant to the query intent.
    
    Args:
        original_query: User's original query
        user_id: User's device ID for personal data filtering
        
    Returns:
        Enhanced query with relevant enrichments or original query if no relevant enrichments found
    """
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"🔍 Enhanced MongoDB Enrichment: Starting for query: '{original_query}'")
        
        # Step 1: Get basic enrichment from MongoDB
        from query import enrich_query_with_mongodb
        enriched = await enrich_query_with_mongodb(original_query, user_id)
        
        # Step 2: If no enrichment or same as original, return original
        if not enriched or enriched == original_query:
            logger.info("🔍 Enhanced MongoDB Enrichment: No enrichment found")
            return original_query
        
        # Step 3: Extract what was added by enrichment
        added_context = enriched.replace(original_query, '').strip()
        if not added_context:
            return original_query
        
        logger.info(f"🔍 Enhanced MongoDB Enrichment: Added context: '{added_context[:100]}...'")
        
        # Step 4: Check semantic relevance using embeddings
        try:
            # Use embeddings from utils
            from utils import embed_text
            
            # Generate embeddings for both
            original_embedding = await embed_text(original_query, task_type="RETRIEVAL_QUERY")
            enrichment_embedding = await embed_text(added_context, task_type="RETRIEVAL_QUERY")
            
            # Calculate cosine similarity
            similarity = np.dot(original_embedding, enrichment_embedding) / (
                np.linalg.norm(original_embedding) * np.linalg.norm(enrichment_embedding)
            )
            
            logger.info(f"🔍 Enhanced MongoDB Enrichment: Semantic similarity: {similarity:.3f}")
            
            # Step 5: Apply relevance threshold
            RELEVANCE_THRESHOLD = 0.5  # Adjust based on testing
            
            if similarity < RELEVANCE_THRESHOLD:
                logger.warning(f"⚠️ Enhanced MongoDB Enrichment rejected - Low relevance: {similarity:.3f}")
                logger.warning(f"⚠️ Original: '{original_query}'")
                logger.warning(f"⚠️ Attempted enrichment: '{added_context[:100]}...'")
                return original_query
            
            # Step 6: Smart acronym expansion based on context
            enriched_with_smart_expansion = await smart_acronym_expansion(
                original_query, added_context, similarity
            )
            
            if enriched_with_smart_expansion:
                logger.info(f"✅ Enhanced MongoDB Enrichment accepted with smart expansion")
                return enriched_with_smart_expansion
            
            logger.info(f"✅ Enhanced MongoDB Enrichment accepted - Similarity: {similarity:.3f}")
            return enriched
            
        except ImportError:
            logger.warning("⚠️ embedding service not available, using original enrichment without relevance check")
            return enriched
        except Exception as embed_error:
            logger.warning(f"⚠️ Embedding similarity check failed: {embed_error}, using original enrichment")
            return enriched
        
    except Exception as e:
        logger.error(f"❌ Enhanced MongoDB enrichment failed: {e}")
        return original_query


async def smart_acronym_expansion(original_query: str, mongo_context: str, similarity: float) -> Optional[str]:
    """
    Smart acronym expansion that considers context relevance
    
    Args:
        original_query: User's original query
        mongo_context: Context from MongoDB enrichment
        similarity: Semantic similarity score
        
    Returns:
        Enhanced query with smart acronym expansions or None if no expansions found
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Extract potential acronyms from original query
        acronyms = re.findall(r'\b[A-Z]{2,}\b', original_query)
        
        if not acronyms:
            return None
        
        logger.info(f"🔤 Found acronyms to expand: {acronyms}")
        
        # Look for expansions in MongoDB context
        expansions = {}
        for acronym in acronyms:
            # Search for patterns like "FER (First Examination Report)" or "First Examination Report (FER)"
            pattern1 = rf"{acronym}\s*\(([^)]+)\)"
            pattern2 = rf"([^(]+)\s*\({acronym}\)"
            
            match1 = re.search(pattern1, mongo_context, re.IGNORECASE)
            match2 = re.search(pattern2, mongo_context, re.IGNORECASE)
            
            if match1:
                expansion = match1.group(1).strip()
                if len(expansion.split()) <= 5:  # Reasonable expansion length
                    expansions[acronym] = expansion
                    logger.info(f"🔤 Found expansion pattern 1: {acronym} → {expansion}")
            elif match2:
                expansion = match2.group(1).strip()
                if len(expansion.split()) <= 5:  # Reasonable expansion length
                    expansions[acronym] = expansion
                    logger.info(f"🔤 Found expansion pattern 2: {acronym} → {expansion}")
        
        if not expansions:
            return None
        
        # Build enhanced query with expansions
        enhanced_query = original_query
        for acronym, expansion in expansions.items():
            # Add expansion as context, not replacement
            enhanced_query = enhanced_query.replace(
                acronym, 
                f"{acronym} ({expansion})"
            )
        
        logger.info(f"✅ Smart acronym expansion: {expansions}")
        return enhanced_query
        
    except Exception as e:
        logger.error(f"Smart acronym expansion failed: {e}")
        return None
