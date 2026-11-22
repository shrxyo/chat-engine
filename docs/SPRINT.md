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
| T3 | S6.3 | DONE | 1h | B1 |
| T4 | S7.3 | DONE | 1.5h | B2, B3 |
| T5 | S6.4 | DONE | 1.5h | B1, B2 |
| T6 | S7.2 | DONE | 1.5h | B3 |
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

## T3 — S6.3 Load balancing · branch `feat/S6.3-nginx-lb` · DONE

- [x] `infra/nginx/nginx.conf` (mounted as `conf.d/default.conf`): `upstream backend` round-robin, no stickiness; `Upgrade`/`Connection` via `map` (empty `Connection` for plain HTTP so upstream `keepalive 32` works); `proxy_read_timeout`/`proxy_send_timeout` 3600s; `X-Forwarded-*`; access log includes `upstream=$upstream_addr`
  - `resolver 127.0.0.11 valid=5s` + `server backend:8000 resolve` (needs nginx ≥ 1.27.3) so replicas added or removed by `--scale` join/leave without restarting nginx
  - Health: OSS nginx has no active checks. Passive: `max_fails=2 fail_timeout=5s`, `proxy_next_upstream error timeout http_502 http_503`, `proxy_connect_timeout 2s`. Backend compose healthcheck tightened to every 5s (gates nginx startup). nginx liveness at `/nginx-health`.
- [x] `docker-compose.yml`: `nginx` (`nginxinc/nginx-unprivileged:1.28-alpine`, non-root) on host `:8000` → container 8080. `backend` host port removed (`expose: 8000`).
- [x] **Added (not in plan, needed to scale):** one-shot `migrate` service runs `alembic upgrade head`; `backend` depends on it (`service_completed_successfully`) and sets `RUN_MIGRATIONS=false`. Otherwise every replica ran migrations at start and raced on DDL. `docker-entrypoint.sh` still migrates by default outside compose.
- [x] Frontend: browser URLs unchanged (`localhost:8000`, now nginx). Server-side `BACKEND_URL` → `http://nginx:8080` so Next.js rewrites are balanced too. Verified `GET :3000/api/channels` → 401 from a backend via nginx.
- [x] Verify (scratchpad `lb_check.py`, not committed: creates N users + channel, connects N sockets through :8000, one sends, reads `upstream=` from nginx logs): 3 replicas, 4 clients → upstreams 2/1/1, deliveries `[1,1,1,1]`; 6 clients → 2/2/2, all exactly once. 3/3 runs PASS.
- [x] Live scale 3 → 4 without touching nginx: 12 requests split 3/3/3/3.
- [x] `docker kill` of one replica, no nginx restart: run 1, 1/12 requests 502 (`no live upstreams`, during the DNS update window); run 2, 0/20 errors (one request retried to a live peer after the 2s connect timeout). Sockets on a killed replica drop; client reconnect handles it (gap fill is T8).
- Results: 72 tests pass. Lint clean. Pyright 91 (unchanged).
- Not done: uvicorn doesn't trust `X-Forwarded-For` yet (`--proxy-headers --forwarded-allow-ips`). Matters for S3.2 rate limiting by IP.

## T4 — S7.3 Prometheus + Grafana · branch `feat/S7.3-prometheus` · DONE

- [x] Tests first: `tests/test_metrics.py` (9): `/metrics` exposes all 4 custom metrics; HTTP requests counted by handler/status; `/health` not instrumented; connection count ignores a replaced socket; gauge follows a real socket open/close; `message.new` carries `server_ts` and bumps counter + histogram + publish counter; latency only observed for timestamped `message.new` with local sockets; failed publish counted as `error`
- [x] `prometheus-fastapi-instrumentator` → `/metrics` (not in OpenAPI). `/metrics`, `/health`, `/ready` excluded from HTTP metrics.
  - **Found:** the instrumentator registers its collectors on an app's first request; every later app in the process hits "duplicated timeseries" and silently records nothing (tests build one app per test). Fix: collectors built once in `app/metrics.py` (`HTTP_METRICS`) and `.add()`ed to each app. Finer HTTP buckets (from 1ms; library default starts at 10ms).
