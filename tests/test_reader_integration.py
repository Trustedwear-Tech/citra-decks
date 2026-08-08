"""
Integration Tests for Reader API — Chat Endpoints
====================================================

Tests the chat endpoints through FastAPI TestClient with:
- Mocked auth (skips JWT verification)
- Mocked LLM (reply function)
- Mocked reranker service
- Mocked MongoDB

Prerequisites:
  pip install pytest pytest-asyncio httpx
"""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# ═══════════════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════════════

TEST_USER_ID = "testuser@example.com"
TEST_USER_EMAIL = "testuser@example.com"

SMALL_PAGE_CONTENT = "Python is a high-level programming language. It supports multiple paradigms."
LARGE_PAGE_CONTENT = "Sentence about machine learning topic. " * 1500  # ~55K chars, above 30K threshold


def _mock_reply(prompt, static_context=None, conversation_history=None,
                enable_internet_search=False, user_id=None, user_email=None, **kwargs):
    """Mock the reply() LLM function to return a canned response."""
    return f"AI response to: {prompt}"


class FakeRequestState:
    user_id = TEST_USER_ID
    user_email = TEST_USER_EMAIL


class FakeRequest:
    state = FakeRequestState()

    async def json(self):
        return self._body

    def __init__(self, body):
        self._body = body


@pytest.fixture
def app():
    """Create and configure the FastAPI app with mocked dependencies."""
    with patch("api.reader.reply", side_effect=_mock_reply), \
         patch("api.reader.get_mongo_client") as mock_mongo:

        # Mock MongoDB collections
        mock_db = MagicMock()
        mock_mongo.return_value.__getitem__ = MagicMock(return_value=mock_db)

        from fastapi import FastAPI
        from api.reader import router

        test_app = FastAPI()
        test_app.include_router(router)

        # Add middleware to inject user state
        @test_app.middleware("http")
        async def inject_user(request, call_next):
            request.state.user_id = TEST_USER_ID
            request.state.user_email = TEST_USER_EMAIL
            return await call_next(request)

        yield test_app


