import uuid

import structlog
from fastapi import WebSocket

logger = structlog.get_logger(__name__)


class ConnectionManager:
    """
    In-process registry of active WebSocket connections.

    Internal structure: {channel_id: {user_id: WebSocket}}
    """

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, dict[uuid.UUID, WebSocket]] = {}

    def connect(
        self,
        user_id: uuid.UUID,
        channel_id: uuid.UUID,
        ws: WebSocket,
    ) -> None:
        if channel_id not in self._connections:
            self._connections[channel_id] = {}
        self._connections[channel_id][user_id] = ws
        logger.info(
            "ws_connected",
            user_id=str(user_id),
            channel_id=str(channel_id),
        )

    def disconnect(self, user_id: uuid.UUID, channel_id: uuid.UUID) -> None:
        channel_conns = self._connections.get(channel_id)
        if channel_conns is not None:
            channel_conns.pop(user_id, None)
            if not channel_conns:
                del self._connections[channel_id]
        logger.info(
            "ws_disconnected",
            user_id=str(user_id),
            channel_id=str(channel_id),
        )

    async def broadcast_to_channel(
        self,
        channel_id: uuid.UUID,
        payload: dict,  # type: ignore[type-arg]
        exclude_user_id: uuid.UUID | None = None,
    ) -> None:
        channel_conns = self._connections.get(channel_id, {})
        for uid, ws in list(channel_conns.items()):
            if exclude_user_id is not None and uid == exclude_user_id:
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                logger.warning(
                    "ws_send_failed",
                    user_id=str(uid),
                    channel_id=str(channel_id),
                )


# Module-level singleton — import this everywhere, never instantiate per-request.
manager = ConnectionManager()
