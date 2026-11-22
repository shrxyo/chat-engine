"""
Presence via Redis (S4.2).

State lives in Redis, so every replica sees the same online set:

- ``{prefix}:channel:{channel_id}``: sorted set, one member per open socket,
  ``"{user_id}:{conn_id}"``, scored by its expiry (epoch ms). A user is online
  in a channel while any of their members is unexpired, so two tabs on two
  replicas count once, and the user goes offline only when the last closes.
- ``{prefix}:{user_id}``: string with a TTL, refreshed with the sorted set.
  "Online anywhere", for lookups outside a channel.
- ``{prefix}:channels``: set of channel ids with members, for the sweeper.

Sockets refresh their entry on any inbound frame (clients ping every 20s,
throttled server-side to once per ttl/3). If a socket stops refreshing, or
its replica dies, the entry expires and a sweeper on any replica removes it
and reports the user offline, so ``presence.leave`` still goes out.

Each operation is a Lua script using Redis ``TIME``, so it is atomic and
immune to clock skew between replicas: of N replicas racing to sweep the same
entry, exactly one reports it. Keys for one channel are not co-located, so
this assumes a single Redis (not Cluster).
"""

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, cast

import redis.asyncio as aioredis
import structlog
from redis.exceptions import RedisError

from app.schemas.ws import WSMessageType

logger = structlog.get_logger(__name__)

OnOffline = Callable[[uuid.UUID, uuid.UUID], Awaitable[None]]

_REDIS_ERRORS = (RedisError, OSError)

# Members are "{user_id}:{conn_id}"; UUIDs contain no ':'.
_LUA_HELPERS = """
local function now_ms()
  local t = redis.call('TIME')
  return tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
end
local function user_of(member)
  return string.match(member, '^([^:]+):')
end
local function user_is_live(key, user, now)
  for _, m in ipairs(redis.call('ZRANGEBYSCORE', key, '(' .. now, '+inf')) do
    if user_of(m) == user then return true end
  end
  return false
end
local function drop_index_if_empty(key, index, channel)
  if redis.call('ZCARD', key) == 0 then redis.call('SREM', index, channel) end
end
"""

# KEYS: channel zset, channel index, user key
# ARGV: member, user_id, ttl_ms, channel_id
# Returns 1 if the user was offline in the channel before this touch.
_TOUCH = (
    _LUA_HELPERS
    + """
local now = now_ms()
local ttl = tonumber(ARGV[3])
local was_live = user_is_live(KEYS[1], ARGV[2], now)
redis.call('ZADD', KEYS[1], now + ttl, ARGV[1])
-- Outlives every member by a wide margin, so sweepers see expiries first;
-- only reclaims the key if every replica is gone.
redis.call('PEXPIRE', KEYS[1], ttl * 4)
redis.call('SADD', KEYS[2], ARGV[4])
redis.call('SET', KEYS[3], '1', 'PX', ttl)
if was_live then return 0 end
return 1
"""
)

# KEYS: channel zset, channel index
# ARGV: member, user_id, channel_id
# Returns 1 if this removal took the user offline in the channel.
_LEAVE = (
    _LUA_HELPERS
    + """
if redis.call('ZREM', KEYS[1], ARGV[1]) == 0 then
  return 0  -- never joined, or already swept (the sweep reported it)
end
local now = now_ms()
local result = 1
if user_is_live(KEYS[1], ARGV[2], now) then
  result = 0
else
  -- Drop the user's expired leftovers so a later sweep can't leave again.
  for _, m in ipairs(redis.call('ZRANGE', KEYS[1], 0, -1)) do
    if user_of(m) == ARGV[2] then redis.call('ZREM', KEYS[1], m) end
  end
end
drop_index_if_empty(KEYS[1], KEYS[2], ARGV[3])
return result
"""
)

# KEYS: channel zset, channel index
# ARGV: channel_id
# Returns the user ids that went offline.
_SWEEP = (
    _LUA_HELPERS
    + """
local now = now_ms()
local expired = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', now)
local gone = {}
if #expired > 0 then
  redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
  local live = {}
  for _, m in ipairs(redis.call('ZRANGE', KEYS[1], 0, -1)) do
    live[user_of(m)] = true
  end
  local seen = {}
  for _, m in ipairs(expired) do
    local u = user_of(m)
    if not live[u] and not seen[u] then
      seen[u] = true
      table.insert(gone, u)
    end
  end
end
drop_index_if_empty(KEYS[1], KEYS[2], ARGV[1])
return gone
"""
)

# KEYS: channel zset. Returns distinct user ids with an unexpired member.
_ONLINE = (
    _LUA_HELPERS
    + """
local seen, users = {}, {}
for _, m in ipairs(redis.call('ZRANGEBYSCORE', KEYS[1], '(' .. now_ms(), '+inf')) do
  local u = user_of(m)
  if not seen[u] then
    seen[u] = true
    table.insert(users, u)
  end
end
return users
"""
)


