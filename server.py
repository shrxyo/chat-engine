import json
from collections import deque

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

MAX_HISTORY = 200
# Each entry: {"username": str, "text": str} (chat line body, no envelope on stored items)
message_history: deque[dict] = deque(maxlen=MAX_HISTORY)


def history_envelope_json() -> str:
    return json.dumps(
        {"type": "history", "messages": list(message_history)},
        ensure_ascii=False,
    )


def chat_envelope_json(username: str, text: str) -> str:
    return json.dumps(
        {"type": "chat", "username": username, "text": text},
        ensure_ascii=False,
    )


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"Client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"Client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


manager = ConnectionManager()


@app.get("/")
async def serve_index():
    from fastapi.responses import FileResponse

    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    print("WS route hit")
    print("NEW WS OBJECT:", id(websocket))
    await manager.connect(websocket)
    await websocket.send_text(history_envelope_json())
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                print(f"Invalid JSON: {raw!r}")
                continue
            if not isinstance(data, dict):
                continue
            if data.get("type") != "chat":
                continue
            username = data.get("username")
            text = data.get("text")
            if not isinstance(username, str) or not isinstance(text, str):
                continue
            username = username.strip()
            text = text.strip()
            if not username or not text:
                continue
            line = {"username": username, "text": text}
            message_history.append(line)
            payload = chat_envelope_json(username, text)
            print(f"Received: {payload}")
            await manager.broadcast(payload)
    except WebSocketDisconnect:
        manager.disconnect(websocket)