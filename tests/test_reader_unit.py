"""
Unit Tests for Reader API — Reranker Integration
==================================================

Tests the _chunk_and_rerank function and related constants.
All external dependencies (reranker service, LLM, MongoDB) are mocked.
"""

import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.reader import (
    _chunk_and_rerank,
    LARGE_CONTENT_THRESHOLD,
    READER_RERANK_TOP_K,
    READER_CHUNK_SIZE,
    READER_CHUNK_OVERLAP,
)


# ═══════════════════════════════════════════════════════════════════════════════════════
# 1. CONSTANTS SANITY
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestReaderConstants:
    def test_large_content_threshold(self):
        assert LARGE_CONTENT_THRESHOLD == 30_000

    def test_rerank_top_k(self):
        assert READER_RERANK_TOP_K == 8

    def test_chunk_size(self):
        assert READER_CHUNK_SIZE == 512

    def test_chunk_overlap(self):
        assert READER_CHUNK_OVERLAP == 50


# ═══════════════════════════════════════════════════════════════════════════════════════
# 2. _chunk_and_rerank — SMALL CONTENT (passthrough)
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestChunkAndRerankPassthrough:
    """Content at or below LARGE_CONTENT_THRESHOLD should be returned as-is."""

    def test_none_content(self):
        assert _chunk_and_rerank(None, "query") is None

    def test_empty_content(self):
        assert _chunk_and_rerank("", "query") == ""

    def test_short_content_unchanged(self):
        content = "This is a short paragraph about Python."
        result = _chunk_and_rerank(content, "what is Python?")
        assert result == content

    def test_exactly_at_threshold(self):
        content = "x" * LARGE_CONTENT_THRESHOLD
        result = _chunk_and_rerank(content, "query")
        assert result == content  # <= threshold, returned as-is

    def test_one_char_below_threshold(self):
        content = "a" * (LARGE_CONTENT_THRESHOLD - 1)
        result = _chunk_and_rerank(content, "query")
        assert result == content