class PresenceStore:
    """One per process. Owns a Redis client and the background sweeper."""

    def __init__(
        self,
        redis_url: str,
        *,
        ttl: float,
        sweep_interval: float,
        on_offline: OnOffline | None = None,
        key_prefix: str = "presence",
    ) -> None:
        self._redis: aioredis.Redis = aioredis.from_url(  # pyright: ignore[reportUnknownMemberType]
            redis_url, decode_responses=True
        )
        self.ttl = ttl
        self.refresh_interval = ttl / 3
        self._ttl_ms = max(1, int(ttl * 1000))
        self._sweep_interval = sweep_interval
        self._on_offline = on_offline
        self._prefix = key_prefix
        self._index = f"{key_prefix}:channels"
        self._touch: Any = self._redis.register_script(_TOUCH)  # pyright: ignore[reportUnknownMemberType]
        self._leave: Any = self._redis.register_script(_LEAVE)  # pyright: ignore[reportUnknownMemberType]
        self._sweep: Any = self._redis.register_script(_SWEEP)  # pyright: ignore[reportUnknownMemberType]
        self._online: Any = self._redis.register_script(_ONLINE)  # pyright: ignore[reportUnknownMemberType]
        self._task: asyncio.Task[None] | None = None

    # -- keys ---------------------------------------------------------------

    def channel_key(self, channel_id: uuid.UUID) -> str:
        return f"{self._prefix}:channel:{channel_id}"

    def user_key(self, user_id: uuid.UUID) -> str:
        return f"{self._prefix}:{user_id}"

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        self._task = asyncio.create_task(self._sweep_loop(), name="presence-sweeper")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        with contextlib.suppress(*_REDIS_ERRORS):
            await self._redis.aclose()

    # -- operations (raise on Redis errors) ----------------------------------

    async def touch(
        self, channel_id: uuid.UUID, user_id: uuid.UUID, conn_id: uuid.UUID
    ) -> bool:
        """Add or refresh a socket's entry. True if the user just came online."""
        result = await self._touch(
            keys=[self.channel_key(channel_id), self._index, self.user_key(user_id)],
            args=[f"{user_id}:{conn_id}", str(user_id), self._ttl_ms, str(channel_id)],
        )
        return bool(result)

    async def leave(
        self, channel_id: uuid.UUID, user_id: uuid.UUID, conn_id: uuid.UUID
    ) -> bool:
        """Remove a socket's entry. True if the user just went offline."""
        result = await self._leave(
            keys=[self.channel_key(channel_id), self._index],
            args=[f"{user_id}:{conn_id}", str(user_id), str(channel_id)],
        )
        return bool(result)

    async def online(self, channel_id: uuid.UUID) -> list[uuid.UUID]:
        result: list[str] = await self._online(keys=[self.channel_key(channel_id)])
        return [uuid.UUID(u) for u in result]

    async def channels(self) -> list[uuid.UUID]:
        members: Any = await self._redis.smembers(self._index)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportGeneralTypeIssues]
        return [uuid.UUID(m) for m in cast(set[str], members)]

    async def sweep(self) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """Remove expired entries. Returns (channel_id, user_id) gone offline."""
        gone: list[tuple[uuid.UUID, uuid.UUID]] = []
        for channel_id in await self.channels():
            users: list[str] = await self._sweep(
                keys=[self.channel_key(channel_id), self._index],
                args=[str(channel_id)],
            )
            gone.extend((channel_id, uuid.UUID(u)) for u in users)
        return gone

    async def _sweep_loop(self) -> None:
        while True:
            await asyncio.sleep(self._sweep_interval)
            try:
                gone = await self.sweep()
            except _REDIS_ERRORS as exc:
                logger.warning("presence_sweep_failed", error=str(exc))
                continue
            for channel_id, user_id in gone:
                logger.info(
                    "presence_expired", channel_id=str(channel_id), user_id=str(user_id)
                )
                if self._on_offline is None:
                    continue
                try:
                    await self._on_offline(channel_id, user_id)
                except Exception:
                    logger.exception("presence_on_offline_failed")


class PresenceConnection:
    """
    One socket's presence. Never raises: when Redis is unavailable (or no
    store is installed) it assumes every join/leave is a change, matching the
    behaviour before S4.2, and the snapshot contains only the user.
    """

    def __init__(
        self, store: PresenceStore | None, channel_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        self._store = store
        self.channel_id = channel_id
        self.user_id = user_id
        self.conn_id = uuid.uuid4()
        self._last_touch = 0.0

    async def join(self) -> bool:
        return await self._touch(fallback=True)

    async def refresh(self) -> bool:
        """Extend the entry, at most once per ttl/3. True if it rejoined."""
        if self._store is None:
            return False
        if time.monotonic() - self._last_touch < self._store.refresh_interval:
            return False
        return await self._touch(fallback=False)

    async def leave(self) -> bool:
        if self._store is None:
            return True
        try:
            return await self._store.leave(self.channel_id, self.user_id, self.conn_id)
        except _REDIS_ERRORS as exc:
            self._warn("presence_leave_failed", exc)
            return True

    async def online(self) -> list[uuid.UUID]:
        if self._store is None:
            return [self.user_id]
        try:
            return await self._store.online(self.channel_id)
        except _REDIS_ERRORS as exc:
            self._warn("presence_snapshot_failed", exc)
            return [self.user_id]

    async def _touch(self, *, fallback: bool) -> bool:
        if self._store is None:
            return fallback
        self._last_touch = time.monotonic()
        try:
            return await self._store.touch(self.channel_id, self.user_id, self.conn_id)
        except _REDIS_ERRORS as exc:
            self._warn("presence_touch_failed", exc)
            return fallback

    def _warn(self, event: str, exc: Exception) -> None:
        logger.warning(
            event,
            channel_id=str(self.channel_id),
            user_id=str(self.user_id),
            error=str(exc),
        )


def presence_event(
    event_type: WSMessageType, channel_id: uuid.UUID, user_id: uuid.UUID
) -> dict[str, Any]:
    return {
        "type": event_type,
        "payload": {"user_id": str(user_id), "channel_id": str(channel_id)},
    }


# ---------------------------------------------------------------------------
# Process-wide store, installed by the app lifespan (see main.py).
# ---------------------------------------------------------------------------

_store: PresenceStore | None = None


def set_store(store: PresenceStore | None) -> None:
    global _store
    _store = store


def connection(channel_id: uuid.UUID, user_id: uuid.UUID) -> PresenceConnection:
    return PresenceConnection(_store, channel_id, user_id)
