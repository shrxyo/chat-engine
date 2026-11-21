# SPRINT — Resume-claims hardening (1 day)

> Goal: make every claim in the resume bullets below true **and measured**.
> Tracking file for this sprint. Canonical status still lives in `docs/PROGRESS.md` — update both when a task changes state.
>
> Statuses: `TODO` · `IN_PROGRESS` · `BLOCKED` · `DONE` · `CUT`
> Started: 2026-11-21

## Resume claims → stories

| # | Claim | Proven by |
|---|-------|-----------|
| B1 | Horizontally scalable FastAPI + PostgreSQL backend, high concurrency | T1, T2, T3, T5 |
| B2 | Redis + WebSockets, sub-100ms latency, state synchronization | T1, T4, T5, T7, T8 |
| B3 | OpenTelemetry + Prometheus observability | T4, T6 |

**Rule:** the final resume numbers must come from T5's k6 report. If measured p99 > 100ms, reword the bullet with the real number + concurrency.

---

## Task board

| Task | Backlog ID | Status | Est. | Claims |
|------|-----------|--------|------|--------|
| T0 | — (setup) | DONE | 10m | — |
| T1 | S6.1 | IN_PROGRESS | 2h | B1, B2 |
| T2 | S6.5 (partial) | TODO | 45m | B1 |
| T3 | S6.3 | TODO | 1h | B1 |
| T4 | S7.3 | TODO | 1.5h | B2, B3 |
| T5 | S6.4 | TODO | 1.5h | B1, B2 |
| T6 | S7.2 | TODO | 1.5h | B3 |
| — | **CUT LINE** (~8.5h) | | | |
| T7 | S4.2 | TODO | 1h | B2 |
| T8 | S4.3 | TODO | 1h | B2 |
| T9 | S12.1 | TODO | 30m | all |

---

## T0 — Setup

- [x] Local folder connected to `origin` (github.com/shrxyo/chat-engine); `main` tracks `origin/main` @ `c0e7380`. Verified identical to the downloaded folder.
- [x] `.env` created from `.env.example` (placeholders only; git-ignored)
- [x] Confirm baseline: `make -C backend test`, `make -C backend lint && make -C backend typecheck`
- [x] Pre-existing failures (do not fix unless asked):
  - **Tests:** 59 passed, 76% coverage. Needs `docker compose up -d postgres redis`.
  - **Lint:** clean.
  - **Typecheck: 100 pre-existing pyright errors**, mostly SQLModel/SQLAlchemy typing (`reportUnknownMemberType`, `reportArgumentType`); worst files `services/dm.py` (27), `routers/ws.py` (17), `routers/dm.py` (12). **Bar for this sprint: the count must not go above 100, and new files must have 0 errors.**
  - `services/pubsub.py` publish path is uncovered (lines 15, 26-30). Tests don't exercise real Redis yet; T1 must add that.
  - Frontend lint/typecheck/test not baselined (not touched until T8).

Branch per story: `feat/<story-id>-<slug>`.

## T1 — S6.1 Redis Pub/Sub fanout  · branch `feat/S6.1-pubsub-fanout`

Current state: `services/pubsub.py:publish()` publishes to `channel:{id}`; nothing subscribes. `ConnectionManager` is in-process only. Every handler in `routers/ws.py` calls `publish()` **and** `manager.broadcast_to_channel()`.

- [ ] Tests first (`tests/test_pubsub_fanout.py`): two `ConnectionManager` instances sharing one Redis → message published via A is delivered to a socket registered on B; no duplicate delivery on A
- [ ] `ConnectionManager`: subscribe to `channel:{id}` on first local socket, unsubscribe on last; refcount per channel
- [ ] Background listener task started/stopped in `main.py` `lifespan`; dispatches Redis messages to local sockets
- [ ] Remove every direct `manager.broadcast_to_channel(...)` that follows `publish(...)` in `routers/ws.py` (presence join/leave, message new/edit/delete, reaction, typing)
- [ ] Carry `exclude_user_id` inside the published envelope (typing + presence.join need it)
- [ ] Parallel fanout: `asyncio.gather` with per-send timeout; drop/disconnect sockets that fail
- [ ] Existing `tests/test_ws.py` still passes (may need Redis fixture or fake)
- [ ] Manual: `docker compose up --scale backend=2`, client on each instance sees the other's messages

Gotchas: Redis pub/sub connection must be separate from the publish client. Handle listener reconnect if Redis drops.

## T2 — S6.5 (partial) DB pool + indexes · branch `feat/S6.5-db-pool-indexes`

- [ ] `database.py`: replace `NullPool` with `pool_size=5, max_overflow=15, pool_pre_ping=True`
- [ ] New Alembic revision (never edit existing ones): `messages(channel_id, created_at DESC)`, `channel_memberships(user_id)`
- [ ] Check test suite still works with a pooled engine (event-loop scoping in `conftest.py`)
- [ ] `alembic upgrade head` + `downgrade -1` round-trip

