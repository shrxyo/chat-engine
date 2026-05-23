# BACKLOG — chat-engine

> Compact, ID-anchored task list distilled from `chat-plan.md`. Reference items by their **ID** (`S2.3`, `T6.1.4`). Original prose lives in `chat-plan.md`; agents should grep there only when an entry below is insufficient.
>
> **Convention.** Stories are `S<epic>.<story>` (e.g. `S3.1`). Tasks are `T<epic>.<story>.<task>` (e.g. `T1.2.4`). Use these IDs in branches, commits, PR titles, and `docs/PROGRESS.md`.

---

## EPIC 1 — Foundation & Infrastructure

### S1.1 — Monorepo scaffold
Three top-level dirs (`backend/`, `frontend/`, `infra/`), root `Makefile`, root `.gitignore`, root `README.md`, initial commit.

### S1.2 — Backend Python project
FastAPI + SQLModel + asyncpg + Alembic + pydantic-settings + structlog. `uv` package manager. Strict `ruff` + `pyright`. `src/app/` layout: `main.py`, `config.py`, `database.py`, `dependencies.py`, `models/`, `schemas/`, `routers/`, `services/`. Makefile targets: `run`, `test`, `lint`, `typecheck`, `migrate`.

### S1.3 — Frontend Next.js project
Next.js 15 App Router + TS strict + Tailwind v4 + shadcn/ui. Path alias `@/`. Deps: TanStack Query v5, Zustand, next-auth v5 (beta), zod, lucide-react, date-fns, clsx, tailwind-merge. ESLint + Prettier with Tailwind plugin. Placeholder routes: `/`, `/auth/signin`, `/channels/[channelId]`. shadcn primitives: button, input, scroll-area, avatar, badge, command, dialog, dropdown-menu, separator, sheet, skeleton, sonner, tooltip.

### S1.4 — Local dev with Docker Compose
`docker-compose.yml`: `postgres` (pgvector/pgvector:pg16) + `redis` (redis:7-alpine), health checks, named volume for Postgres. `.env.example` documents all vars. `infra/postgres/init.sql` enables pgvector. `make dev` boots compose + backend + frontend.

### S1.5 — DB schema + migrations
SQLModel tables: `users`, `channels`, `channel_memberships`, `messages`, `message_reactions`, `message_attachments`. Async Alembic. UUID PKs. `created_at`/`updated_at` everywhere. `embedding vector(1536)` (nullable) on `messages`. `reply_to_id` self-FK on `messages`. `scripts/seed.py` loads 3 channels / 5 users / 50 messages.

---

## EPIC 2 — Core Messaging

### S2.1 — HTTP API (channels, messages, users)
- `GET /api/channels` — list for current user
- `POST /api/channels` — create
- `GET /api/channels/{id}` — detail + members
- `DELETE /api/channels/{id}` — soft delete (admin)
- `GET /api/channels/{id}/messages?before=<uuid>&limit=50` — cursor pagination
- `PATCH /api/messages/{id}` — edit own
- `DELETE /api/messages/{id}` — soft delete own
- `GET /api/users/me`, `PATCH /api/users/me`, `GET /api/users/{id}`
- `GET /health`, `GET /ready`
- Pytest coverage for each route: happy path, 401/403, validation.

### S2.2 — WebSocket gateway (single instance)
`WS /ws/{channel_id}?token=<jwt>`. `ConnectionManager` tracks `{channel_id: {user_id: ws}}`. Event types: `message.new`, `message.edit`, `message.delete`, `message.reaction`, `typing.start`, `typing.stop`, `presence.join`, `presence.leave`, `error`. Auth + membership before `ws.accept()`. Persist before broadcast. structlog on every event.

### S2.3 — Frontend chat UI
Three-pane layout (sidebar / main / members). Components: `ChannelSidebar`, `MembersPanel`, `MessageList` (virtualized via `@tanstack/react-virtual`), `Message`, `MessageInput`, `TypingIndicator`. Hooks: `useWebSocket`, `useMessages`. Contexts: `WebSocketContext`, `PresenceContext`. Optimistic send, infinite-scroll history, auto-scroll-to-bottom unless user scrolled up.

### S2.4 — Direct messages
DMs = channels with `is_dm=true` and exactly two members. `POST /api/dm` finds-or-creates. `GET /api/dm` lists. `DMSection` in sidebar. DM header shows other user.

---

## EPIC 3 — Authentication

### S3.1 — OAuth (GitHub + Google) via Auth.js
NextAuth v5. JWT sessions (no DB session table). `signIn` callback upserts user via `POST /api/auth/sync`. JWT carries `sub=<user_uuid>`. Backend `get_current_user` validates `Authorization: Bearer <jwt>` (HS256, shared `SECRET_KEY`). WebSocket validates the same token from `?token=`. `middleware.ts` redirects unauthenticated `/channels/*` requests to `/auth/signin`.

