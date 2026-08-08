"""
Context compression utilities to optimize LLM response times
"""
import logging
import re
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class ContextCompressor:
    """
    Intelligent context compression to reduce token count while preserving relevance
    """
    
    def __init__(self, target_tokens: int = 2000):
        self.target_tokens = target_tokens
        self.avg_chars_per_token = 4  # Rough estimate for English text
    
    def compress_search_results(self, results: List[Dict[str, Any]], query: str) -> Tuple[List[Dict[str, Any]], int]:
        """
        Compress search results by removing redundant content and prioritizing relevance
        
        Args:
            results: List of search result dictionaries
            query: Original query for relevance scoring
            
        Returns:
            Tuple of (compressed_results, tokens_saved)
        """
        if not results:
            return results, 0
        
        original_size = self._estimate_token_count(str(results))
        
        # If already under target, return as-is
        if original_size <= self.target_tokens:
            return results, 0
        
        # Compress each result
        compressed_results = []
        current_tokens = 0
        
        # Sort by relevance (if score available)
        sorted_results = sorted(results, key=lambda x: x.get('score', 0), reverse=True)
        
        for result in sorted_results:
            compressed_result = self._compress_single_result(result, query)
            result_tokens = self._estimate_token_count(str(compressed_result))
            
            if current_tokens + result_tokens <= self.target_tokens:
                compressed_results.append(compressed_result)
                current_tokens += result_tokens
            else:
                # Truncate the last result if we can fit part of it
                remaining_tokens = self.target_tokens - current_tokens
                if remaining_tokens > 100:  # Only if meaningful space remains
                    truncated_result = self._truncate_result(compressed_result, remaining_tokens)
                    if truncated_result:
                        compressed_results.append(truncated_result)
                break
        
        final_size = self._estimate_token_count(str(compressed_results))
        tokens_saved = original_size - final_size
        
        logger.info(f"🗜️ Context compressed: {original_size} → {final_size} tokens (saved {tokens_saved})")
        return compressed_results, tokens_saved
    
    def _compress_single_result(self, result: Dict[str, Any], query: str) -> Dict[str, Any]:
        """
        Compress a single search result by removing verbose content
        """
        compressed = result.copy()
        
        # Compress text field if it exists
        if 'text' in compressed and compressed['text']:
            compressed['text'] = self._compress_text(compressed['text'], query)
        
        # Compress content field if it exists
        if 'content' in compressed and compressed['content']:
            compressed['content'] = self._compress_text(compressed['content'], query)
        
        # Keep only essential metadata
        essential_fields = ['id', 'text', 'content', 'score', 'metadata', 'source']
        compressed = {k: v for k, v in compressed.items() if k in essential_fields}
        
        return compressed
    
    def _compress_text(self, text: str, query: str, max_chars: int = 800) -> str:
        """
        Compress text content while preserving query-relevant information
        """
        if len(text) <= max_chars:
            return text
        
        # Split into sentences
        sentences = re.split(r'[.!?]+', text)
        query_words = set(query.lower().split())
        
        # Score sentences by relevance to query
        scored_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # Count query word matches
            sentence_words = set(sentence.lower().split())
            relevance_score = len(query_words.intersection(sentence_words))
            scored_sentences.append((sentence, relevance_score, len(sentence)))
        
        # Sort by relevance, then by brevity
        scored_sentences.sort(key=lambda x: (-x[1], x[2]))
        
        # Build compressed text
        compressed_text = ""
        for sentence, score, length in scored_sentences:
            if len(compressed_text) + length + 2 <= max_chars:
                compressed_text += sentence + ". "
            else:
                break
        
        return compressed_text.strip()
    
    def _truncate_result(self, result: Dict[str, Any], max_tokens: int) -> Dict[str, Any]:
        """
        Truncate a result to fit within token limit
        """
        max_chars = max_tokens * self.avg_chars_per_token
        
        truncated = result.copy()
        
        # Truncate text fields
        for field in ['text', 'content']:
            if field in truncated and truncated[field]:
                if len(truncated[field]) > max_chars:
                    truncated[field] = truncated[field][:max_chars] + "..."
        
        return truncated
    
    def _estimate_token_count(self, text: str) -> int:
        """
        Rough token count estimation
        """
        return len(text) // self.avg_chars_per_token
    
    def compress_prompt_context(self, prompt_parts: List[str], max_tokens: int = 2000) -> str:
        """
        Compress multiple prompt parts to fit within token limit
        """
        total_text = "\n\n".join(prompt_parts)
        estimated_tokens = self._estimate_token_count(total_text)
        
        if estimated_tokens <= max_tokens:
            return total_text
        
        # Compress by truncating from the end, preserving the beginning (query/instructions)
        max_chars = max_tokens * self.avg_chars_per_token
        if len(total_text) > max_chars:
            total_text = total_text[:max_chars] + "\n\n[Content truncated for performance...]"
        
        logger.info(f"🗜️ Prompt compressed: {estimated_tokens} → {self._estimate_token_count(total_text)} tokens")
        return total_text

# Global compressor instance
context_compressor = ContextCompressor()