# PROGRESS — chat-engine

> Lossless state for compaction recovery. Read first at every session start. Update on `claim`, `block`, `done`.
>
> Statuses: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`.
> Format per row: `<ID> <STATUS> [<owner>] [<YYYY-MM-DD>] — <one-line note>`.

---

## Snapshot

| Metric                  | Value      |
| ----------------------- | ---------- |
| Last updated            | 2026-11-21 |
| Active branch (default) | `main`     |
| Stories DONE / total    | 13 / 39    |
| Currently IN_PROGRESS   | 0          |
| Currently BLOCKED       | 0          |
| Currently PARTIAL       | 3 (S6.5, S7.3, S11.2) |

---

## EPIC 1 — Foundation

| ID   | Status      | Notes                                                                 |
| ---- | ----------- | --------------------------------------------------------------------- |
| S1.1 | DONE        | Monorepo: `backend/`, `frontend/`, `infra/`, root Makefile, README.   |
| S1.2 | DONE        | FastAPI scaffold; `src/app/` layout; ruff + pyright; uv lockfile.     |
| S1.3 | DONE        | Next.js 15 scaffold; shadcn primitives generated; TanStack Query, Zustand, zod, next-auth installed. |
| S1.4 | DONE        | `docker-compose.yml` runs full stack: Postgres, Redis, backend (FastAPI + migrations), frontend (Next.js). `docker compose up` starts everything. `backend/Dockerfile` and `frontend/Dockerfile` added (multi-stage, non-root). |
| S1.5 | DONE        | Initial schema migrated. `messages.embedding vector(1536)` column present. `scripts/seed.py` seeds 3 channels / 5 users / 50 messages. |

## EPIC 2 — Core Messaging

| ID   | Status      | Notes                                                                                  |
| ---- | ----------- | -------------------------------------------------------------------------------------- |
| S2.1 | DONE        | HTTP API for channels, messages, users; cursor pagination; soft delete; pytest covers happy/401/403/validation. |
| S2.2 | DONE        | Single-instance WebSocket gateway. ConnectionManager. Event types in `schemas/ws.py`. JWT auth before `ws.accept()`. structlog. Both `publish()` (Redis) and in-process broadcast (Epic 6 stub). |
| S2.3 | DONE        | Three-panel Discord-style layout, WebSocketContext (reconnect + backoff), PresenceContext, useMessages (infinite query + WS updates + optimistic send), MessageList (react-virtual + infinite scroll + auto-scroll), Message, MessageInput, TypingIndicator, ChannelSidebar, MembersPanel. Vitest installed; 7 tests pass; lint + typecheck green. |
| S2.4 | DONE        | Direct messages: POST/GET /api/dm (find-or-create), DMSection sidebar, ChannelHeader for DM, Send DM from members panel, DMs excluded from GET /api/channels. |

## EPIC 3 — Authentication

| ID   | Status      | Notes                                                                |
| ---- | ----------- | -------------------------------------------------------------------- |
| S3.1 | DONE        | Auth.js v5 (GitHub + Google). JWT sessions. `signIn` callback upserts via `POST /api/auth/sync`. Backend JWT (`sub`, `email`, `name`) in `session.accessToken`. `middleware.ts` protects `/channels/*`. Sign-in page + sidebar sign-out. |
| S3.2 | TODO        | Rate limiting + security headers.                                    |

## EPIC 4 — Real-time UX

| ID   | Status | Notes |
| ---- | ------ | ----- |
| S4.1 | TODO   | Typing indicators (backend rebroadcasts already supported; frontend hook + UI missing). |
| S4.2 | TODO   | Presence via Redis TTL. |
| S4.3 | TODO   | Reconnect + gap fill (needs `GET /api/channels/{id}/messages?after=` endpoint). |
| S4.4 | TODO   | Read receipts + unread counts. |

## EPIC 5 — AI Layer

| ID   | Status | Notes |
| ---- | ------ | ----- |
| S5.1 | TODO   | arq worker service. No `backend/src/app/worker/` directory yet. |
| S5.2 | TODO   | Semantic search endpoint + Cmd+K modal. |
| S5.3 | TODO   | `@assistant` RAG streaming. |
| S5.4 | TODO   | Thread summarization. |
| S5.5 | TODO   | Daily digest. |

## EPIC 6 — Horizontal Scaling

| ID   | Status | Notes |
| ---- | ------ | ----- |
| S6.1 | DONE | `RedisBus` fanout: per-instance subscribe/unsubscribe by local refcount, publish-only handlers, parallel send with slow-consumer eviction, reconnect + resubscribe. Verified across 2 processes. |
| S6.2 | TODO   | Go gateway (optional). |
| S6.3 | DONE | nginx LB (`infra/nginx/nginx.conf`): round-robin, no stickiness, WS upgrade, 1h idle timeout, passive health (max_fails=2/5s), DNS `resolve` so `--scale` needs no nginx restart. Backend has no host port. One-shot `migrate` service. |
| S6.4 | DONE        | k6 WebSocket flood (`make load-test`) via nginx over 3 replicas; seed script mints JWTs to a git-ignored file. Max sustainable 200 VUs: 0 lost, msg_rtt p50 9ms / p99 749ms. Reports in `docs/benchmarks/`; findings in SPRINT T5. |
| S6.5 | PARTIAL | Pool + indexes DONE (T2): QueuePool 5+15, pre_ping; partial `ix_messages_channel_id_id_live (channel_id, id) WHERE deleted_at IS NULL`; `ix_channel_memberships_channel_id`. Read replica + Redis cache TODO. |

## EPIC 7 — Observability

| ID   | Status | Notes |
| ---- | ------ | ----- |
| S7.1 | TODO   | structlog is configured but no `RequestIDMiddleware`. |
| S7.2 | IN_PROGRESS | OpenTelemetry (sprint T6). Claimed 2026-11-21. |
| S7.3 | PARTIAL | T4 DONE: `/metrics` (instrumentator) + `ws_active_connections`, `messages_broadcast_total`, `redis_pubsub_publish_total`, `message_broadcast_latency_seconds`; `server_ts` on `message.new`; Prometheus (Docker DNS discovery) + Grafana overview dashboard (`--profile observability`). TODO: `db_query_duration_seconds`, embedding metrics (S5.1), Latency/AI Worker/Database dashboards. |
| S7.4 | TODO   | Sentry. |

## EPIC 8 — Product Features

| ID   | Status | Notes |
| ---- | ------ | ----- |
| S8.1 | TODO   | Reactions (data model + WS event exist; UI missing). |
| S8.2 | TODO   | Threads / replies. `reply_to_id` column exists. |
| S8.3 | TODO   | File uploads (R2). |
| S8.4 | TODO   | Mentions + notifications. |
| S8.5 | TODO   | Slash commands. |
| S8.6 | TODO   | Admin + moderation. |

## EPIC 9 — PWA

| ID   | Status | Notes |
| ---- | ------ | ----- |
| S9.1 | TODO   | Manifest + install prompt. |
| S9.2 | TODO   | Service Worker + offline. |

## EPIC 10 — Testing

| ID    | Status | Notes |
| ----- | ------ | ----- |
| S10.1 | PARTIAL| Backend tests exist: `test_channels.py`, `test_messages.py`, `test_users.py`, `test_health.py`, `test_ws.py`. Coverage gate not yet enforced. |
| S10.2 | TODO   | Frontend Vitest setup. |
| S10.3 | TODO   | Playwright E2E. |

## EPIC 11 — CI/CD

| ID    | Status | Notes |
| ----- | ------ | ----- |
| S11.1 | TODO   | No `.github/workflows/` yet. |
| S11.2 | PARTIAL | `backend/Dockerfile` and `frontend/Dockerfile` added (multi-stage, non-root, dev mode). Production hardening needed: `next build && next start`, standalone output, worker Dockerfile, gateway Dockerfile. |
| S11.3 | TODO   | No `fly.toml`. |
| S11.4 | TODO   | Preview deployments. |

## EPIC 12 — Docs & Portfolio

| ID    | Status     | Notes |
| ----- | ---------- | ----- |
| S12.1 | TODO       | `docs/ARCHITECTURE.md` stub created; needs Mermaid diagrams + decisions + numbers. |
| S12.2 | TODO       | README polish: GIF, badges, live demo link. |
| S12.3 | TODO       | Three blog posts. |
| S12.4 | TODO       | Demo video. |

---

## Activity log (newest first)

- `2026-11-21` — S6.4 DONE (T5): k6 load test. 200 VUs over 3 replicas: 6,981/6,981 echoed, p50 9ms, p99 749ms (misses the 100ms target); 500+ VUs degrade badly. Root causes: structlog's blocking stdout writes froze the event loop under Docker Desktop (load-test overlay logs to a file; app fix is S7.1), plus remaining loop stalls (follow-up: profile). nginx caps at ~4k sockets. `tests/test_loadtest_seed.py` (8). 89 tests green.
- `2026-11-21` — S7.3 PARTIAL (T4): Prometheus metrics + Grafana. 3 replicas scraped via DNS; 120 messages → counter 120, 360 latency observations (one per delivering replica). Removed `PROMETHEUS_MULTIPROC_DIR` from `.env.example` (crashed startup). nginx hides `/metrics`. 81 tests green.
- `2026-11-21` — S6.3 DONE (T3): nginx on :8000 in front of `--scale backend=3`. 4 and 6 clients spread across 3 replicas each got 1 broadcast exactly once (3/3 runs). Live scale 3→4 picked up without restart. Migrations moved to a one-shot `migrate` service (replicas raced on `alembic upgrade`). 72 tests green.
- `2026-11-21` — S6.5 PARTIAL (T2): pooled engine replaces NullPool (session round trip p50 34ms → 2.5ms locally). Migration `c7e2a9f4b1d3` adds 2 indexes CONCURRENTLY. `tests/test_db_pool_indexes.py` (5). 72 tests green.
- `2026-11-21` — S6.1 DONE: Redis Pub/Sub fanout. `services/pubsub.py:RedisBus`, async `ConnectionManager.connect/disconnect`, handlers publish only. `tests/test_pubsub_fanout.py` (8). WS tests now use real Redis.
- `2026-11-21` — Sprint T0 done: local folder wired to origin @ `c0e7380`; baseline 59 tests green, lint clean, 100 pre-existing pyright errors (see `docs/SPRINT.md` T0).
- `2026-11-21` — Sprint plan created in `docs/SPRINT.md` (S6.1, S6.5, S6.3, S7.3, S6.4, S7.2, then S4.2, S4.3, S12.1). Read it after this file.
- `2026-06-14` — S2.4 DONE: Direct messages. `POST /api/dm` find-or-create, `GET /api/dm` list with other_user. `DMSection` in sidebar. `ChannelHeader` shows other user for DMs. "Send DM" in members panel avatar menu. `GET /api/channels` excludes `is_dm=true`. Backend tests in `test_dm.py`.
- `2026-06-14` — S1.4 ENHANCED: Full-stack Docker Compose. `backend/Dockerfile` (python:3.12-slim, multi-stage, uv, `docker-entrypoint.sh` runs Alembic then uvicorn --reload), `frontend/Dockerfile` (node:20-alpine, multi-stage, npm ci, next dev). `docker-compose.yml` extended with `backend` and `frontend` services, healthchecks, `depends_on: service_healthy`, source bind-mounts for hot reload. `frontend/next.config.ts` uses `BACKEND_URL` env var for server-side API rewrite.
- `2026-06-14` — S3.1 DONE: OAuth auth (GitHub + Google). Backend `POST /api/auth/sync` upserts user, returns `{user_id, access_token}`. NextAuth `signIn`/`jwt`/`session` callbacks wire backend JWT. `middleware.ts` guards `/channels/*`. Sign-in page with provider buttons. `SidebarFooter` sign-out menu.
- `2026-06-14` — S2.3 DONE: Full frontend chat UI. Three-panel layout, WS/Presence contexts, useMessages hook (infinite query + optimistic send), MessageList (react-virtual + day groups + infinite scroll + auto-scroll), MessageInput (auto-grow, emoji picker, send on Enter), TypingIndicator (animated dots), ChannelSidebar (active highlight, unread badge), MembersPanel (online/offline status). Vitest installed; 7 tests green; lint + typecheck pass.
- `2026-05-22` — Agent governance bootstrap: AGENTS.md (root + submodules), `.cursor/rules/*`, `.cursorignore`, `docs/{BACKLOG,PROGRESS,ARCHITECTURE,OPERATIONS,CONVENTIONS}.md`, `.env.example`, `CONTRIBUTING.md`.
- `2026-05-22` — Backend Phase 1–2 already implemented (HTTP API + WS gateway + tests).
- `2026-05-22` — Frontend scaffold in place; routes are placeholders.
