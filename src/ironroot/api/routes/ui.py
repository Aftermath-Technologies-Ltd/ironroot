# Author: Bradley R. Kinnard
"""ui backend endpoints including websocket events."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/events/stream")
async def event_stream(websocket: WebSocket) -> None:
    """pushes run events and gate updates in real time."""
    await websocket.accept()
    try:
        # todo: subscribe to trace events in phase 7
        while True:
            data = await websocket.receive_text()
            # echo for now, will push real events later
            await websocket.send_json({"type": "ack", "data": data})
    except WebSocketDisconnect:
        pass
