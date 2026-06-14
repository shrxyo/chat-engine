# PROGRESS — chat-engine

> Lossless state for compaction recovery. Read first at every session start. Update on `claim`, `block`, `done`.
>
> Statuses: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`.
> Format per row: `<ID> <STATUS> [<owner>] [<YYYY-MM-DD>] — <one-line note>`.

---

## Snapshot

| Metric                  | Value      |
| ----------------------- | ---------- |
| Last updated            | 2026-05-22 |
| Active branch (default) | `main`     |
| Stories DONE / total    | 7 / 39     |
| Currently IN_PROGRESS   | 0          |
| Currently BLOCKED       | 0          |

---

## EPIC 1 — Foundation

| ID   | Status      | Notes                                                                 |
| ---- | ----------- | --------------------------------------------------------------------- |
| S1.1 | DONE        | Monorepo: `backend/`, `frontend/`, `infra/`, root Makefile, README.   |
| S1.2 | DONE        | FastAPI scaffold; `src/app/` layout; ruff + pyright; uv lockfile.     |
| S1.3 | DONE        | Next.js 15 scaffold; shadcn primitives generated; TanStack Query, Zustand, zod, next-auth installed. |
| S1.4 | DONE        | `docker-compose.yml` runs Postgres (pgvector) + Redis with healthchecks. |
| S1.5 | DONE        | Initial schema migrated. `messages.embedding vector(1536)` column present. `scripts/seed.py` seeds 3 channels / 5 users / 50 messages. |

## EPIC 2 — Core Messaging

| ID   | Status      | Notes                                                                                  |
| ---- | ----------- | -------------------------------------------------------------------------------------- |
| S2.1 | DONE        | HTTP API for channels, messages, users; cursor pagination; soft delete; pytest covers happy/401/403/validation. |
| S2.2 | DONE        | Single-instance WebSocket gateway. ConnectionManager. Event types in `schemas/ws.py`. JWT auth before `ws.accept()`. structlog. Both `publish()` (Redis) and in-process broadcast (Epic 6 stub). |
| S2.3 | IN_PROGRESS | [agent 2026-06-14] Frontend chat UI. Building three-panel layout, WS context, messages hooks, all components. |
| S2.4 | TODO        | Direct messages.                                                                       |

## EPIC 3 — Authentication

| ID   | Status      | Notes                                                                |
| ---- | ----------- | -------------------------------------------------------------------- |
| S3.1 | TODO        | OAuth via Auth.js (GitHub + Google). Backend JWT validation exists; frontend NextAuth config missing. |
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
| S6.1 | TODO   | Pub/Sub fanout. `pubsub.publish()` exists; no subscriber loop. ConnectionManager still local-only. |
| S6.2 | TODO   | Go gateway (optional). |
| S6.3 | TODO   | Load balancing. |
| S6.4 | TODO   | k6 load tests. |
| S6.5 | TODO   | DB scaling: pool, indexes, read replica, Redis cache. |

## EPIC 7 — Observability

| ID   | Status | Notes |
| ---- | ------ | ----- |
| S7.1 | TODO   | structlog is configured but no `RequestIDMiddleware`. |
| S7.2 | TODO   | OpenTelemetry. |
| S7.3 | TODO   | Prometheus + Grafana. |
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
| S11.2 | TODO   | No production Dockerfiles yet. |
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

- `2026-05-22` — Agent governance bootstrap: AGENTS.md (root + submodules), `.cursor/rules/*`, `.cursorignore`, `docs/{BACKLOG,PROGRESS,ARCHITECTURE,OPERATIONS,CONVENTIONS}.md`, `.env.example`, `CONTRIBUTING.md`.
- `2026-05-22` — Backend Phase 1–2 already implemented (HTTP API + WS gateway + tests).
- `2026-05-22` — Frontend scaffold in place; routes are placeholders.
