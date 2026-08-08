"""Unit tests for ``services.action_chat_bridge``.

Covers:
  - SSE frame parser (multi-frame, partial frame, heartbeat, malformed)
  - Event translator (message → CHUNK, artifact → ARTIFACT, drop list)
  - End-to-end bridge happy path (mocked httpx stream)
  - End-to-end bridge failure paths (connect error, mid-stream truncate,
    upstream non-200, missing JWT)
  - Heartbeat emission when upstream goes quiet
  - Always terminates with DONE
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import AsyncIterator

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from streaming_response import StreamEvent, StreamEventType  # noqa: E402
from services import action_chat_bridge as bridge_mod  # noqa: E402
from services.action_chat_bridge import (  # noqa: E402
    _parse_sse_frames,
    _translate,
    _DROP,
    bridge_to_action_chat,
)


# ─── SSE frame parser ────────────────────────────────────────────────────────

def test_parse_two_complete_frames():
    buf = (
        'event: message\ndata: {"type":"message","text":"hello"}\n\n'
        'event: artifact\ndata: {"type":"artifact","kind":"pdf","url":"https://x/y.pdf"}\n\n'
    )
    events, tail = _parse_sse_frames(buf)
    assert tail == ""
    assert len(events) == 2
    assert events[0] == {"type": "message", "text": "hello"}
    assert events[1]["type"] == "artifact"
    assert events[1]["url"] == "https://x/y.pdf"


def test_parse_partial_frame_returns_tail():
    buf = (
        'event: message\ndata: {"type":"message","text":"complete"}\n\n'
        'event: message\ndata: {"type":"message","text":"partia'  # no trailing \n\n
    )
    events, tail = _parse_sse_frames(buf)
    assert len(events) == 1
    assert events[0]["text"] == "complete"
    assert tail.startswith('event: message')
    assert "partia" in tail


def test_parse_heartbeat_comments_are_dropped():
    buf = ': heartbeat\n\n' 'event: message\ndata: {"type":"message","text":"ok"}\n\n'
    events, tail = _parse_sse_frames(buf)
    assert len(events) == 1
    assert events[0]["text"] == "ok"


def test_parse_malformed_json_is_skipped():
    buf = (
        'event: message\ndata: not-json\n\n'
        'event: message\ndata: {"type":"message","text":"good"}\n\n'
    )
    events, tail = _parse_sse_frames(buf)
    assert len(events) == 1
    assert events[0]["text"] == "good"


def test_parse_empty_buffer_returns_nothing():
    events, tail = _parse_sse_frames("")
    assert events == []
    assert tail == ""


# ─── event translator ────────────────────────────────────────────────────────

def test_translate_message_becomes_chunk():
    evt = _translate({"type": "message", "text": "hello"})
    assert isinstance(evt, StreamEvent)
    assert evt.event_type == StreamEventType.CHUNK
    assert evt.data["text"] == "hello"


def test_translate_empty_message_dropped():
    assert _translate({"type": "message", "text": ""}) is _DROP


def test_translate_artifact_preserves_fields():
    raw = {
        "type": "artifact",
        "kind": "pptx",
        "title": "Bird Life Deck",
        "filename": "bird-life.pptx",
        "url": "https://s3/bird-life.pptx",
        "size": 1024,
        "summary": "10 slides",
    }
    evt = _translate(raw)
    assert isinstance(evt, StreamEvent)
    assert evt.event_type == StreamEventType.ARTIFACT
    for k in ("kind", "title", "filename", "url", "size", "summary"):
        assert evt.data[k] == raw[k]
    assert evt.data["source"] == "action_chat"


def test_translate_artifact_accepts_download_url_field():
    evt = _translate({"type": "artifact", "kind": "pdf", "download_url": "https://x.pdf"})
    assert evt.event_type == StreamEventType.ARTIFACT
    assert evt.data["url"] == "https://x.pdf"


@pytest.mark.parametrize("etype,expected", [
    ("tool_call", StreamEventType.TOOL_STATUS),
    ("tool_result", StreamEventType.TOOL_STATUS),
    ("plan", StreamEventType.PLAN),
    ("status", StreamEventType.STAGE),
    ("email_sent", StreamEventType.CHUNK),
    ("cancelled", StreamEventType.CHUNK),
    ("error", StreamEventType.ERROR),
])
def test_translate_other_types(etype: str, expected: StreamEventType):
    evt = _translate({"type": etype, "name": "x", "text": "y", "items": [], "message": "z"})
    assert isinstance(evt, StreamEvent)
    assert evt.event_type == expected


@pytest.mark.parametrize("etype", ["thinking", "canvas_event", "html_block", "done"])
def test_translate_drops_ui_only_or_terminal_events(etype: str):
    assert _translate({"type": etype}) is _DROP


def test_translate_unknown_type_dropped():
    assert _translate({"type": "made_up_event"}) is _DROP


def test_translate_non_dict_returns_none():
    assert _translate("not a dict") is None  # type: ignore[arg-type]


# ─── end-to-end bridge ───────────────────────────────────────────────────────

class _FakeResponse:
    """Stand-in for httpx response.stream context that yields predetermined
    SSE text chunks."""

    def __init__(self, status_code: int, chunks: list[str], raise_after_chunk: Exception | None = None):
        self.status_code = status_code
        self._chunks = chunks
        self._raise_after_chunk = raise_after_chunk

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def aiter_text(self) -> AsyncIterator[str]:
        for c in self._chunks:
            yield c
            await asyncio.sleep(0)
        if self._raise_after_chunk:
            raise self._raise_after_chunk

    async def aread(self) -> bytes:
        return b""


class _FakeClient:
    def __init__(self, response: _FakeResponse, raise_on_stream: Exception | None = None):
        self._response = response
        self._raise_on_stream = raise_on_stream

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    def stream(self, method, url, **kwargs):
        if self._raise_on_stream:
            raise self._raise_on_stream
        return self._response


@pytest.mark.asyncio
async def test_bridge_happy_path(monkeypatch):
    chunks = [
        ': heartbeat\n\n',
        'event: message\ndata: {"type":"message","text":"Generating deck…"}\n\n',
        'event: tool_call\ndata: {"type":"tool_call","name":"image.generate"}\n\n',
        'event: artifact\ndata: {"type":"artifact","kind":"pptx","title":"Bird Life","url":"https://s3/bird.pptx","size":2048}\n\n',
        'event: message\ndata: {"type":"message","text":"Done. Your deck is ready."}\n\n',
    ]
    fake_resp = _FakeResponse(200, chunks)
    monkeypatch.setattr(
        bridge_mod.httpx, "AsyncClient",
        lambda *a, **kw: _FakeClient(fake_resp),
    )

    out: list[StreamEvent] = []
    async for evt in bridge_to_action_chat(
        message="create a presentation on bird life",
        multimodal_attachments=None,
        jwt_token="fake-token",
        intent="presentation",
    ):
        out.append(evt)

    types = [e.event_type for e in out]
    # Should contain at least: CHUNK (text), TOOL_STATUS, ARTIFACT, CHUNK, DONE
    assert StreamEventType.CHUNK in types
    assert StreamEventType.TOOL_STATUS in types
    assert StreamEventType.ARTIFACT in types
    # DONE must be the last event
    assert types[-1] == StreamEventType.DONE
    assert out[-1].data["bridged"] is True
    assert out[-1].data["intent"] == "presentation"
    assert out[-1].data["events_seen"] is True

    # The artifact must come through with correct shape
    art = next(e for e in out if e.event_type == StreamEventType.ARTIFACT)
    assert art.data["kind"] == "pptx"
    assert art.data["url"] == "https://s3/bird.pptx"
    assert art.data["title"] == "Bird Life"
    assert art.data["size"] == 2048


@pytest.mark.asyncio
async def test_bridge_no_jwt_emits_error_then_done():
    out: list[StreamEvent] = []
    async for evt in bridge_to_action_chat(
        message="x", multimodal_attachments=None, jwt_token=None, intent="report",
    ):
        out.append(evt)
    assert [e.event_type for e in out] == [StreamEventType.ERROR, StreamEventType.DONE]
    assert "missing auth token" in out[0].data["message"].lower()


@pytest.mark.asyncio
async def test_bridge_upstream_non_200(monkeypatch):
    fake_resp = _FakeResponse(503, [])
    monkeypatch.setattr(
        bridge_mod.httpx, "AsyncClient",
        lambda *a, **kw: _FakeClient(fake_resp),
    )
    out: list[StreamEvent] = []
    async for evt in bridge_to_action_chat(
        message="x", multimodal_attachments=None, jwt_token="t", intent="report",
    ):
        out.append(evt)
    types = [e.event_type for e in out]
    assert StreamEventType.ERROR in types
    assert types[-1] == StreamEventType.DONE
    err = next(e for e in out if e.event_type == StreamEventType.ERROR)
    assert "503" in err.data["message"]


@pytest.mark.asyncio
async def test_bridge_connect_failure(monkeypatch):
    monkeypatch.setattr(
        bridge_mod.httpx, "AsyncClient",
        lambda *a, **kw: _FakeClient(
            _FakeResponse(200, []),
            raise_on_stream=bridge_mod.httpx.ConnectError("no route"),
        ),
    )
    out: list[StreamEvent] = []
    async for evt in bridge_to_action_chat(
        message="x", multimodal_attachments=None, jwt_token="t", intent="report",
    ):
        out.append(evt)
    types = [e.event_type for e in out]
    assert StreamEventType.ERROR in types
    assert types[-1] == StreamEventType.DONE


@pytest.mark.asyncio
async def test_bridge_mid_stream_truncate(monkeypatch):
    chunks = [
        'event: message\ndata: {"type":"message","text":"started"}\n\n',
    ]
    fake_resp = _FakeResponse(
        200, chunks,
        raise_after_chunk=bridge_mod.httpx.RemoteProtocolError("incomplete chunked read"),
    )
    monkeypatch.setattr(
        bridge_mod.httpx, "AsyncClient",
        lambda *a, **kw: _FakeClient(fake_resp),
    )
    out: list[StreamEvent] = []
    async for evt in bridge_to_action_chat(
        message="x", multimodal_attachments=None, jwt_token="t", intent="presentation",
    ):
        out.append(evt)
    types = [e.event_type for e in out]
    # We saw the initial CHUNK, then upstream truncated → ERROR + DONE.
    assert types[0] == StreamEventType.CHUNK
    assert StreamEventType.ERROR in types
    assert types[-1] == StreamEventType.DONE
    err = next(e for e in out if e.event_type == StreamEventType.ERROR)
    assert "truncat" in err.data["message"].lower()


@pytest.mark.asyncio
async def test_bridge_heartbeat_when_upstream_silent(monkeypatch):
    # Drop heartbeat interval to a small value for the test only.
    monkeypatch.setattr(bridge_mod, "_HEARTBEAT_INTERVAL", 0.1)

    # Chunks delayed beyond heartbeat → bridge should emit STAGE pings.
    class SlowResponse(_FakeResponse):
        async def aiter_text(self):
            await asyncio.sleep(0.35)  # > 3 heartbeats worth
            yield 'event: message\ndata: {"type":"message","text":"hi"}\n\n'

    fake_resp = SlowResponse(200, [])
    monkeypatch.setattr(
        bridge_mod.httpx, "AsyncClient",
        lambda *a, **kw: _FakeClient(fake_resp),
    )

    stage_events = 0
    async for evt in bridge_to_action_chat(
        message="x", multimodal_attachments=None, jwt_token="t", intent="report",
    ):
        if evt.event_type == StreamEventType.STAGE and evt.data.get("stage") == "action_chat_thinking":
            stage_events += 1
    assert stage_events >= 1, "expected at least one heartbeat STAGE event"


@pytest.mark.asyncio
async def test_bridge_drops_thinking_and_done_from_upstream(monkeypatch):
    chunks = [
        'event: thinking\ndata: {"type":"thinking","text":"reasoning..."}\n\n',
        'event: done\ndata: {"type":"done"}\n\n',
        'event: message\ndata: {"type":"message","text":"actual answer"}\n\n',
    ]
    fake_resp = _FakeResponse(200, chunks)
    monkeypatch.setattr(
        bridge_mod.httpx, "AsyncClient",
        lambda *a, **kw: _FakeClient(fake_resp),
    )
    chunk_count = 0
    async for evt in bridge_to_action_chat(
        message="x", multimodal_attachments=None, jwt_token="t", intent="report",
    ):
        if evt.event_type == StreamEventType.CHUNK:
            chunk_count += 1
    # Only the "actual answer" should have been translated to CHUNK.
    # The mid-stream `done` from upstream is dropped, and the bridge
    # synthesizes its own terminal DONE at the end.
    assert chunk_count == 1
