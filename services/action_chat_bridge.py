"""Stream-proxy from quick chat / main chat to ``/actionchat/query/stream``.

Used when ``services.redirect_intent.classify(...)`` decides a turn should
be handled by Action Chat / Deep Research rather than the originating
chat surface. The bridge:

  1. Opens an SSE stream against action-chat-service using the user's
     **incoming JWT** (server-to-server pass-through; action-chat uses
     the same issuer + ``get_secure_user_id`` pattern).
  2. Parses each ``event:/data:`` frame as it arrives.
  3. Translates Action Chat's event vocabulary into the originating
     surface's :class:`streaming_response.StreamEvent` vocabulary —
     specifically lifting ``artifact`` events through as the new
     :data:`StreamEventType.ARTIFACT` payload so the download card
     renders inline in the user's current chat surface.
  4. Honors cooperative cancellation via ``abort_event`` (calls
     ``/actionchat/task/{session_id}/cancel`` if the client disconnects).
  5. Emits a 30s STAGE heartbeat when the action-chat side goes quiet,
     so the UI never looks frozen during long Tier-3 turns.

The bridge is intentionally TOLERANT — it never raises out into the
caller's generator; any failure becomes an ``error`` SSE event and a
clean ``done``, so the originating handler can choose to fall back to
its normal flow rather than 500.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, AsyncIterator

import httpx

from streaming_response import StreamEvent, StreamEventType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- config

def _action_chat_base_url() -> str:
    """Resolve the action-chat-service base URL.

    Priority: explicit env override → default cluster name. Set
    ``ACTION_CHAT_SERVICE_URL=http://actionchat-service:8090`` in the
    Citra-Service .env to override (e.g. local dev / staging).
    """
    return (
        os.getenv("ACTION_CHAT_SERVICE_URL")
        or os.getenv("ACTIONCHAT_SERVICE_URL")
        or "http://actionchat-service:8090"
    ).rstrip("/")


# How long we'll wait on a single read from the action-chat SSE before
# emitting a heartbeat. Action-chat itself heartbeats every 25s, so 30s
# is a safe upper bound that still keeps the user UI feeling alive.
_HEARTBEAT_INTERVAL = 30.0

# Hard ceiling on the whole bridged turn. Tier-3 action chat turns can
# legitimately take many minutes; this is a circuit-breaker, not a
# performance target.
_OVERALL_TIMEOUT = 600.0  # 10 min


# ---------------------------------------------------------------- event translation

# Action Chat → originating-surface event mapping. Action chat's
# ``message`` event becomes a CHUNK; ``artifact`` becomes the new
# structured ARTIFACT; ``tool_call`` / ``tool_result`` become a single
# TOOL_STATUS each; ``thinking`` and surface-specific events are dropped.
_DROP = object()


def _translate(action_event: dict[str, Any]) -> StreamEvent | object | None:
    """Return a StreamEvent, ``_DROP`` (silently ignore), or ``None``
    (event was not parseable).
    """
    if not isinstance(action_event, dict):
        return None
    etype = (action_event.get("type") or "").lower()

    if etype == "message":
        text = action_event.get("text") or ""
        if not text:
            return _DROP
        return StreamEvent(StreamEventType.CHUNK, {"text": text})

    if etype == "artifact":
        # Pass-through structured payload. Action chat already emits the
        # field set the UI's DownloadArtifactCard expects (kind, title,
        # filename, url, size, summary). We don't mutate it.
        payload = {
            "kind": action_event.get("kind"),
            "title": action_event.get("title"),
            "filename": action_event.get("filename"),
            "url": action_event.get("url") or action_event.get("download_url"),
            "size": action_event.get("size"),
            "summary": action_event.get("summary"),
            "source": "action_chat",
        }
        return StreamEvent(StreamEventType.ARTIFACT, payload)

    if etype == "tool_call":
        name = action_event.get("name") or action_event.get("tool") or "tool"
        return StreamEvent(StreamEventType.TOOL_STATUS, {
            "tool": name,
            "status": "running",
            "label": f"Action Chat: {name}",
        })

    if etype == "tool_result":
        name = action_event.get("name") or action_event.get("tool") or "tool"
        return StreamEvent(StreamEventType.TOOL_STATUS, {
            "tool": name,
            "status": "complete",
            "label": f"Action Chat: {name}",
        })

    if etype == "plan":
        items = action_event.get("items") or []
        return StreamEvent(StreamEventType.PLAN, {
            "items": items,
            "source": "action_chat",
        })

    if etype == "status":
        # Transient progress label — show as a stage tick.
        return StreamEvent(StreamEventType.STAGE, {
            "stage": "action_chat_progress",
            "label": action_event.get("text") or action_event.get("stage") or "Working…",
        })

    if etype == "email_sent":
        to = action_event.get("to") or "your account"
        attachments = action_event.get("attachments") or 0
        return StreamEvent(StreamEventType.CHUNK, {
            "text": (
                f"\n\n📧 Emailed to {to} "
                f"({attachments} attachment{'s' if attachments != 1 else ''}).\n"
            ),
        })

    if etype == "cancelled":
        return StreamEvent(StreamEventType.CHUNK, {
            "text": "\n\n_Request cancelled._\n",
        })

    if etype == "error":
        msg = action_event.get("message") or "action-chat error"
        return StreamEvent(StreamEventType.ERROR, {
            "message": f"Action Chat: {msg}",
            "source": "action_chat",
        })

    if etype == "done":
        # We synthesize DONE ourselves once the upstream stream closes,
        # so a mid-stream `done` from action-chat is treated as a signal
        # to stop reading rather than passed through.
        return _DROP

    # Drop UI-only / sandbox-internal events the originating surface
    # can't render meaningfully.
    if etype in ("thinking", "canvas_event", "html_block"):
        return _DROP

    # Unknown event type — log and drop. Don't pass through to avoid
    # malformed payloads tripping the UI.
    logger.debug("[BRIDGE] dropping unknown action-chat event type=%s", etype)
    return _DROP


# ---------------------------------------------------------------- SSE parsing

def _parse_sse_frames(buffer: str) -> tuple[list[dict[str, Any]], str]:
    """Split an SSE buffer into completed event dicts + the tail.

    Action Chat emits frames as ``event: <name>\\ndata: <json>\\n\\n``.
    Some frames are heartbeat comments (``: heartbeat\\n\\n``); we drop
    those. The tail (any incomplete frame) is returned for the next call.
    """
    events: list[dict[str, Any]] = []
    while True:
        sep_idx = buffer.find("\n\n")
        if sep_idx == -1:
            return events, buffer
        frame, buffer = buffer[:sep_idx], buffer[sep_idx + 2:]
        if not frame.strip() or frame.lstrip().startswith(":"):
            continue  # heartbeat / comment
        data_line = None
        for line in frame.splitlines():
            if line.startswith("data:"):
                data_line = line[5:].strip()
                break
        if not data_line:
            continue
        try:
            parsed = json.loads(data_line)
        except (ValueError, TypeError):
            logger.debug("[BRIDGE] skipping non-JSON SSE frame: %r", data_line[:80])
            continue
        if isinstance(parsed, dict):
            events.append(parsed)


# ---------------------------------------------------------------- public API

async def bridge_to_action_chat(
    *,
    message: str,
    multimodal_attachments: list[dict[str, Any]] | None,
    jwt_token: str | None,
    intent: str,
    abort_event: asyncio.Event | None = None,
) -> AsyncIterator[StreamEvent]:
    """Proxy a turn to ``/actionchat/query/stream`` and yield translated events.

    Caller responsibilities:

    - Emit the user-facing "Redirecting…" notice BEFORE calling this
      (so the user sees the notice instantly, not after the upstream
      connect). See ``redirect_intent.user_facing_notice``.
    - Convert each yielded :class:`StreamEvent` to SSE via ``.to_sse()``
      and write it to the client.
    - Decide whether to fall back to the normal flow on failure (this
      bridge always emits a terminal ERROR + DONE on failure, so a
      caller that doesn't want fallback can just pass them through).

    Args:
        message: The user's prompt — passed as ``message`` (action chat
            uses the same field name).
        multimodal_attachments: Forwarded as-is. Action chat accepts the
            same shape Quick Chat does (OCR for pasted images).
        jwt_token: Raw bearer token from the incoming request header.
            REQUIRED — action-chat-service rejects unauthenticated
            requests.
        intent: One of ``"presentation" | "report" | "deep_research"`` —
            used only for logging / telemetry tags here.
        abort_event: If set externally (e.g. when the client
            disconnects), the bridge stops reading the upstream stream
            and best-effort cancels the action-chat task.
    """
    if not jwt_token:
        yield StreamEvent(StreamEventType.ERROR, {
            "message": (
                "Cannot redirect to Deep Research: missing auth token. "
                "This usually means the request was unauthenticated."
            ),
            "source": "bridge",
        })
        yield StreamEvent(StreamEventType.DONE, {"bridged": False})
        return

    abort_event = abort_event or asyncio.Event()
    base = _action_chat_base_url()
    url = f"{base}/actionchat/query/stream"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {"message": message}
    if multimodal_attachments:
        payload["multimodal_attachments"] = multimodal_attachments

    started = time.monotonic()
    logger.info(
        "[BRIDGE] opening action-chat stream intent=%s url=%s msg_len=%d",
        intent, url, len(message),
    )

    # We can't read the response.aiter_text() and a heartbeat task
    # simultaneously without an intermediate queue, so set one up.
    queue: asyncio.Queue = asyncio.Queue()
    _SENTINEL = object()

    async def _reader():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST", url, headers=headers, json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode("utf-8", "replace")[:500]
                        await queue.put({
                            "_error": f"action-chat returned {resp.status_code}",
                            "_body": body,
                            "_status": resp.status_code,
                        })
                        return
                    buffer = ""
                    async for chunk in resp.aiter_text():
                        if abort_event.is_set():
                            break
                        if not chunk:
                            continue
                        buffer += chunk
                        events, buffer = _parse_sse_frames(buffer)
                        for evt in events:
                            await queue.put(evt)
                        if time.monotonic() - started > _OVERALL_TIMEOUT:
                            await queue.put({
                                "_error": f"action-chat exceeded {_OVERALL_TIMEOUT:.0f}s budget",
                                "_status": 504,
                            })
                            break
        except httpx.RemoteProtocolError as e:
            await queue.put({
                "_error": f"action-chat stream truncated: {e}",
                "_status": 502,
            })
        except (httpx.ConnectError, httpx.ReadError, httpx.WriteError) as e:
            await queue.put({
                "_error": f"action-chat unreachable: {e}",
                "_status": 503,
            })
        except Exception as e:  # noqa: BLE001
            logger.exception("[BRIDGE] unexpected reader failure")
            await queue.put({
                "_error": f"bridge error: {e}",
                "_status": 500,
            })
        finally:
            await queue.put(_SENTINEL)

    reader_task = asyncio.create_task(_reader())

    last_event_at = time.monotonic()
    fatal_error: dict[str, Any] | None = None
    saw_any_event = False

    try:
        while True:
            try:
                evt = await asyncio.wait_for(
                    queue.get(), timeout=_HEARTBEAT_INTERVAL,
                )
            except asyncio.TimeoutError:
                # No event in 30s — emit a heartbeat STAGE so the UI
                # knows we're still alive. Action chat may legitimately
                # be deep in a long tool call.
                yield StreamEvent(StreamEventType.STAGE, {
                    "stage": "action_chat_thinking",
                    "label": "Deep Research is working…",
                    "detail": f"{int(time.monotonic() - last_event_at)}s since last update",
                })
                continue

            if evt is _SENTINEL:
                break

            # Internal error signal from the reader
            if isinstance(evt, dict) and "_error" in evt:
                fatal_error = evt
                break

            saw_any_event = True
            last_event_at = time.monotonic()
            translated = _translate(evt)
            if translated is _DROP or translated is None:
                continue
            yield translated  # type: ignore[misc]

    finally:
        # Cooperative cancel of upstream if the client went away.
        if not reader_task.done():
            abort_event.set()
            reader_task.cancel()
            try:
                await asyncio.wait_for(reader_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    if fatal_error:
        yield StreamEvent(StreamEventType.ERROR, {
            "message": fatal_error.get("_error") or "bridge failed",
            "status": fatal_error.get("_status"),
            "source": "bridge",
            "saw_any_event": saw_any_event,
        })

    # Always terminate cleanly with DONE so the originating handler
    # can rely on a single terminal signal.
    elapsed = time.monotonic() - started
    yield StreamEvent(StreamEventType.DONE, {
        "bridged": True,
        "intent": intent,
        "elapsed_seconds": round(elapsed, 2),
        "events_seen": saw_any_event,
    })
    logger.info(
        "[BRIDGE] closed action-chat stream intent=%s elapsed=%.1fs events_seen=%s",
        intent, elapsed, saw_any_event,
    )
