import uuid
from datetime import UTC, datetime
from typing import Any

import anyio
import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import StatusCode
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.metrics import MESSAGES_BROADCAST_TOTAL, now_ms
from app.models.membership import ChannelMembership
from app.models.message import Message
from app.models.reaction import MessageReaction
from app.models.user import User
from app.schemas.messages import MessageResponse
from app.schemas.ws import (
    MessageDeletePayload,
    MessageEditPayload,
    MessageNewBroadcastPayload,
    MessageNewPayload,
    MessageReactionPayload,
    PresenceSnapshotPayload,
    WSMessageType,
)
from app.services.connection_manager import manager
from app.services.presence import PresenceConnection, presence_event
from app.services.presence import connection as presence_connection
from app.services.pubsub import publish

logger = structlog.get_logger(__name__)
_tracer = trace.get_tracer(__name__)

router = APIRouter(tags=["websocket"])

_CLEANUP_TIMEOUT = 2.0


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


async def _get_user_from_token(
    token: str,
    session: AsyncSession,
) -> User | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            return None
        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError):
        return None
    return await session.get(User, user_id)


async def _authorize(token: str | None, channel_id: uuid.UUID) -> User | None:
    """The token's user if they are a member of *channel_id*, else None."""
    if token is None:
        return None
    async with AsyncSessionLocal() as session:
        user = await _get_user_from_token(token, session)
        if user is None:
            return None
        membership = await session.get(ChannelMembership, (user.id, channel_id))
        return user if membership is not None else None