- [x] `app/metrics.py`: `ws_active_connections` (Gauge, `set_function` on the manager's `total_connection_count()`, so it can't drift), `messages_broadcast_total` (once per message on the receiving replica), `redis_pubsub_publish_total{result=ok|error}`, `message_broadcast_latency_seconds` (buckets 1ms–2.5s)
- [x] `server_ts` (epoch ms, taken at handler start) in `message.new` payload: `schemas/ws.py:MessageNewBroadcastPayload`. Latency observed in `ConnectionManager.broadcast_to_channel` after all local sends return, on every replica that delivers.
- [x] One process per container, so no multiprocess mode. **Removed `PROMETHEUS_MULTIPROC_DIR` from `.env.example`** (and local `.env`): its presence makes the instrumentator raise at startup and switches prometheus_client to mmap mode. Prometheus discovers replicas with `dns_sd_configs` on `backend` (refresh 5s).
- [x] `infra/prometheus/prometheus.yml`; compose `prometheus` (`v3.5.0`, :9090) and `grafana` (`12.1.1`, :3001) under `--profile observability`, healthchecked. Grafana: provisioned datasource + dashboard, overview as home, anonymous Viewer, admin password from `GRAFANA_ADMIN_PASSWORD` (default `admin`, local only).
- [x] `infra/grafana/dashboards/overview.json` (11 panels): replicas up, active connections (total + per replica), msgs/sec, broadcast p50/p95/p99 with a 100ms threshold line, Redis publishes by result, HTTP p50/p95/p99, HTTP req/s by status, HTTP p95 by route
- [x] **Added:** nginx returns 404 for `/metrics` (otherwise public, from a random replica).
- [x] Verify (scratchpad `metrics_traffic.py`, not committed: 6 sockets via nginx over 3 replicas, 120 messages, 6 HTTP calls): Prometheus sees 3 targets, 2 sockets each; `messages_broadcast_total` = 120 (40/replica); 360 latency observations (= 120 × 3 delivering replicas); 126 publishes ok (120 + 6 joins), 0 errors; every socket got all 120. All 11 panel queries return data through Grafana's query API.
- Results: 81 tests pass. Lint clean. Pyright 91 (unchanged; 0 in new code).
- **Observed (light load, dev mode with SQL echo, not a benchmark):** server broadcast p50 7.7ms / p95 37.5ms / p99 47.5ms; client-measured own-echo RTT p50 6.7ms / p99 53ms. Real numbers come from T5.
- **Found, not fixed (pre-existing):** `routers/ws.py` calls `manager.connect()` and the presence.join publish *before* the `try/finally` that unregisters the socket. If the handler is cancelled or raises there (e.g. during the Redis subscribe wait), the socket stays registered and the gauge over-counts. Hit only by TestClient's cancel-on-exit in tests; uvicorn doesn't cancel on client close. Fix: move both inside the `try`.
- Not done (rest of BACKLOG S7.3): `db_query_duration_seconds`, embedding metrics (need S5.1), Latency / AI Worker / Database dashboards.

## T5 — S6.4 k6 load test · branch `feat/S6.4-k6` · DONE

- [x] Seed script to create N load-test users + memberships and mint JWTs (no secrets committed; read `SECRET_KEY` from env)
- [x] `infra/load-tests/websocket_flood.js`: VU connects via nginx, sends msg every N s, measures RTT until own `message.new` echo (match by client nonce or content)
- [x] Custom k6 Trend `msg_rtt`; thresholds `ws_connecting p(95)<500`, `msg_rtt p(99)<100`
- [x] `make load-test` target
- [x] Run against 3 backend instances; ramp to max sustainable VUs on this machine
- [x] Save HTML report + Grafana screenshot to `docs/benchmarks/`
- [x] Record results below ⬇

### Results

