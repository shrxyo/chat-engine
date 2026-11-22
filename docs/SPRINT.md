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
| T1 | S6.1 | DONE | 2h | B1, B2 |
| T2 | S6.5 (partial) | DONE | 45m | B1 |
| T3 | S6.3 | IN_PROGRESS | 1h | B1 |
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

## T1 — S6.1 Redis Pub/Sub fanout  · branch `feat/S6.1-pubsub-fanout` · DONE

- [x] Tests first: `tests/test_pubsub_fanout.py` (8 tests, real Redis): cross-instance delivery, exactly-once on the sender's instance, `exclude_user_id` across instances, unsubscribe on last local socket (checked with `PUBSUB NUMSUB`), replaced socket not dropped, slow socket evicted, Redis-down local fallback, resubscribe after Redis kills the connection
- [x] `RedisBus` in `services/pubsub.py`: publish client + separate PubSub connection; subscribe waits for Redis confirmation; tracks wanted topics itself (redis-py forgets a SUBSCRIBE that failed while Redis was down); listener reconnects with backoff
- [x] `ConnectionManager`: async `connect`/`disconnect` drive subscribe/unsubscribe; `disconnect(..., ws)` only removes that exact socket; parallel fanout with per-send timeout (2s), stalled sockets evicted and closed with 1013
- [x] `main.py` lifespan starts/stops the bus
- [x] `routers/ws.py`: all 4 duplicate local broadcasts removed; 7 publish sites; typing + presence.join use `exclude_user_id`
- [x] `tests/test_ws.py`: publish mock removed, so WS tests make a real Redis round trip
- [x] Manual: two uvicorn processes (:8001, :8002). presence.join and message.new cross instances both ways; sender's echo exactly once; 3/3 runs. Script: scratchpad `cross_instance_check.py` (not committed). `docker compose --scale` deferred to T3 (needs nginx; backend host port collides).
- Results: 67 tests pass. Lint clean. Pyright 100 → 91 (0 in new code).
- **Observed:** ~70–80ms per cross-instance message on localhost. High for local; suspect `NullPool` opening a new Postgres connection per insert. Verify in T2/T4.
- Not covered: defensive branches (malformed envelope, deliver raising). Known pre-existing limit: one socket per (user, channel) on an instance, so a second tab replaces the first.

## T2 — S6.5 (partial) DB pool + indexes · branch `feat/S6.5-db-pool-indexes` · DONE

- [x] Tests first: `tests/test_db_pool_indexes.py` (5): pool type/size/overflow/pre_ping; both indexes exist; `EXPLAIN` of the message-list query uses the new index with no Sort node; member-by-channel query uses its index
- [x] `database.py`: `NullPool` → `pool_size=5, max_overflow=15, pool_pre_ping=True` (sizes in `config.py` as `DB_POOL_SIZE` / `DB_MAX_OVERFLOW`). Lifespan now calls `engine.dispose()` on shutdown.
- [x] New revision `c7e2a9f4b1d3`, built `CONCURRENTLY` in an autocommit block. Indexes declared on the models too, so `create_all` (tests) and `alembic check` agree.
  - **Changed from the plan:** the list query is `WHERE channel_id AND deleted_at IS NULL ORDER BY id DESC` (not `created_at`), so the index is `(channel_id, id) WHERE deleted_at IS NULL`, as in the BACKLOG S6.5 list. `channel_memberships(user_id)` would duplicate the PK `(user_id, channel_id)`, so the new index is on `channel_id` (member list, DM lookup).
- [x] Test suite with pooled engine: no change needed. Tests override `get_session`, and `test_ws.py` already gives the TestClient loop its own engine. The new test module runs on the session loop (`loop_scope="session"`) because it never commits.
- [x] `alembic upgrade head` → `downgrade -1` → `upgrade head` OK. `alembic check`: only drift is the pre-existing `messages_embedding_idx` (not declared on the model; not touched).
- Results: 72 tests pass. Lint clean. Pyright 91 (unchanged; 0 in new code).
- **Measured** (scratchpad `pool_bench.py`, 200 iterations, open session + `SELECT 1` + commit, localhost): NullPool p50 34.3ms / p99 283ms → pooled p50 2.5ms / p99 65ms. This accounts for most of T1's ~70–80ms per message. `echo=True` in development adds ~1.7ms p50; T5 should run with `ENVIRONMENT` ≠ development.
- **Found, not fixed (pre-existing, out of scope):** message pagination orders and cursors by `Message.id`, which is a random `uuid4`. So "newest 50" is not newest-by-time and `before=` cursors skip/repeat messages. Matters for T8 (`after=` gap fill). Fix needs a time-ordered key (UUIDv7 or `(created_at, id)` cursor); would need its own index then.

## T3 — S6.3 Load balancing · branch `feat/S6.3-nginx-lb` · IN_PROGRESS

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

- `2026-11-21` — T2 DONE (S6.5 partial). Pooled engine + 2 indexes. Session round trip p50 34ms → 2.5ms. 72 tests green.
- `2026-11-21` — T1 DONE (S6.1). Cross-instance fanout via Redis verified with 2 processes. 67 tests green.
- `2026-11-21` — T0 DONE. Repo wired to origin, baseline: 59 tests pass, lint clean, 100 pre-existing pyright errors.
- `2026-11-21` — Sprint file created. All tasks TODO.