## T3 — S6.3 Load balancing · branch `feat/S6.3-nginx-lb`

- [ ] `infra/nginx/nginx.conf`: upstream round-robin to `backend:8000`, WebSocket upgrade headers (`Upgrade`, `Connection`), long `proxy_read_timeout`
- [ ] `docker-compose.yml`: `nginx` service on `:8000`; remove host port mapping from `backend` so it can scale
- [ ] Frontend env still points at `localhost:8000` (now nginx) — verify
- [ ] Verify: `docker compose up --scale backend=3`; 3+ clients across instances all receive the same broadcast (check logs show different instance hostnames)

## T4 — S7.3 Prometheus + Grafana · branch `feat/S7.3-prometheus`

- [ ] Tests first: `/metrics` returns 200 and contains custom metric names
- [ ] Add `prometheus-fastapi-instrumentator` → `/metrics`
- [ ] `app/metrics.py`: `ws_active_connections` (Gauge), `messages_broadcast_total` (Counter), `redis_pubsub_publish_total` (Counter), `message_broadcast_latency_seconds` (Histogram, receive → fanout complete)
- [ ] Add `server_ts` (epoch ms) to `message.new` broadcast payload (`schemas/ws.py` + handler)
- [ ] Multi-process note: each scaled instance exposes its own `/metrics`; Prometheus scrapes via Docker DNS service discovery
- [ ] `infra/prometheus/prometheus.yml`; compose services `prometheus` (:9090) and `grafana` (:3001)
- [ ] `infra/grafana/dashboards/overview.json` + provisioning: active connections, msgs/sec, broadcast latency p50/p95/p99, HTTP latency

## T5 — S6.4 k6 load test · branch `feat/S6.4-k6`

- [ ] Seed script to create N load-test users + memberships and mint JWTs (no secrets committed; read `SECRET_KEY` from env)
- [ ] `infra/load-tests/websocket_flood.js`: VU connects via nginx, sends msg every N s, measures RTT until own `message.new` echo (match by client nonce or content)
- [ ] Custom k6 Trend `msg_rtt`; thresholds `ws_connecting p(95)<500`, `msg_rtt p(99)<100`
- [ ] `make load-test` target
- [ ] Run against 3 backend instances; ramp to max sustainable VUs on this machine
- [ ] Save HTML report + Grafana screenshot to `docs/benchmarks/`
- [ ] Record results below ⬇

### Results

| Date | Instances | Peak VUs | ws_connecting p95 | msg_rtt p50 | msg_rtt p99 | Errors | Notes |
|------|-----------|----------|-------------------|-------------|-------------|--------|-------|
| | | | | | | | |

## T6 — S7.2 OpenTelemetry · branch `feat/S7.2-otel`

- [ ] Deps: `opentelemetry-sdk`, `-exporter-otlp`, instrumentation for `fastapi`, `sqlalchemy`/`asyncpg`, `redis`
- [ ] `app/telemetry.py`: setup gated by env (`OTEL_EXPORTER_OTLP_ENDPOINT`); no-op in tests
- [ ] Manual span around `_handle_message_new`: child spans for DB persist, publish, fanout
- [ ] Propagate trace context in the pub/sub envelope so delivery on instance B links to the send on instance A
- [ ] Compose: `otel-collector` + `jaeger` (UI :16686), `infra/otel/collector.yaml`
- [ ] Screenshot of a cross-instance trace → `docs/benchmarks/`

---

## T7 — S4.2 Presence via Redis · branch `feat/S4.2-presence`

- [ ] Redis key `presence:{user_id}` TTL 30s; refreshed on any WS message + client ping every 20s
- [ ] Per-channel online set in Redis so presence is correct across instances
- [ ] On connect, send `presence.snapshot` to the new socket
- [ ] Tests: snapshot contents; TTL expiry → leave

## T8 — S4.3 Reconnect gap fill · branch `feat/S4.3-gap-fill`

- [ ] `GET /api/channels/{id}/messages?after=<id>` (tests first)
- [ ] Frontend: track `lastMessageId`, fetch on reconnect, merge + dedupe; >200 gap → full reload
- [ ] Reconnect banner

## T9 — S12.1 Docs

- [ ] `docs/ARCHITECTURE.md`: Mermaid diagram (client → nginx → N backends ↔ Redis pub/sub, Postgres, OTel/Prometheus)
- [ ] README: benchmark section with T5 numbers + screenshots
- [ ] `docs/PROGRESS.md`: mark finished IDs DONE, add activity log entries
- [ ] Final resume wording check against measured numbers

---

## Log (newest first)

- `2026-11-21` — T0 DONE. Repo wired to origin, baseline: 59 tests pass, lint clean, 100 pre-existing pyright errors.
- `2026-11-21` — Sprint file created. All tasks TODO.