| Date | Instances | Peak VUs | ws_connecting p95 | msg_rtt p50 | msg_rtt p99 | Errors | Notes |
|------|-----------|----------|-------------------|-------------|-------------|--------|-------|
| 2026-11-21 | 3 | 200 | 264ms | 9ms | **749ms** | 0 lost, 0 late, 0 server errors (6,981/6,981 echoed) | Best result; `docs/benchmarks/200vu-3r/` (report + Grafana) |
| 2026-11-21 | 3 | 500 | 6.24s | 19ms | 4.84s | 1,918 no echo within 5s | Old script (see note); `500vu-3r/` |
| 2026-11-21 | 3 | 1000 | 1.54s | 362ms | 3.81s | 27,849 no echo within 5s; 2 connects failed | Old script; fanout lag ~1 min; `1000vu-3r/` |
| 2026-11-21 | 3 | 2000 | 2.16s | 158ms | 8.61s | 98.7% of connect attempts failed; 2,070 server errors | Old script; past nginx connection limit; `2000vu-3r/` |

**Verdict:** no load level meets `msg_rtt p99<100ms` on this machine (Docker Desktop for Mac, 8 CPU / 4 GB VM). Max sustainable is **200 concurrent sockets** (0 lost, p50 9ms, p99 749ms). Per the rule above, the resume bullet must use these numbers, not "sub-100ms".

Run with `make load-test VUS=200 RAMP=1m HOLD=2m SESSION_S=600 RUN_NAME=200vu-3r`. Settings: room size 10, one message per VU every 5s, frontend stopped, Grafana stopped during runs.

**Findings:**
- **Blocking stdout logging (fixed for load tests only).** structlog writes synchronously from the event loop; on Docker Desktop the stdout pipe blocks under load and freezes every replica. With stdout logging, 500 VUs gave msg_rtt p99 7.64s, 10,813 of 13,853 messages with no echo, and DB pool timeouts. The load-test overlay sends backend logs to `/tmp/app.log` instead. App fix (level filtering + non-blocking output) belongs to S7.1. Also, `LOG_LEVEL` is not wired to structlog (pre-existing).
- **Event-loop stalls remain.** Even with file logging, the server-side broadcast median was ~240ms at 500 VUs while Postgres, Redis and CPU were idle, so something inside the backend still blocks the loop. Run-to-run variance is large (two 200-VU runs: p99 3.98s and 749ms). The worst stalls cluster at the end of the ramp, while sockets are still connecting. Needs profiling; follow-up story.
- **Docker Desktop VM jitter.** A bare asyncio loop in its own container with no load stalled up to 435ms (p99.9 78ms). Part of the tail is the host, not the app.
- **Uneven load balancing.** At 200 VUs nginx put 95/95/10 connections on the 3 replicas (Grafana screenshot).
- **nginx connection limit.** `worker_connections 1024` × 8 workers, with 2 connections per proxied WebSocket, gives roughly 4k sockets. At 2000 VUs connects failed, and the endless reconnects made it worse.
- **No messages dropped.** For the first 200-VU run, all 6,981 sent messages were in Postgres; the 156 reported "lost" were late echoes. The script now separates `msg_late` (echo > 5s, still timed) from `msg_lost` (no echo before close). The 500/1000/2000 rows above were run before this change, so their "no echo within 5s" counts include late messages.
- k6 1.3.0 has no `k6/websockets`; the script uses `k6/experimental/websockets`.
- Thresholds use the sprint's 100ms target (BACKLOG S6.4 says 200ms).

## T6 — S7.2 OpenTelemetry · branch `feat/S7.2-otel` · DONE