# ---------------------------------------------------------------------------
# Main WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws/{channel_id}")
async def websocket_endpoint(
    channel_id: uuid.UUID,
    ws: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    user: User | None = None
    presence: PresenceConnection | None = None
    log: Any = logger.bind(channel_id=str(channel_id))
    try:
        # S7.2: the handshake is its own trace. The socket's lifetime is not
        # traced (see app/telemetry.py), so this span ends once the socket is live.
        with _tracer.start_as_current_span(
            "ws.connect",
            context=Context(),
            attributes={"chat.channel_id": str(channel_id)},
        ) as span:
            # --- Auth & membership check (before accepting) ---
            user = await _authorize(token, channel_id)
            if user is None:
                span.set_status(StatusCode.ERROR, "unauthorized")
                await ws.close(code=4001)
                return
            span.set_attribute("enduser.id", str(user.id))
            log = log.bind(user_id=str(user.id))

            # --- Accept & register connection ---
            # Inside the try: if anything below fails, `finally` unregisters.
            await ws.accept()
            await manager.connect(user.id, channel_id, ws)
            presence = presence_connection(channel_id, user.id)
            await _join(ws, user, channel_id, presence, log)

        # --- Receive loop ---
        while True:
            try:
                data: Any = await ws.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception as exc:
                log.error("ws_receive_error", error=str(exc))
                break

            # S4.2: any frame, including ping, keeps the user online.
            if await presence.refresh():
                await _announce_join(user, channel_id, log)

            msg_type_str: Any = data.get("type") if isinstance(data, dict) else None
            payload_data: dict[str, Any] = (
                data.get("payload", {}) if isinstance(data, dict) else {}
            )

            try:
                msg_type = WSMessageType(msg_type_str)
            except ValueError:
                await ws.send_json(
                    {
                        "type": WSMessageType.error,
                        "payload": {"message": f"Unknown event type: {msg_type_str!r}"},
                    }
                )
                log.warning(
                    "ws_unknown_event_type",
                    event_type=msg_type_str,
                )
                continue

            log.info("ws_event_received", event_type=msg_type)

            try:
                await _handle_event(ws, user, channel_id, msg_type, payload_data)
            except Exception as exc:
                log.error("ws_event_handler_error", event_type=msg_type, error=str(exc))
                try:
                    await ws.send_json(
                        {
                            "type": WSMessageType.error,
                            "payload": {"message": "Internal server error"},
                        }
                    )
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    finally:
        # Shielded: if the handler is being cancelled (server shutdown), the
        # leave must still go out or the user shows online until the TTL.
        # Bounded so a stuck Redis can't hold up shutdown.
        with anyio.move_on_after(_CLEANUP_TIMEOUT, shield=True):
            if user is not None:
                await manager.disconnect(user.id, channel_id, ws)
            if user is not None and presence is not None and await presence.leave():
                await publish(
                    channel_id,
                    presence_event(WSMessageType.presence_leave, channel_id, user.id),
                )
                log.info("ws_presence_leave", event_type=WSMessageType.presence_leave)


async def _join(
    ws: WebSocket,
    user: User,
    channel_id: uuid.UUID,
    presence: PresenceConnection,
    log: Any,
) -> None:
    """Mark the socket online, announce it if the user was offline, then
    send the new socket who is online (S4.2)."""
    if await presence.join():
        await _announce_join(user, channel_id, log)
    snapshot = PresenceSnapshotPayload(
        channel_id=channel_id, online_user_ids=await presence.online()
    )
    await ws.send_json(
        {
            "type": WSMessageType.presence_snapshot,
            "payload": snapshot.model_dump(mode="json"),
        }
    )


async def _announce_join(user: User, channel_id: uuid.UUID, log: Any) -> None:
    await publish(
        channel_id,
        presence_event(WSMessageType.presence_join, channel_id, user.id),
        exclude_user_id=user.id,
    )
    log.info("ws_presence_join", event_type=WSMessageType.presence_join)


# ---------------------------------------------------------------------------
# Per-event handlers
# ---------------------------------------------------------------------------


async def _handle_event(
    ws: WebSocket,
    user: User,
    channel_id: uuid.UUID,
    msg_type: WSMessageType,
    payload_data: dict[str, Any],
) -> None:
    log = logger.bind(
        user_id=str(user.id), channel_id=str(channel_id), event_type=msg_type
    )

    if msg_type == WSMessageType.message_new:
        await _handle_message_new(ws, user, channel_id, payload_data, log)

    elif msg_type == WSMessageType.message_edit:
        await _handle_message_edit(ws, user, channel_id, payload_data, log)

    elif msg_type == WSMessageType.message_delete:
        await _handle_message_delete(ws, user, channel_id, payload_data, log)

    elif msg_type == WSMessageType.message_reaction:
        await _handle_message_reaction(ws, user, channel_id, payload_data, log)

    elif msg_type in (WSMessageType.typing_start, WSMessageType.typing_stop):
        await _handle_typing(user, channel_id, msg_type, log)

    # ping: nothing to do; the receive loop already refreshed presence.


async def _handle_message_new(
    ws: WebSocket,
    user: User,
    channel_id: uuid.UUID,
    payload_data: dict[str, Any],
    log: Any,
) -> None:
    # S7.2: one trace per message. Delivery on every replica joins it through
    # the trace context in the pub/sub envelope.
    with _tracer.start_as_current_span(
        "ws.message.new",
        context=Context(),
        attributes={"chat.channel_id": str(channel_id), "enduser.id": str(user.id)},
    ) as span:
        server_ts = now_ms()
        try:
            payload = MessageNewPayload(**payload_data)
        except ValidationError as exc:
            span.set_status(StatusCode.ERROR, "validation error")
            await ws.send_json(
                {"type": WSMessageType.error, "payload": {"message": str(exc)}}
            )
            log.warning("ws_validation_error")
            return

        with _tracer.start_as_current_span("db.persist"):
            async with AsyncSessionLocal() as session:
                message = Message(
                    channel_id=channel_id,
                    user_id=user.id,
                    content=payload.content,
                    reply_to_id=payload.reply_to_id,
                )
                session.add(message)
                await session.commit()
                await session.refresh(message)
        span.set_attribute("chat.message_id", str(message.id))

        msg_response = MessageNewBroadcastPayload.model_validate(
            {
                **MessageResponse.model_validate(message).model_dump(),
                "server_ts": server_ts,
            }
        )
        broadcast: dict[str, Any] = {
            "type": WSMessageType.message_new,
            "payload": msg_response.model_dump(mode="json"),
        }
        await publish(channel_id, broadcast)
        MESSAGES_BROADCAST_TOTAL.inc()

    log.info("ws_message_new", message_id=str(message.id))
    logger.info("embedding job enqueued", message_id=str(message.id))


async def _handle_message_edit(
    ws: WebSocket,
    user: User,
    channel_id: uuid.UUID,
    payload_data: dict[str, Any],
    log: Any,
) -> None:
    try:
        payload = MessageEditPayload(**payload_data)
    except ValidationError as exc:
        await ws.send_json(
            {"type": WSMessageType.error, "payload": {"message": str(exc)}}
        )
        log.warning("ws_validation_error")
        return

    async with AsyncSessionLocal() as session:
        message = await session.get(Message, payload.message_id)
        if message is None or message.deleted_at is not None:
            await ws.send_json(
                {
                    "type": WSMessageType.error,
                    "payload": {"message": "Message not found"},
                }
            )
            return

        if message.user_id != user.id:
            await ws.send_json(
                {
                    "type": WSMessageType.error,
                    "payload": {"message": "You can only edit your own messages"},
                }
            )
            return

        message.content = payload.content
        message.edited_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(message)
        await session.commit()
        await session.refresh(message)

    msg_response = MessageResponse.model_validate(message)
    broadcast: dict[str, Any] = {
        "type": WSMessageType.message_edit,
        "payload": msg_response.model_dump(mode="json"),
    }
    await publish(channel_id, broadcast)
    log.info("ws_message_edit", message_id=str(payload.message_id))


async def _handle_message_delete(
    ws: WebSocket,
    user: User,
    channel_id: uuid.UUID,
    payload_data: dict[str, Any],
    log: Any,
) -> None:
    try:
        payload = MessageDeletePayload(**payload_data)
    except ValidationError as exc:
        await ws.send_json(
            {"type": WSMessageType.error, "payload": {"message": str(exc)}}
        )
        log.warning("ws_validation_error")
        return

    async with AsyncSessionLocal() as session:
        message = await session.get(Message, payload.message_id)
        if message is None or message.deleted_at is not None:
            await ws.send_json(
                {
                    "type": WSMessageType.error,
                    "payload": {"message": "Message not found"},
                }
            )
            return

        if message.user_id != user.id:
            await ws.send_json(
                {
                    "type": WSMessageType.error,
                    "payload": {"message": "You can only delete your own messages"},
                }
            )
            return

        message.deleted_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(message)
        await session.commit()

    broadcast: dict[str, Any] = {
        "type": WSMessageType.message_delete,
        "payload": {"message_id": str(payload.message_id)},
    }
    await publish(channel_id, broadcast)
    log.info("ws_message_delete", message_id=str(payload.message_id))


async def _handle_message_reaction(
    ws: WebSocket,
    user: User,
    channel_id: uuid.UUID,
    payload_data: dict[str, Any],
    log: Any,
) -> None:
    try:
        payload = MessageReactionPayload(**payload_data)
    except ValidationError as exc:
        await ws.send_json(
            {"type": WSMessageType.error, "payload": {"message": str(exc)}}
        )
        log.warning("ws_validation_error")
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MessageReaction).where(
                MessageReaction.message_id == payload.message_id,
                MessageReaction.user_id == user.id,
                MessageReaction.emoji == payload.emoji,
            )
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            await session.delete(existing)
        else:
            reaction = MessageReaction(
                message_id=payload.message_id,
                user_id=user.id,
                emoji=payload.emoji,
            )
            session.add(reaction)

        await session.commit()

        result = await session.execute(
            select(MessageReaction).where(
                MessageReaction.message_id == payload.message_id
            )
        )
        reactions = result.scalars().all()

    broadcast: dict[str, Any] = {
        "type": WSMessageType.message_reaction,
        "payload": {
            "message_id": str(payload.message_id),
            "reactions": [
                {"id": str(r.id), "user_id": str(r.user_id), "emoji": r.emoji}
                for r in reactions
            ],
        },
    }
    await publish(channel_id, broadcast)
    log.info("ws_message_reaction", message_id=str(payload.message_id))


async def _handle_typing(
    user: User,
    channel_id: uuid.UUID,
    msg_type: WSMessageType,
    log: Any,
) -> None:
    broadcast: dict[str, Any] = {
        "type": msg_type,
        "payload": {"user_id": str(user.id), "channel_id": str(channel_id)},
    }
    await publish(channel_id, broadcast, exclude_user_id=user.id)
    log.info("ws_typing")
