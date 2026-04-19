# chat-engine

A Discord-like chat app built phase by phase using FastAPI and WebSockets.

## Setup

```bash
pip install -r requirements.txt
```

## Running the server

```bash
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

The server starts at `http://localhost:8000`.

## Testing the WebSocket (Phase 1)

Open your browser's DevTools console (`F12`) and paste:

```js
const ws = new WebSocket("ws://localhost:8000/ws");
ws.onmessage = (e) => console.log(e.data);
ws.onopen = () =>
  ws.send(JSON.stringify({ type: "chat", username: "Dev", text: "hello" }));
```

Outbound chat lines are JSON: `{"type":"chat","username":"…","text":"…"}`. On connect the server sends a history batch: `{"type":"history","messages":[{username,text},…]}` (up to 200 lines; cleared on server restart).

Alternatively, use [websocat](https://github.com/vi/websocat):

```bash
echo '{"type":"chat","username":"Dev","text":"hello"}' | websocat ws://localhost:8000/ws
```

## Phases

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Echo WebSocket server | ✅ Done |
| 2 | Two-way broadcast chat | ✅ Done |
| 3 | Usernames and JSON messages | ✅ Done |
| 4 | Discord-like UI | ⬜ |
| 5 | Channels | ⬜ |
