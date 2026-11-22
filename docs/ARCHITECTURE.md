# ARCHITECTURE — chat-engine

> Target architecture (what we are building toward, per `chat-plan.md`). Sections marked **planned** are not yet implemented; see `docs/PROGRESS.md` for live state.

---

## System overview

```mermaid
graph TB
  subgraph Client
    Browser["Next.js 15 PWA<br/>TypeScript · TanStack Query · Zustand"]
  end
  subgraph Edge
    LB[Load Balancer<br/>nginx / Traefik]
  end
  subgraph Gateways["WebSocket Gateways (N replicas, stateless)"]
    GW1[Gateway 1]
    GW2[Gateway 2]
  end
  subgraph BackendSvc["Backend"]
    API[FastAPI HTTP API]
    Worker[arq AI Worker]
  end
  subgraph Data
    PG[(Postgres + pgvector)]
    Redis[(Redis<br/>Pub/Sub · cache · presence)]
    R2[(R2 / S3<br/>attachments)]
  end
  subgraph Obs[Observability]
    OTel[OTel Collector]
    Prom[Prometheus]
    Graf[Grafana]
    Sentry
  end

  Browser -->|HTTPS REST| LB --> API
  Browser <-.WS.-> LB
  LB --> GW1
  LB --> GW2
  GW1 <--> Redis
  GW2 <--> Redis
  API --> PG
  API --> Redis
  API --> R2
  Worker --> PG
  Worker --> Redis
  Prom -.scrape /metrics.-> GW1
  Prom -.scrape /metrics.-> API
  Worker -.metrics.-> OTel
  OTel --> Prom
  Prom --> Graf
  API -.errors.-> Sentry
  Browser -.errors.-> Sentry
```

"Gateway" and "API" are the same Python process, and any number of them can run side by side (`S6.1`). Each instance runs one `RedisBus` (`services/pubsub.py`): handlers only `publish()` to Redis topic `channel:{id}`, and each instance subscribes to a channel's topic while it holds at least one local socket in that channel, delivering what it receives to those sockets. The sender's own instance also delivers from Redis, so there is exactly one delivery path. If publishing fails, the event is delivered locally (single-instance degraded mode). The envelope is `{"payload", "exclude_user_id", "trace"?}`; `trace` carries the OpenTelemetry context (`S7.2`). Delivery is at-most-once (Pub/Sub); clients recover gaps with `S4.3`.

**Reconnect gap fill (`S4.3`).** `WebSocketContext` exposes `status` (`connecting` / `open` / `reconnecting`) and `reconnectCount`. On each reconnect, `useMessages` asks for `GET /api/channels/{id}/messages?after=<newest confirmed id>&limit=200`, merges the result into the newest page and dedupes by id (live messages on the new socket may already be there). If `has_more` is true (gap > 200) or the cursor is unknown (400), it drops the cache and reloads the newest page. A banner shows "Reconnecting…" while the socket is down and "Reconnected — catching up…" during the fill. Edits and deletes made during the gap are not recovered (no event log); they show on the next full load.

---

## Component responsibilities

