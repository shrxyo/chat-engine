import json
import uuid
from functools import lru_cache

import redis.asyncio as aioredis
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)


@lru_cache
def get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    return aioredis.from_url(get_settings().REDIS_URL, decode_responses=True)


async def publish(channel_id: uuid.UUID, payload: dict) -> None:  # type: ignore[type-arg]
    """
    Publish a payload to the Redis channel for *channel_id*.

    Single-instance: the pub/sub plumbing is correct for Epic 6 fan-out but
    currently no subscriber is listening — the in-process ConnectionManager
    handles delivery directly.
    """
    try:
        redis = get_redis()
        await redis.publish(f"channel:{channel_id}", json.dumps(payload, default=str))
    except Exception as exc:
        logger.warning(
            "pubsub_publish_failed",
            channel_id=str(channel_id),
            error=str(exc),
        )