### S3.2 — Rate limiting + security headers
Redis sliding-window limiter as a `Depends` factory. Limits: messages 60/min, WS connect 30/min, auth endpoints 10/min. Returns 429 with `Retry-After`. Middleware adds `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security`, `Content-Security-Policy`. Frontend handles 429 with toast.

---

## EPIC 4 — Real-time UX Polish

### S4.1 — Typing indicators
`typing.start` (first keystroke after 2s idle), `typing.stop` (debounced 2s). Server rebroadcasts; no DB. Client `useTypingIndicator` hook. `TypingIndicator` component reads `PresenceContext`. Stale entries cleared after 5s.

### S4.2 — Presence
Redis key `presence:{user_id}` with TTL 30s. Client pings every 20s; any WS message refreshes TTL. On connect/disconnect: broadcast `presence.join`/`presence.leave`. New connection receives `presence.snapshot`. `MembersPanel` renders online dot. Channel header shows "N online".

### S4.3 — Reconnect with gap fill
Exponential backoff (1, 2, 4, 8, … cap 30s) + jitter. Client tracks `lastMessageId`. On reconnect: `GET /api/channels/{id}/messages?after=<id>`. Merge + dedupe by ID. If gap >200, full reload. Banner: "Reconnecting…", "Reconnected — catching up".

### S4.4 — Read receipts + unread counts
Column `last_read_message_id` on `channel_memberships` (Alembic migration). `POST /api/channels/{id}/read`. `GET /api/channels` returns `unread_count`. `IntersectionObserver` on last visible message → debounced read call. Sidebar badge + bold channel name.

---

## EPIC 5 — AI Layer

### S5.1 — arq worker service
`backend/src/app/worker/main.py` (`WorkerSettings`). Deps: `arq`, `openai`, `tenacity`. `tasks/embeddings.py:generate_embedding(message_id)` — fetch row, call OpenAI `text-embedding-3-small`, write back. Retry 3× exponential. Enqueue from WS handler post-persist. Compose service: `worker`. Prometheus metrics: `embedding_job_duration_seconds`, `embedding_job_total{status}`.

### S5.2 — Semantic search
`GET /api/search?q=<text>&channel_id=<uuid?>&limit=20`. Embed query (Redis 1h cache). pgvector: `ORDER BY embedding <=> $1 LIMIT 20`. Filter soft-deleted + non-member channels. pgvector index: `CREATE INDEX ... USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)`. Frontend `SearchModal` (shadcn `Command`) opens on `Cmd+K`. Debounced 300ms. Click jumps to message.

### S5.3 — `@assistant` RAG
Seed an `ASSISTANT_USER_ID` system user. WS handler detects `@assistant` prefix → enqueues `assistant_reply` arq job. Worker: embed question → top-5 from same channel → build prompt → stream OpenAI `gpt-4o` with `stream=True` → publish each chunk as `message.stream` to Redis topic. Final chunk publishes `message.stream.done`. Save full response as `Message` from `ASSISTANT_USER_ID`. Frontend: streaming `AssistantMessage` component, distinct style, "Assistant is thinking…" placeholder.

### S5.4 — Thread summarization
`POST /api/messages/{id}/summarize` collects thread replies → LLM → saves `Message` with `type="summary"` from `ASSISTANT_USER_ID`. Button on thread header when replies >5. One summary per thread.

### S5.5 — Daily digest
arq cron job. Per user: rank unseen messages by cosine similarity to user's "interest profile" (concatenated past messages). Group by channel. LLM-generated 3–5 sentence summary per channel. Posted as DM from `ASSISTANT_USER_ID`. User preference to disable (default on).

---

## EPIC 6 — Horizontal Scaling

### S6.1 — Redis Pub/Sub fanout
Refactor `ConnectionManager`:
- `connect()`: subscribe Redis `chat:{channel_id}` if first local subscriber.
- `disconnect()`: unsubscribe if last local subscriber.
- `handle_message()`: persist → publish to Redis → **do not** broadcast locally.
- Background asyncio task subscribes and calls local broadcast on receive.
Verify with `docker compose up --scale backend=3`: message on backend-1 reaches client on backend-2.

### S6.2 — Go WebSocket gateway (optional, high-signal)
`gateway/` Go module. `gorilla/websocket`, `go-redis/v9`, `golang-jwt`. JWT HS256 validation with shared `SECRET_KEY`. Connection registry: `sync.Map[channelID]map[connID]conn`. Redis subscribe per channel with refcounting. Graceful shutdown drains connections with `{"type":"reconnect"}`. Prometheus `/metrics`. Multi-stage Dockerfile.