@pytest_asyncio.fixture
async def client(app):
    """Async HTTP client bound to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ═══════════════════════════════════════════════════════════════════════════════════════
# 1. HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


# ═══════════════════════════════════════════════════════════════════════════════════════
# 2. INTERNET CHAT — /internet/chat
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestInternetChat:
    @pytest.mark.asyncio
    async def test_basic_chat(self, client):
        resp = await client.post("/internet/chat", json={
            "url": "https://example.com",
            "query": "What is this page about?",
            "page_content": SMALL_PAGE_CONTENT,
            "page_title": "Test Page",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["query"] == "What is this page about?"
        assert "AI response" in data["response"]
        assert data["url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_missing_query_returns_400(self, client):
        resp = await client.post("/internet/chat", json={
            "url": "https://example.com",
            "page_content": SMALL_PAGE_CONTENT,
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_query_returns_400(self, client):
        resp = await client.post("/internet/chat", json={
            "url": "https://example.com",
            "query": "",
            "page_content": SMALL_PAGE_CONTENT,
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_with_conversation_history(self, client):
        resp = await client.post("/internet/chat", json={
            "url": "https://example.com",
            "query": "Tell me more",
            "page_content": SMALL_PAGE_CONTENT,
            "conversation_history": [
                {"role": "user", "content": "What is Python?"},
                {"role": "assistant", "content": "Python is a programming language."},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["cache_hit_expected"] is True  # has history

    @pytest.mark.asyncio
    async def test_first_question_cache_hint(self, client):
        resp = await client.post("/internet/chat", json={
            "query": "First question",
            "page_content": SMALL_PAGE_CONTENT,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["cache_hit_expected"] is False  # no history

    @pytest.mark.asyncio
    async def test_history_capped_at_8(self, client):
        """Conversation history >8 should be capped — no error."""
        history = [{"role": "user", "content": f"msg {i}"} for i in range(12)]
        resp = await client.post("/internet/chat", json={
            "query": "Latest question",
            "page_content": SMALL_PAGE_CONTENT,
            "conversation_history": history,
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @patch("api.reader._chunk_and_rerank")
    async def test_large_content_triggers_reranker(self, mock_rerank, client):
        """Content above 30K chars should trigger _chunk_and_rerank via asyncio.to_thread."""
        mock_rerank.return_value = "Reranked relevant chunks about ML."

        resp = await client.post("/internet/chat", json={
            "url": "https://example.com",
            "query": "What about ML?",
            "page_content": LARGE_PAGE_CONTENT,
        })
        assert resp.status_code == 200
        mock_rerank.assert_called_once()
        # Verify the query was passed
        call_args = mock_rerank.call_args
        assert call_args[0][1] == "What about ML?"  # query argument

    @pytest.mark.asyncio
    async def test_small_content_skips_reranker(self, client):
        """Content below 30K chars should NOT trigger reranker."""
        with patch("api.reader._chunk_and_rerank") as mock_rerank:
            mock_rerank.return_value = SMALL_PAGE_CONTENT

            resp = await client.post("/internet/chat", json={
                "query": "Simple question",
                "page_content": SMALL_PAGE_CONTENT,
            })
            assert resp.status_code == 200
            mock_rerank.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_page_content(self, client):
        """Missing page_content should not crash — relies on web search."""
        resp = await client.post("/internet/chat", json={
            "url": "https://example.com",
            "query": "What is on this page?",
        })
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════════════
# 3. DOCUMENT CHAT — /document/chat
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestDocumentChat:
    @pytest.mark.asyncio
    async def test_basic_document_chat(self, client):
        resp = await client.post("/document/chat", json={
            "document_id": "doc123",
            "query": "Summarize this document",
            "document_content": SMALL_PAGE_CONTENT,
            "document_title": "Test Doc",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["document_id"] == "doc123"
        assert "AI response" in data["response"]

    @pytest.mark.asyncio
    async def test_missing_query_returns_400(self, client):
        resp = await client.post("/document/chat", json={
            "document_id": "doc123",
            "document_content": SMALL_PAGE_CONTENT,
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_document_content_returns_400(self, client):
        resp = await client.post("/document/chat", json={
            "document_id": "doc123",
            "query": "Summarize",
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    @patch("api.reader._chunk_and_rerank")
    async def test_large_document_triggers_reranker(self, mock_rerank, client):
        """Document content above 30K chars should trigger reranker."""
        mock_rerank.return_value = "Reranked document chunks."

        resp = await client.post("/document/chat", json={
            "document_id": "doc123",
            "query": "Key findings?",
            "document_content": LARGE_PAGE_CONTENT,
        })
        assert resp.status_code == 200
        mock_rerank.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_conversation_history(self, client):
        resp = await client.post("/document/chat", json={
            "document_id": "doc123",
            "query": "What else?",
            "document_content": SMALL_PAGE_CONTENT,
            "conversation_history": [
                {"role": "user", "content": "Summarize"},
                {"role": "assistant", "content": "This doc is about Python."},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["cache_hit_expected"] is True


# ═══════════════════════════════════════════════════════════════════════════════════════
# 4. STREAMING INTERNET CHAT — /internet/chat/stream
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestInternetChatStream:
    @pytest.mark.asyncio
    @patch("api.reader._chunk_and_rerank")
    async def test_large_content_triggers_reranker_in_stream(self, mock_rerank, client):
        """Streaming endpoint should also use reranker for large content."""
        mock_rerank.return_value = "Relevant chunks for streaming."

        with patch("api.reader.stream_llm_response", new_callable=AsyncMock) as mock_stream:
            async def fake_stream(**kwargs):
                from streaming_response import StreamEvent, StreamEventType
                yield StreamEvent(StreamEventType.CHUNK, {"text": "Hello"})
                yield StreamEvent(StreamEventType.DONE, {})

            mock_stream.side_effect = fake_stream

            resp = await client.post("/internet/chat/stream", json={
                "url": "https://example.com",
                "query": "What about ML?",
                "page_content": LARGE_PAGE_CONTENT,
            })
            assert resp.status_code == 200
            mock_rerank.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_missing_query_returns_400(self, client):
        resp = await client.post("/internet/chat/stream", json={
            "url": "https://example.com",
            "page_content": SMALL_PAGE_CONTENT,
        })
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════════════
# 5. STREAMING DOCUMENT CHAT — /document/chat/stream
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestDocumentChatStream:
    @pytest.mark.asyncio
    @patch("api.reader._chunk_and_rerank")
    async def test_large_document_triggers_reranker_in_stream(self, mock_rerank, client):
        """Streaming document chat should also use reranker for large content."""
        mock_rerank.return_value = "Relevant doc chunks."

        with patch("api.reader.stream_llm_response", new_callable=AsyncMock) as mock_stream:
            async def fake_stream(**kwargs):
                from streaming_response import StreamEvent, StreamEventType
                yield StreamEvent(StreamEventType.CHUNK, {"text": "Doc answer"})
                yield StreamEvent(StreamEventType.DONE, {})

            mock_stream.side_effect = fake_stream

            resp = await client.post("/document/chat/stream", json={
                "document_id": "doc456",
                "query": "Key details?",
                "document_content": LARGE_PAGE_CONTENT,
            })
            assert resp.status_code == 200
            mock_rerank.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_missing_query_returns_400(self, client):
        resp = await client.post("/document/chat/stream", json={
            "document_id": "doc456",
            "document_content": SMALL_PAGE_CONTENT,
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_stream_missing_document_content_returns_400(self, client):
        resp = await client.post("/document/chat/stream", json={
            "document_id": "doc456",
            "query": "Summarize",
        })
        assert resp.status_code == 400
