"""In-memory WebSocket fan-out for the agent message bus, keyed by workspace."""
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, workspace_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._rooms[workspace_id].add(ws)

    def disconnect(self, workspace_id: str, ws: WebSocket) -> None:
        self._rooms.get(workspace_id, set()).discard(ws)

    async def broadcast(self, workspace_id: str, message: dict) -> None:
        dead = []
        for ws in list(self._rooms.get(workspace_id, ())):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(workspace_id, ws)


manager = ConnectionManager()
