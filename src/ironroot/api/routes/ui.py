# Author: Bradley R. Kinnard
"""UI backend endpoints including the live belief-event WebSocket (Phase 3.3).

The previous Phase-0 implementation echoed whatever the client sent.
That was misleading: there is no echo channel, and the route looked
like a real feed.

The Phase 3 implementation subscribes to the
:data:`ironroot.events.bus.BELIEF_EVENT_CHANNEL` Redis pubsub channel
(or the in-memory bus, when one is configured for tests) and forwards
each event as a JSON text frame. Client-to-server messages are read
but ignored, except for ``{"type": "ping"}`` which we reply to so
load balancers and the UI can use a simple liveness check.

If the bus connection drops mid-stream the WebSocket closes; the
client is expected to reconnect.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ironroot.events import get_belief_event_bus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/events/stream")
async def event_stream(websocket: WebSocket) -> None:
    """Forwards belief-append events to the connected client.

    The route does not interpret the chain — it only relays JSON
    payloads from the event bus. Clients use the ``belief_id`` and
    ``seq`` in each event to refetch the corresponding belief via
    ``/api/v1/beliefs/{id}`` or to render the chain incrementally.
    """
    await websocket.accept()
    bus = get_belief_event_bus()

    async def _reader() -> None:
        """Drains client → server frames; ignores anything that isn't a ping.

        The default WebSocket implementation in starlette requires
        us to actively read from the socket to notice client
        disconnects. Without this task, a CLOSE frame from the
        client would be invisible until the next server write
        failed.
        """
        try:
            while True:
                message = await websocket.receive_json()
                if isinstance(message, dict) and message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            return
        except Exception:
            return

    reader_task = asyncio.create_task(_reader())
    try:
        async with bus.subscribe() as events:
            async for event in events:
                if reader_task.done():
                    break
                try:
                    await websocket.send_json(event)
                except (WebSocketDisconnect, RuntimeError):
                    break
    except Exception as exc:
        logger.warning("event stream terminated: %s", exc)
    finally:
        reader_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await reader_task
        with contextlib.suppress(Exception):
            await websocket.close()


__all__ = ["router"]


def _legacy_echo(payload: Any) -> Any:  # pragma: no cover - kept for docs only
    """Removed in Phase 3.3.

    The previous implementation echoed client messages. There is no
    longer any such handler. Documented here so a grep for the
    previous behaviour points at the replacement.
    """
    raise NotImplementedError("echo websocket was removed in Phase 3.3")
