import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.membership import ChannelMembership
from app.models.message import Message
from app.models.reaction import MessageReaction
from app.models.user import User
from app.schemas.messages import MessageResponse
from app.schemas.ws import (
    MessageDeletePayload,
    MessageEditPayload,
    MessageNewPayload,
    MessageReactionPayload,
    WSMessageType,
)
from app.services.connection_manager import manager
from app.services.pubsub import publish

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["websocket"])


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


# ---------------------------------------------------------------------------
# Main WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws/{channel_id}")
async def websocket_endpoint(
    channel_id: uuid.UUID,
    ws: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    # --- Auth & membership check (before accepting) ---
    if token is None:
        await ws.close(code=4001)
        return

    async with AsyncSessionLocal() as session:
        user = await _get_user_from_token(token, session)
        if user is None:
            await ws.close(code=4001)
            return

        membership = await session.get(ChannelMembership, (user.id, channel_id))
        if membership is None:
            await ws.close(code=4001)
            return

    # --- Accept & register connection ---
    await ws.accept()
    manager.connect(user.id, channel_id, ws)

    log = logger.bind(user_id=str(user.id), channel_id=str(channel_id))

    join_payload: dict[str, Any] = {
        "type": WSMessageType.presence_join,
        "payload": {"user_id": str(user.id), "channel_id": str(channel_id)},
    }
    await publish(channel_id, join_payload)
    await manager.broadcast_to_channel(
        channel_id, join_payload, exclude_user_id=user.id
    )
    log.info("ws_presence_join", event_type=WSMessageType.presence_join)

    # --- Receive loop ---
    try:
        while True:
            try:
                data: Any = await ws.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception as exc:
                log.error("ws_receive_error", error=str(exc))
                break

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
        manager.disconnect(user.id, channel_id)
        leave_payload: dict[str, Any] = {
            "type": WSMessageType.presence_leave,
            "payload": {"user_id": str(user.id), "channel_id": str(channel_id)},
        }
        await publish(channel_id, leave_payload)
        await manager.broadcast_to_channel(channel_id, leave_payload)
        log.info("ws_presence_leave", event_type=WSMessageType.presence_leave)


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


async def _handle_message_new(
    ws: WebSocket,
    user: User,
    channel_id: uuid.UUID,
    payload_data: dict[str, Any],
    log: Any,
) -> None:
    try:
        payload = MessageNewPayload(**payload_data)
    except ValidationError as exc:
        await ws.send_json(
            {"type": WSMessageType.error, "payload": {"message": str(exc)}}
        )
        log.warning("ws_validation_error")
        return

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

    msg_response = MessageResponse.model_validate(message)
    broadcast: dict[str, Any] = {
        "type": WSMessageType.message_new,
        "payload": msg_response.model_dump(mode="json"),
    }
    await publish(channel_id, broadcast)
    await manager.broadcast_to_channel(channel_id, broadcast)

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
    await manager.broadcast_to_channel(channel_id, broadcast)
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
    await manager.broadcast_to_channel(channel_id, broadcast)
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
    await manager.broadcast_to_channel(channel_id, broadcast)
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
    await publish(channel_id, broadcast)
    await manager.broadcast_to_channel(channel_id, broadcast, exclude_user_id=user.id)
    log.info("ws_typing")
