from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        # Maps username to WebSocket
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, username: str):
        await websocket.accept()
        # Close existing connection if user logs in from another tab
        if username in self.active_connections:
            try:
                await self.active_connections[username].close()
            except Exception:
                pass
        self.active_connections[username] = websocket

    def disconnect(self, username: str):
        if username in self.active_connections:
            del self.active_connections[username]

    async def send_personal_message(self, message: dict, username: str):
        if username in self.active_connections:
            websocket = self.active_connections[username]
            try:
                await websocket.send_json(message)
            except Exception:
                pass

    async def broadcast(self, message: dict, exclude_user: str = None):
        for username, websocket in self.active_connections.items():
            if exclude_user and username == exclude_user:
                continue
            try:
                await websocket.send_json(message)
            except Exception:
                pass
