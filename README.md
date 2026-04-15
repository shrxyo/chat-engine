# chat-engine

A Discord-like chat app built phase by phase using FastAPI and WebSockets.

## Setup

```bash
pip install -r requirements.txt
```

## Running the server

```bash
uvicorn server:app --reload
```

The server starts at `http://localhost:8000`.

## Testing the WebSocket (Phase 1)

Open your browser's DevTools console (`F12`) and paste:

```js
const ws = new WebSocket("ws://localhost:8000/ws");
ws.onmessage = (e) => console.log(e.data);
ws.onopen = () => ws.send("hello!");
```

You should see `Echo: hello!` printed in the console.

Alternatively, use [websocat](https://github.com/vi/websocat):

```bash
websocat ws://localhost:8000/ws
```

## Phases

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Echo WebSocket server | ✅ Done |
| 2 | Two-way broadcast chat | ⬜ |
| 3 | Usernames and JSON messages | ⬜ |
| 4 | Discord-like UI | ⬜ |
| 5 | Channels | ⬜ |
