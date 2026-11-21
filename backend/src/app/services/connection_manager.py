import asyncio
import contextlib
import uuid
from typing import Any, Protocol

import structlog
from fastapi import WebSocket

logger = structlog.get_logger(__name__)

# 1013 "Try Again Later": tells the client to reconnect (and gap-fill).
_SLOW_CONSUMER_CLOSE_CODE = 1013
_CLOSE_TIMEOUT = 1.0


class ChannelSubscriber(Protocol):
    async def subscribe(self, channel_id: uuid.UUID) -> None: ...

    async def unsubscribe(self, channel_id: uuid.UUID) -> None: ...


class ConnectionManager:
    """
    Registry of WebSocket connections held by *this* process.

    Internal structure: {channel_id: {user_id: WebSocket}}

    Cross-instance delivery (S6.1): the attached subscriber (the RedisBus) is
    told when a channel gets its first local socket and when its last one
    leaves, so each instance only receives events for channels it serves.
    Events arriving from Redis are delivered with ``broadcast_to_channel``.
    """

    def __init__(self, *, send_timeout: float = 2.0) -> None:
        self._connections: dict[uuid.UUID, dict[uuid.UUID, WebSocket]] = {}
        self._subscriber: ChannelSubscriber | None = None
        self._send_timeout = send_timeout

    def attach_subscriber(self, subscriber: ChannelSubscriber | None) -> None:
        self._subscriber = subscriber

    def local_connection_count(self, channel_id: uuid.UUID) -> int:
        return len(self._connections.get(channel_id, {}))

    async def connect(
        self,
        user_id: uuid.UUID,
        channel_id: uuid.UUID,
        ws: WebSocket,
    ) -> None:
        channel_conns = self._connections.setdefault(channel_id, {})
        first_local = not channel_conns
        channel_conns[user_id] = ws
        logger.info("ws_connected", user_id=str(user_id), channel_id=str(channel_id))
        if first_local and self._subscriber is not None:
            await self._subscriber.subscribe(channel_id)

    async def disconnect(
        self,
        user_id: uuid.UUID,
        channel_id: uuid.UUID,
        ws: WebSocket | None = None,
    ) -> None:
        """
        Remove a connection. Idempotent.

        When *ws* is given, only that exact socket is removed: if the user has
        since reconnected (new tab, reconnect), the newer socket is kept.
        """
        channel_conns = self._connections.get(channel_id)
        if channel_conns is None:
            return
        current = channel_conns.get(user_id)
        if current is None or (ws is not None and current is not ws):
            return

        del channel_conns[user_id]
        logger.info("ws_disconnected", user_id=str(user_id), channel_id=str(channel_id))
        if not channel_conns:
            del self._connections[channel_id]
            if self._subscriber is not None:
                await self._subscriber.unsubscribe(channel_id)

    async def broadcast_to_channel(
        self,
        channel_id: uuid.UUID,
        payload: dict[str, Any],
        exclude_user_id: uuid.UUID | None = None,
    ) -> None:
        """Send to every local socket in the channel, in parallel."""
        targets = [
            (uid, ws)
            for uid, ws in self._connections.get(channel_id, {}).items()
            if uid != exclude_user_id
        ]
        if not targets:
            return
        await asyncio.gather(
            *(self._send(uid, channel_id, ws, payload) for uid, ws in targets)
        )

    async def _send(
        self,
        user_id: uuid.UUID,
        channel_id: uuid.UUID,
        ws: WebSocket,
        payload: dict[str, Any],
    ) -> None:
        try:
            await asyncio.wait_for(ws.send_json(payload), self._send_timeout)
        except Exception as exc:
            # A dead or stalled client must not hold up the rest of the
            # channel: drop it and let it reconnect.
            logger.warning(
                "ws_send_failed_evicting",
                user_id=str(user_id),
                channel_id=str(channel_id),
                error=type(exc).__name__,
            )
            await self.disconnect(user_id, channel_id, ws)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    ws.close(code=_SLOW_CONSUMER_CLOSE_CODE), _CLOSE_TIMEOUT
                )


# Module-level singleton — import this everywhere, never instantiate per-request.
manager = ConnectionManager()