### S6.3 — Load balancing
nginx or Traefik in `docker-compose.yml`. Round-robin (stateless gateways → no stickiness). Health check `/health` every 5s. Verify: 4 clients across 3 gateways all receive the same broadcast.

### S6.4 — k6 load tests
`infra/load-tests/websocket_flood.js`: ramp 0→10K VU over 5min, hold 10min. Each VU connects, sends 1 msg/30s, measures RTT. Thresholds: `ws_connecting` P95 <500ms, msg RTT P99 <200ms. `connection_density.js`: 10K idle. Save HTML report + Grafana screenshots. `make load-test`.

### S6.5 — DB scaling
asyncpg pool min=5/max=20. Indexes: `messages(channel_id, created_at DESC)`, `messages(channel_id, id DESC)`, `channel_memberships(user_id)`, pgvector ivfflat, `message_reactions(message_id)`. Read replica via streaming replication. Redis cache for hot reads (channel metadata 5min, recent message page 30s).

---

## EPIC 7 — Observability

### S7.1 — Structured logging
`structlog` JSON in prod, pretty in dev. `RequestIDMiddleware` generates UUID per request, stored in `contextvars.ContextVar`, auto-included in every log entry. Log: WS connect/disconnect, message send/broadcast, slow DB query >100ms, job enqueue/complete/fail.

### S7.2 — OpenTelemetry
Auto-instrument FastAPI, asyncpg, Redis. Manual spans around OpenAI calls. OTel Collector service in compose. Jaeger for trace UI. Same instrumentation in worker and Go gateway.

### S7.3 — Prometheus + Grafana
`prometheus-fastapi-instrumentator` for HTTP. Custom metrics: `ws_active_connections`, `messages_broadcast_total`, `message_broadcast_latency_seconds`, `embedding_queue_depth`, `embedding_job_duration_seconds`, `redis_pubsub_publish_total`, `db_query_duration_seconds`. `/metrics` on every service. Prometheus + Grafana compose services. Dashboards JSON in `infra/grafana/dashboards/`: Overview, Latency, AI Worker, Database.

### S7.4 — Sentry
Backend `sentry-sdk[fastapi]` with `traces_sample_rate=0.2`. User/channel IDs in scope. Frontend `@sentry/nextjs` (`npx @sentry/wizard`). `ErrorBoundary` wrapping channel page. DSNs in env.

---

## EPIC 8 — Product Features

### S8.1 — Message reactions
`POST /api/messages/{id}/reactions` toggle. WS broadcast `message.reaction` with full reaction list. `ReactionBar` below message. `emoji-mart` picker. Optimistic toggle with rollback.

### S8.2 — Threads / replies
`GET /api/messages/{id}/thread?before=&limit=50`. Index `reply_to_id`. `reply_count` in message response. `ThreadPanel` slides in from right with own input. Root message shows "N replies" + avatar pile. Thread messages not in main view.

### S8.3 — File uploads
Cloudflare R2 (S3-compatible). `POST /api/upload/presign` returns pre-signed PUT URL (5min expiry). Allowlist: images, PDFs, common video. Max 25MB. Frontend drag-and-drop + file picker → presign → PUT to R2 → send message with `attachment_url`. Inline image + lightbox. File card for docs. HTML5 `<video>` for video.

### S8.4 — Mentions + notifications
Parse `@username` in message content → create `Notification` row per mention. `notifications` table: `id`, `user_id`, `type`, `message_id`, `channel_id`, `read_at`, `created_at`. `GET /api/notifications`, `POST /api/notifications/{id}/read`. WS `notification.new` to mentioned user. `@` in input opens user picker. `NotificationBell` badge in sidebar. Browser push via Service Worker + VAPID (Epic 9 dependency).

### S8.5 — Slash commands
Frontend: `/` opens command picker (fuzzy search). `SlashCommandRegistry` map. Built-in: `/giphy`, `/poll`, `/remind`. Backend: `poll_options`, `poll_votes` tables. `POST /api/poll`, `POST /api/poll/{id}/vote`. `POST /api/reminders` schedules arq cron. `chrono-node` for natural-language times. Document new-command flow in `CONTRIBUTING.md`.

### S8.6 — Admin + moderation
Tables: `banned_users`, `pinned_messages`, `moderation_log`. Routes (admin only): `DELETE /api/channels/{id}/members/{user_id}` (kick), `POST /api/channels/{id}/bans`, `POST /api/messages/{id}/pin`, `GET /api/channels/{id}/pinned`. Frontend: hover menus on member + message for admins. Pinned-messages banner (collapsible). `ChannelSettings` modal.