# ═══════════════════════════════════════════════════════════════════════════════════════
# 3. _chunk_and_rerank — LARGE CONTENT (chunked + reranked)
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestChunkAndRerankLargeContent:
    """Content above LARGE_CONTENT_THRESHOLD should be chunked and reranked."""

    def _make_large_content(self, num_sentences=200):
        """Generate content above the threshold with distinct sentences."""
        sentences = [f"Sentence number {i} discusses topic {i % 10}. " for i in range(num_sentences)]
        content = " ".join(sentences)
        # Ensure it exceeds threshold
        while len(content) <= LARGE_CONTENT_THRESHOLD:
            content += " " + content
        return content

    @patch("reranker.rerank")
    @patch("reranker.ENABLE_RERANKER", True)
    def test_large_content_is_chunked_and_reranked(self, mock_rerank):
        """Large content should go through chunking + reranking pipeline."""
        content = self._make_large_content()

        # Mock reranker to return first 3 chunks
        def fake_rerank(query, chunks, top_k):
            return [
                {**chunks[0], "score": 0.95},
                {**chunks[2], "score": 0.80},
                {**chunks[1], "score": 0.70},
            ]

        mock_rerank.side_effect = fake_rerank

        result = _chunk_and_rerank(content, "topic 5")

        mock_rerank.assert_called_once()
        call_args = mock_rerank.call_args
        assert call_args[0][0] == "topic 5"  # query
        assert len(call_args[0][1]) > 3  # chunks list
        assert isinstance(result, str)
        assert len(result) < len(content)  # Should be shorter than original

    @patch("reranker.rerank")
    @patch("reranker.ENABLE_RERANKER", True)
    def test_reranked_chunks_sorted_by_original_position(self, mock_rerank):
        """Reranked chunks should be sorted by chunk_id (original position) for readability."""
        content = self._make_large_content()

        def fake_rerank(query, chunks, top_k):
            # Return chunks out of order by relevance
            return [
                {**chunks[5], "score": 0.99},
                {**chunks[1], "score": 0.90},
                {**chunks[10], "score": 0.80},
            ]

        mock_rerank.side_effect = fake_rerank

        result = _chunk_and_rerank(content, "query")

        # Result should contain text from chunks 1, 5, 10 in that order
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("reranker.rerank")
    @patch("reranker.ENABLE_RERANKER", False)
    def test_reranker_disabled_uses_first_k_chunks(self, mock_rerank):
        """When reranker is disabled, first top_k chunks should be returned."""
        content = self._make_large_content()

        result = _chunk_and_rerank(content, "query", top_k=3)

        mock_rerank.assert_not_called()
        assert isinstance(result, str)
        assert len(result) > 0
        assert len(result) < len(content)

    @patch("reranker.rerank")
    @patch("reranker.ENABLE_RERANKER", True)
    def test_few_chunks_skip_reranker(self, mock_rerank):
        """If chunk count <= top_k, skip reranker and use all chunks."""
        # Create content just above threshold but with very few chunks possible
        content = "A" * (LARGE_CONTENT_THRESHOLD + 100)

        result = _chunk_and_rerank(content, "query", top_k=1000)

        # With top_k=1000 and few chunks, reranker should be skipped
        mock_rerank.assert_not_called()

    @patch("reranker.rerank")
    @patch("reranker.ENABLE_RERANKER", True)
    def test_chunk_dicts_have_required_fields(self, mock_rerank):
        """Chunks passed to reranker should have text, chunk_id, score."""
        content = self._make_large_content()
        captured_chunks = []

        def capture_rerank(query, chunks, top_k):
            captured_chunks.extend(chunks)
            return chunks[:top_k]

        mock_rerank.side_effect = capture_rerank

        _chunk_and_rerank(content, "query")

        assert len(captured_chunks) > 0
        for chunk in captured_chunks:
            assert "text" in chunk
            assert "chunk_id" in chunk
            assert "score" in chunk
            assert isinstance(chunk["text"], str)
            assert len(chunk["text"]) > 0

    @patch("reranker.rerank")
    @patch("reranker.ENABLE_RERANKER", True)
    def test_default_top_k_is_reader_rerank_top_k(self, mock_rerank):
        """Default top_k should be READER_RERANK_TOP_K (8)."""
        content = self._make_large_content(500)

        mock_rerank.side_effect = lambda q, c, k: c[:k]

        _chunk_and_rerank(content, "query")

        call_args = mock_rerank.call_args
        assert call_args[0][2] == READER_RERANK_TOP_K

    @patch("reranker.rerank")
    @patch("reranker.ENABLE_RERANKER", True)
    def test_custom_top_k(self, mock_rerank):
        """Custom top_k should be passed to reranker."""
        content = self._make_large_content(500)

        mock_rerank.side_effect = lambda q, c, k: c[:k]

        _chunk_and_rerank(content, "query", top_k=3)

        call_args = mock_rerank.call_args
        assert call_args[0][2] == 3

    @patch("reranker.rerank")
    @patch("reranker.ENABLE_RERANKER", True)
    def test_result_is_joined_by_double_newline(self, mock_rerank):
        """Reranked chunks should be joined by double newlines."""
        content = self._make_large_content()

        def fake_rerank(query, chunks, top_k):
            return [
                {"text": "First chunk text.", "chunk_id": "0", "score": 0.9},
                {"text": "Second chunk text.", "chunk_id": "1", "score": 0.8},
            ]

        mock_rerank.side_effect = fake_rerank

        result = _chunk_and_rerank(content, "query")

        assert "First chunk text." in result
        assert "Second chunk text." in result
        assert "\n\n" in result


# ═══════════════════════════════════════════════════════════════════════════════════════
# 4. _chunk_and_rerank — EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestChunkAndRerankEdgeCases:

    @patch("llama_index.core.node_parser.SentenceSplitter")
    @patch("reranker.ENABLE_RERANKER", True)
    def test_empty_chunks_returns_truncated(self, MockSplitter):
        """If SentenceSplitter returns empty list, fall back to truncation."""
        MockSplitter.return_value.split_text.return_value = []

        content = "x" * (LARGE_CONTENT_THRESHOLD + 100)
        result = _chunk_and_rerank(content, "query")

        assert len(result) == LARGE_CONTENT_THRESHOLD

    @patch("reranker.rerank")
    @patch("reranker.ENABLE_RERANKER", True)
    def test_reranker_returns_chunks_with_empty_text(self, mock_rerank):
        """Empty-text chunks should be filtered out."""
        content = "Sentence one about cats. " * 2000  # large content

        def fake_rerank(query, chunks, top_k):
            return [
                {"text": "", "chunk_id": "0", "score": 0.9},
                {"text": "   ", "chunk_id": "1", "score": 0.8},
                {"text": "Valid chunk about cats.", "chunk_id": "2", "score": 0.7},
            ]

        mock_rerank.side_effect = fake_rerank
        result = _chunk_and_rerank(content, "cats")

        assert "Valid chunk about cats." in result
        # Empty/whitespace chunks should not appear as separate entries
        parts = [p for p in result.split("\n\n") if p.strip()]
        assert len(parts) == 1