- [x] Tests first: `tests/test_telemetry.py` (9): no-op without endpoint; tests run with tracing off; resource has service name + replica id; HTTP server spans with probes excluded; delivery on instance B is a child of the publish span on A (same trace, PUBLISH nested); untraced publish → no spans; envelope with no/garbage/non-dict `trace` still delivers; `message.new` trace = root → `db.persist` (→ INSERT) + `pubsub.publish` → `pubsub.deliver`, no long-lived WS server span; `ws.connect` groups the auth queries
- [x] Deps: `opentelemetry-sdk`, `-exporter-otlp-proto-grpc`, instrumentation for `fastapi`, `sqlalchemy` (covers asyncpg), `redis` (1.45.2 / 0.66b2)
- [x] `app/telemetry.py`: `setup_telemetry(app, settings)` gated by `OTEL_EXPORTER_OTLP_ENDPOINT`; one global provider per process (idempotent); BatchSpanProcessor → OTLP/gRPC. **No-op in tests:** `tests/__init__.py` blanks the endpoint, because the local `.env` already set it (it was in `.env.example`). `.env.example` now ships it blank.
- [x] `ws.message.new` span (new root per message) with `db.persist` and `pubsub.publish` children; fanout is `pubsub.deliver` on each replica, with `chat.local_recipients` set by `ConnectionManager.broadcast_to_channel`
- [x] Trace context in the pub/sub envelope (`"trace": {"traceparent": ...}`), only when publishing inside a span, so typing/presence-leave stay untraced
- [x] **Added:** `ws.connect` span (auth + accept + register + presence join), else every WS handshake left orphan SELECT root spans. Auth checks folded into `_authorize()` so the span has one exit path. WS paths are excluded from the ASGI instrumentation (a span per socket would last the whole connection).
- [x] Compose: `otel-collector` (contrib `0.135.0`, :4317) + `jaeger` (`2.10.0`, in-memory, UI :16686) under `--profile observability`; config at `infra/otel/collector-config.yaml` (the name `infra/AGENTS.md` already listed). Backends get `${OTEL_EXPORTER_OTLP_ENDPOINT:+http://otel-collector:4317}`; load-test overlay blanks it to keep runs comparable with T5.
  - **Collector has no compose healthcheck:** the image is distroless (no shell/wget), so nothing can probe it from inside. Its `health_check` extension serves :13133 on the compose network. Nothing `depends_on` it; the exporter retries in the background.
- [x] Verify (3 replicas via nginx, 6 sockets in one channel, 5 messages, scratchpad `trace_traffic.py`): all 6 sockets got all 5; Jaeger has 5 `ws.message.new` traces of 11 spans each, every one with `pubsub.deliver` on all 3 replicas. Screenshot + trace JSON → `docs/benchmarks/otel/`.
- Results: 98 tests pass. Lint clean. Pyright 91 (unchanged; untyped `opentelemetry-instrumentation-*` calls suppressed inline like redis-py).
- Not done (rest of BACKLOG S7.2): manual spans around OpenAI calls and worker instrumentation (need Epic 5), Go gateway (S6.2, optional).

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

- `2026-11-21` — T5 DONE (S6.4). k6 WebSocket flood via nginx over 3 replicas. Max sustainable 200 VUs: 0 lost, msg_rtt p50 9ms / p99 749ms (misses 100ms target). Found blocking stdout logging (worked around in the load-test overlay; app fix is S7.1) and remaining loop stalls (follow-up). 89 tests green.
- `2026-11-21` — T4 DONE (S7.3 partial). `/metrics` + 4 custom metrics + `server_ts`; Prometheus (DNS discovery over replicas) + Grafana overview dashboard. Counts verified exact across 3 replicas. 81 tests green.
- `2026-11-21` — T3 DONE (S6.3). nginx LB over 3 replicas; broadcast reaches clients on every replica exactly once. Live scale-up without restart. 72 tests green.
- `2026-11-21` — T2 DONE (S6.5 partial). Pooled engine + 2 indexes. Session round trip p50 34ms → 2.5ms. 72 tests green.
- `2026-11-21` — T1 DONE (S6.1). Cross-instance fanout via Redis verified with 2 processes. 67 tests green.
- `2026-11-21` — T0 DONE. Repo wired to origin, baseline: 59 tests pass, lint clean, 100 pre-existing pyright errors.
- `2026-11-21` — Sprint file created. All tasks TODO.