---

## EPIC 9 — Progressive Web App

### S9.1 — PWA manifest + install prompt
`public/manifest.json`: name, icons (192, 512), `display: standalone`. Link in `app/layout.tsx`. `InstallPrompt` intercepts `beforeinstallprompt`. Test Chrome desktop + Safari iOS.

### S9.2 — Service Worker + offline
Build SW (next-pwa or manual). Cache strategy: `StaleWhileRevalidate` for static, `NetworkFirst` for `/api`. IndexedDB (`idb`) for last 100 messages per channel. Offline send queue with idempotency key. "You're offline" banner. Flush queue on reconnect with dedupe.

---

## EPIC 10 — Testing

### S10.1 — Backend tests (≥70% coverage)
`conftest.py` owns test DB + rollback fixture. `factories.py`: `UserFactory`, `ChannelFactory`, `MessageFactory`. Integration tests for every router. Service unit tests (rate limiter, search, ConnectionManager). Worker tests with `respx` mocking OpenAI. `--cov-fail-under=70`.

### S10.2 — Frontend unit tests (Vitest)
`vitest` + `@testing-library/react` + `msw`. Tests for `useWebSocket` reconnect logic, `useMessages` pagination + optimistic updates, `useTypingIndicator` debounce, `MessageInput` Enter/Shift+Enter. `vitest --coverage` in CI.

### S10.3 — E2E (Playwright)
`@playwright/test` with chromium. Tests: sign-in flow, send-and-receive across two contexts, semantic search after embedding ready, reconnect, file upload, `@assistant` streaming. CI: `npx playwright test --reporter=github`.

---

## EPIC 11 — CI/CD + Deployment

### S11.1 — GitHub Actions CI
`.github/workflows/ci.yml`. Parallel jobs: `backend-lint`, `backend-test`, `frontend-lint`, `frontend-test`, `e2e`. Cache pip + npm. Upload Playwright artifacts on failure. Codecov upload. Coverage gate <70% fails. Target <5min run.

### S11.2 — Production Docker images
`backend/Dockerfile`, `worker/Dockerfile`, `frontend/Dockerfile` — multi-stage, non-root. `gateway/Dockerfile` (if S6.2). Push to GHCR on `main` merge with `latest` + `sha-<short>`.

### S11.3 — Deploy to Fly.io
`flyctl`. One Fly app per service: backend, frontend, worker (internal), [gateway]. Fly Postgres (hobby). Upstash Redis (Fly addon). Secrets via `fly secrets set`. Alembic as `release_command`. GitHub Actions deploys on `main` merge.

### S11.4 — Preview deployments
Per PR: `chat-engine-pr-<num>` Fly app, separate Postgres (or schema-per-PR). Comment preview URL on PR. Destroy app on PR close.

---

## EPIC 12 — Documentation & Portfolio

### S12.1 — ARCHITECTURE.md
Mermaid system diagram, ER diagram, WebSocket scaling sequence diagram, AI pipeline. "Engineering Decisions" section: pgvector vs Pinecone, arq vs Celery, Auth.js JWTs vs DB sessions, Go vs Python gateway, cursor vs offset pagination, optimistic UI rationale. k6 load-test numbers. `EXPLAIN ANALYZE` for top 5 queries.

### S12.2 — README polish
Hero GIF (Kap, 15s walkthrough). Live demo link first paragraph. Tech badges. Key features list. Mermaid arch diagram. 4-command "Getting Started". CI/coverage/license badges.

### S12.3 — Engineering blog posts
1. "Scaling WebSockets to 10K connections with Redis Pub/Sub" (~1500w).
2. "Semantic chat search with pgvector + RAG" (~1200w).
3. "WebSocket auth patterns that actually work" (~1000w).
Cross-post to dev.to, HN, /r/programming.

### S12.4 — Demo video
3–5 min narrated walkthrough. Seed DB with 500 messages / 5 channels / 10 users via Faker. Script: sign in → switch channels → send + receive → typing indicator → Cmd+K search → `@assistant` → file upload → Grafana glance. QuickTime/Loom + YouTube unlisted.

---

## Dependency graph (high-level)

```
S1.1 → S1.2 → S1.5 → S2.1 → S2.2 → S2.3
                 ↓             ↓
              S5.1 → S5.2 → S5.3
                              ↓
                            S6.1 → S6.3 → S6.4
S3.1 → S3.2 (gates real-time features in prod)
S7.1 → S7.2 → S7.3 (any order after S2.2)
S10.* (any time after the matching feature)
S11.* (after S2.* + S3.1)
S12.* (final)
```
