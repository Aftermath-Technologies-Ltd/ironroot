# Author: Bradley R. Kinnard
"""websocket connection management."""

from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """manages active websocket connections."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """accepts and stores a new connection."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """removes a connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """sends message to all connected clients."""
        for connection in self.active_connections:
            await connection.send_json(message)


# singleton manager
manager = ConnectionManager()
