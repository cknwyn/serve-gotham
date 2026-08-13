from typing import List
from fastapi import WebSocket
import logging

logger = logging.getLogger("gotham_dispatch.websocket")


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket, initial_incidents: list[dict]):
        await websocket.accept()
        self.active_connections.append(websocket)
        # Send initial snapshot to newly connected dispatcher
        snapshot_payload = {
            "event": "INITIAL_SNAPSHOT",
            "incidents": initial_incidents
        }
        await websocket.send_json(snapshot_payload)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception as e:
                logger.warning(f"Error broadcasting to WebSocket: {e}")
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()