| Component         | Responsibility                                                                    | Stack                                 |
| ----------------- | --------------------------------------------------------------------------------- | ------------------------------------- |
| Browser (PWA)     | UI, optimistic updates, offline cache, push notifications                         | Next.js 15, TS, shadcn, TanStack Query|
| HTTP API          | REST reads (channels, messages history, search, auth sync, uploads), admin ops    | FastAPI, asyncpg, SQLModel            |
| WebSocket Gateway | Stateless WS termination, JWT validation, Redis pub/sub fan-out                   | FastAPI now → Go later (`S6.2`)       |
| AI Worker         | Embedding generation, `@assistant` RAG, summarization, daily digest               | arq, OpenAI, tenacity                 |
| Postgres          | Source of truth: users, channels, memberships, messages (+ vector embeddings), reactions, attachments, notifications | Postgres 16 + pgvector. Per-instance pool 5 + 15 overflow (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`), so N instances use up to 20·N connections; keep under `max_connections` (100) |
| Redis             | Pub/Sub broadcast, sliding-window rate limit, presence TTL keys, query embedding cache, hot-read cache | Redis 7 |
| R2 / S3           | Attachment storage; clients PUT via pre-signed URLs                               | Cloudflare R2 (S3 API)                |

---

## Data model (current)

```mermaid
erDiagram
  USER ||--o{ CHANNEL_MEMBERSHIP : has
  CHANNEL ||--o{ CHANNEL_MEMBERSHIP : has
  CHANNEL ||--o{ MESSAGE : contains
  USER ||--o{ MESSAGE : authors
  MESSAGE ||--o{ MESSAGE_REACTION : has
  MESSAGE ||--o{ MESSAGE_ATTACHMENT : has
  MESSAGE ||--o| MESSAGE : reply_to

  USER {
    uuid id PK
    text email
    text name
    text avatar_url
    text provider
    text provider_id
    timestamp created_at
    timestamp updated_at
  }

  CHANNEL {
    uuid id PK
    text name
    text description
    bool is_dm
    uuid created_by FK
    timestamp deleted_at
    timestamp created_at
  }

  CHANNEL_MEMBERSHIP {
    uuid user_id PK,FK
    uuid channel_id PK,FK
    text role
    timestamp joined_at
  }

  MESSAGE {
    uuid id PK
    uuid channel_id FK
    uuid user_id FK
    text content
    vector embedding "nullable, 1536"
    uuid reply_to_id FK "nullable"
    timestamp edited_at
    timestamp deleted_at
    timestamp created_at
  }

  MESSAGE_REACTION {
    uuid id PK
    uuid message_id FK
    uuid user_id FK
    text emoji
  }

  MESSAGE_ATTACHMENT {
    uuid id PK
    uuid message_id FK
    text filename
    text content_type
    text url
    int size_bytes
  }
```

Tables added later: `notifications` (`S8.4`), `banned_users`, `pinned_messages`, `moderation_log` (`S8.6`), `poll_options`, `poll_votes` (`S8.5`).

---

## WebSocket protocol

All messages are JSON: `{ "type": <WSMessageType>, "payload": <object> }`.

| Type                | Direction        | Payload                                                            |
| ------------------- | ---------------- | ------------------------------------------------------------------ |
| `message.new`       | client ↔ server  | in: `{ content, reply_to_id? }` · out: message + `server_ts` (epoch ms received) |
| `message.edit`      | client ↔ server  | `{ message_id, content }`                                          |
| `message.delete`    | client ↔ server  | `{ message_id }`                                                   |
| `message.reaction`  | client ↔ server  | `{ message_id, emoji }`                                            |
| `message.stream`    | server → client  | `{ message_id, chunk, done }` (assistant streaming)                |
| `typing.start`      | client ↔ server  | `{ user_id, channel_id }`                                          |
| `typing.stop`       | client ↔ server  | `{ user_id, channel_id }`                                          |
| `presence.join`     | server → client  | `{ user_id, channel_id }`                                          |
| `presence.leave`    | server → client  | `{ user_id, channel_id }`                                          |
| `presence.snapshot` | server → client  | `{ channel_id, online_user_ids: [...] }`, once per new socket, sender included |
| `ping`              | client → server  | `{}` every 20s; no reply (any inbound frame refreshes presence)    |
| `notification.new`  | server → client  | `{ notification_id, type, message_id }`                            |
| `error`             | server → client  | `{ message }`                                                      |

Connection URL: `WS /ws/{channel_id}?token=<jwt>`. Server **must** authenticate and authorize before `ws.accept()`. Auth failure closes with code `4001`.

## Presence (`S4.2`)

Presence state lives in Redis, so all replicas agree on it.

| Key | Type | Content |
| --- | ---- | ------- |
| `presence:channel:{channel_id}` | sorted set | One member per open socket, `"{user_id}:{conn_id}"`, score = expiry (epoch ms, Redis `TIME`). Key `PEXPIRE` 4×TTL as a last-resort cleanup. |
| `presence:{user_id}` | string, `PX` TTL | "Online anywhere" flag, refreshed with the set. Nothing reads it yet. |
| `presence:channels` | set | Channel ids that have members, iterated by the sweeper. |

- **TTL 30s** (`PRESENCE_TTL_SECONDS`). Any inbound frame refreshes the socket's entry, at most once per TTL/3 per socket. The client sends `ping` every 20s.
- **Join/leave are per user, not per socket.** `presence.join` goes out only when a user's first live socket in the channel appears, and `presence.leave` only when the last one goes, so two tabs on two replicas produce one join and one leave.
- **Expiry.** Every replica sweeps every 5s (`PRESENCE_SWEEP_INTERVAL_SECONDS`) and publishes `presence.leave` for users whose last entry expired. That covers sockets that went silent and replicas that died. A silent socket that speaks again rejoins (`presence.join`).
- **Exactly once.** Touch, leave, sweep and snapshot are Lua scripts, so concurrent replicas can't both report the same transition. They use Redis `TIME`, so replica clock skew doesn't matter. The scripts touch keys of different hash slots, so this assumes a single Redis, not Cluster.
- **Redis down.** Join/leave fall back to "always announce" (the behaviour before S4.2) and the snapshot contains only the connecting user.

---

## Metrics (`S7.3`)

Every backend replica serves its own `/metrics` (one uvicorn process per container, so no `PROMETHEUS_MULTIPROC_DIR`). Prometheus finds replicas through Docker DNS (`dns_sd_configs` on `backend`), so `--scale` needs no config change. nginx returns 404 for `/metrics`; it is only reachable on the compose network.

| Metric | Type | Meaning |
| ------ | ---- | ------- |
| `ws_active_connections` | Gauge | Sockets held by this replica (read from `ConnectionManager` at scrape time) |
| `messages_broadcast_total` | Counter | `message.new` accepted, counted once on the receiving replica |
| `redis_pubsub_publish_total{result}` | Counter | Redis PUBLISH calls; `error` = local-only fallback |
| `message_broadcast_latency_seconds` | Histogram | `server_ts` (handler start) → send to every local socket returned, observed on each delivering replica, so it includes DB insert, Redis hop and fanout |
| `http_requests_total`, `http_request_duration_seconds`, `http_request_duration_highr_seconds` | Counter / Histogram | `prometheus-fastapi-instrumentator`; `/metrics`, `/health`, `/ready` excluded |

`server_ts` is wall-clock time, so the cross-replica latency assumes the hosts' clocks agree (true on one Docker host; needs NTP across machines). Negative values are clamped to 0. Dashboard: `infra/grafana/dashboards/overview.json`.

## Tracing (`S7.2`)

`app/telemetry.py` turns tracing on only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (tests force it blank). Path: backend → OTLP/gRPC → `otel-collector` (:4317) → Jaeger (UI :16686), both under `--profile observability`. Spans carry `service.name=chat-engine-backend` and `service.instance.id=<container hostname>`. Sampling uses the standard `OTEL_TRACES_SAMPLER` variables (default: every trace).

- **Auto-instrumented:** FastAPI HTTP routes (`/health`, `/ready`, `/metrics` excluded), SQLAlchemy/asyncpg queries, Redis commands. The pub/sub listener's polling is not a command, so it creates no spans.
- **WebSockets:** the socket itself is not a span. One span would stay open for the whole connection and put every message into one trace. Instead `ws.connect` (auth + register + presence join) and `ws.message.new` each start a new trace.
- **`message.new` trace:** `ws.message.new` → `db.persist` (→ `INSERT`, `SELECT`) and `pubsub.publish` (PRODUCER, → `PUBLISH`). `publish()` adds the W3C context to the Redis envelope as `"trace": {"traceparent": ...}`, and every delivering replica opens `pubsub.deliver` (CONSUMER, attribute `chat.local_recipients`) under it. One trace therefore shows the send on replica A and the fanout on replicas A..N. Events published outside a span (typing, presence leave) carry no context and produce no spans. Envelopes without (or with a bad) `trace` still deliver.
- The load-test overlay disables tracing so k6 runs stay comparable with the T5 baseline.

---

## WebSocket scaling (planned — `S6.1`)

```mermaid
sequenceDiagram
  participant C1 as Client on GW-1
  participant C2 as Client on GW-2
  participant GW1
  participant GW2
  participant R as Redis
  participant DB as Postgres

  C1->>GW1: message.new
  GW1->>DB: INSERT message
  DB-->>GW1: ok
  GW1->>R: PUBLISH chat:<channel_id> {payload}
  R-->>GW1: ack
  R-->>GW2: message
  GW1->>C1: message.new echo (own optimistic confirm)
  GW2->>C2: message.new
```

Each gateway maintains a refcount per channel of local subscribers. When the first local client joins, the gateway subscribes to `chat:<channel_id>`; when the last leaves, it unsubscribes. Stateless: any gateway can serve any user → round-robin LB, no sticky sessions.

---

## AI pipeline (planned — Epic 5)

```mermaid
flowchart LR
  M[Message persisted] -->|arq enqueue| Q1[embed_message job]
  Q1 -->|OpenAI text-embedding-3-small| E[1536-dim vector]
  E -->|UPDATE messages.embedding| PG[(Postgres + pgvector)]

  U[User: @assistant ...] -->|arq enqueue| Q2[assistant_reply job]
  Q2 -->|embed question| EQ[query vector]
  EQ -->|cosine similarity, LIMIT 5| PG
  PG -->|top-5 messages| Ctx[Context]
  Ctx -->|prompt + stream=True| LLM[OpenAI gpt-4o]
  LLM -.chunks.-> Q2 -->|PUBLISH message.stream| R[(Redis)]
  R --> Browser
```

---

## Engineering decisions

| Decision                              | Choice                              | Why                                                                                                                            |
| ------------------------------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Vector store                          | **pgvector** (extension on Postgres)| Single source of truth; no second system to operate; performance is adequate up to tens of millions of vectors.                |
| Background work                       | **arq**                             | Async-native (no thread overhead like Celery), small surface area, Redis-backed (we already run Redis).                       |
| WebSocket auth                        | **JWT in `?token=` query param**    | Cookies aren't always sent on cross-origin WS upgrades; first-message auth adds a round trip; query param works everywhere with HTTPS. |
| Session storage                       | **JWT only**, no DB session table   | Stateless backend; gateway can validate without a DB hit; refresh handled by NextAuth.                                         |
| Gateway language                      | **Python now, Go later (`S6.2`)**   | Python is enough until ~10K connections; Go gives 10× density per node when needed.                                            |
| Pagination                            | **Cursor (`?before=` / `?after=<message id>`), ordered by `(created_at, id)`** | Stable under concurrent writes; offset pagination shifts rows when new messages arrive. Ids are random uuid4, so the cursor id is resolved to its `(created_at, id)` position and compared as a row (`id` breaks ties). Index `ix_messages_channel_id_created_at_id_live (channel_id, created_at, id) WHERE deleted_at IS NULL` serves both directions with no sort. Known limit: `created_at` is set in the app before commit, so a message from a slow transaction can commit with a `created_at` older than one already delivered, and an `after=` fill can miss it (window ≈ commit latency). |
| Frontend state                        | **TanStack Query + Zustand**        | TQ for server state with optimistic updates + cache; Zustand for tiny client-only stores (no Redux ceremony).                  |
| Soft delete                           | **`deleted_at` column**             | Preserves audit trail and lets us undo accidental deletes; reads always filter `deleted_at IS NULL`.                           |
| Migrations                            | **Alembic, async, append-only**     | Standard for SQLAlchemy; never edit a merged revision (creates merge-conflict landmines).                                      |
| Real-time scaling                     | **Redis Pub/Sub fan-out**           | Stateless gateways behind round-robin LB; no sticky sessions; trivial horizontal scale.                                        |
| File uploads                          | **Pre-signed PUT to R2**            | Files never traverse our servers; R2 has no egress fees.                                                                       |

---

## Non-functional targets

| Property                          | Target                                |
| --------------------------------- | ------------------------------------- |
| P50 broadcast latency             | <50 ms                                |
| P99 broadcast latency             | <200 ms                               |
| Concurrent WS connections (Py)    | 10K (single replica)                  |
| Concurrent WS connections (Go)    | 100K (single replica) — `S6.2`        |
| Test coverage (backend)           | ≥70% lines                            |
| CI wall time                      | <5 minutes                            |
| Postgres write IOPS               | <500 sustained                        |
| Sentry trace sample rate          | 20% (prod)                            |

These are tracked in Grafana (`S7.3`) and validated by k6 (`S6.4`).

---

## Local environment

`docker-compose.yml` runs the full stack — Postgres, Redis, backend (FastAPI + Alembic migrations on startup), and frontend (Next.js dev server). A single `docker compose up` is all that is needed.

```
docker compose up
```

Services start in dependency order: Postgres & Redis first (healthchecked), then backend (runs `alembic upgrade head` before starting uvicorn with `--reload`), then frontend (`next dev` with source code bind-mounted for hot reload).

Alternatively, run only infrastructure in Docker and the application services on the host for a lighter dev loop:

```bash
docker compose up -d postgres redis
make -C backend install && make dev-backend
make -C frontend install && make dev-frontend
```

Dockerfiles live at `backend/Dockerfile` and `frontend/Dockerfile` (multi-stage, non-root runtime user).

Optional `--profile observability` brings up Prometheus (:9090), Grafana (:3001, overview dashboard as home, anonymous read-only), the OTel collector (:4317) and Jaeger (:16686). Traces are exported only when `.env` sets `OTEL_EXPORTER_OTLP_ENDPOINT` (any value; compose points the backends at `otel-collector`).

Port reservations are listed in `infra/AGENTS.md`.
