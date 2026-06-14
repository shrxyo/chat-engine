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
  GW1 -.metrics.-> OTel
  API -.metrics.-> OTel
  Worker -.metrics.-> OTel
  OTel --> Prom --> Graf
  API -.errors.-> Sentry
  Browser -.errors.-> Sentry
```

In the current single-instance state, "Gateway" and "API" are the same Python process. Epic 6 (`S6.1`) splits the WebSocket plane behind Redis Pub/Sub.

---

## Component responsibilities

| Component         | Responsibility                                                                    | Stack                                 |
| ----------------- | --------------------------------------------------------------------------------- | ------------------------------------- |
| Browser (PWA)     | UI, optimistic updates, offline cache, push notifications                         | Next.js 15, TS, shadcn, TanStack Query|
| HTTP API          | REST reads (channels, messages history, search, auth sync, uploads), admin ops    | FastAPI, asyncpg, SQLModel            |
| WebSocket Gateway | Stateless WS termination, JWT validation, Redis pub/sub fan-out                   | FastAPI now → Go later (`S6.2`)       |
| AI Worker         | Embedding generation, `@assistant` RAG, summarization, daily digest               | arq, OpenAI, tenacity                 |
| Postgres          | Source of truth: users, channels, memberships, messages (+ vector embeddings), reactions, attachments, notifications | Postgres 16 + pgvector |
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
| `message.new`       | client ↔ server  | `{ content, reply_to_id? }`                                        |
| `message.edit`      | client ↔ server  | `{ message_id, content }`                                          |
| `message.delete`    | client ↔ server  | `{ message_id }`                                                   |
| `message.reaction`  | client ↔ server  | `{ message_id, emoji }`                                            |
| `message.stream`    | server → client  | `{ message_id, chunk, done }` (assistant streaming)                |
| `typing.start`      | client ↔ server  | `{ user_id, channel_id }`                                          |
| `typing.stop`       | client ↔ server  | `{ user_id, channel_id }`                                          |
| `presence.join`     | server → client  | `{ user_id, channel_id }`                                          |
| `presence.leave`    | server → client  | `{ user_id, channel_id }`                                          |
| `presence.snapshot` | server → client  | `{ online_user_ids: [...] }`                                       |
| `notification.new`  | server → client  | `{ notification_id, type, message_id }`                            |
| `error`             | server → client  | `{ message }`                                                      |

Connection URL: `WS /ws/{channel_id}?token=<jwt>`. Server **must** authenticate and authorize before `ws.accept()`. Auth failure closes with code `4001`.

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
| Pagination                            | **Cursor (`?before=<uuid>`)**       | Stable under concurrent writes; offset pagination shifts rows when new messages arrive.                                        |
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

Optional `--profile observability` brings up Prometheus, Grafana, OTel collector, Jaeger (Epic 7 — not yet wired).

Port reservations are listed in `infra/AGENTS.md`.
