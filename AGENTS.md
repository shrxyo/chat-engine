# AGENTS.md — chat-engine

> Universal agent spec. Read this first. Submodule overrides live at `backend/AGENTS.md`, `frontend/AGENTS.md`, `infra/AGENTS.md`.

## Project

Realtime chat platform. Monorepo. Three top-level workspaces:

| Path        | Stack                                        | Owner        |
| ----------- | -------------------------------------------- | ------------ |
| `backend/`  | Python 3.12, FastAPI, SQLModel, asyncpg, arq | backend team |
| `frontend/` | Next.js 15 (App Router), TypeScript, shadcn  | frontend team|
| `infra/`    | Docker Compose, Postgres init, Grafana, k6   | infra        |

## Required reading before any task

1. `docs/PROGRESS.md` — current state. **Always read first.**
2. `docs/BACKLOG.md` — story/task IDs. Reference by ID (`S1.2`, `T2.1.3`).
3. `docs/ARCHITECTURE.md` — target architecture.
4. The submodule `AGENTS.md` of the directory you are editing.
5. `.cursor/rules/` — auto-attached on file matches; do not read all eagerly.

`chat-plan.md` is the original product brief. It is large (≈110 KB) and **excluded from default context**. Only read it via `grep` when a backlog ID's compact description is insufficient.

## Setup (deterministic)

```bash
cp .env.example .env
docker compose up -d postgres redis
make -C backend install
make -C frontend install
make dev          # backend on :8000, frontend on :3000
```

## Test runners (use these exact commands)

| Scope       | Command                                    |
| ----------- | ------------------------------------------ |
| Backend     | `make -C backend test`                     |
| Backend lint| `make -C backend lint && make -C backend typecheck` |
| Frontend    | `make -C frontend test`                    |
| Frontend lint| `make -C frontend lint && make -C frontend typecheck`|
| All         | `make test && make lint`                   |

## Hard constraints

- **TDD.** Write/extend failing tests before implementation (see `.cursor/rules/40-workflow.mdc`).
- **Plan adherence.** Implement only the task IDs assigned. Do not expand scope. Drift = bug.
- **Progress file.** Update `docs/PROGRESS.md` when claiming, blocking, or completing a task.
- **No commits to `main`.** Branch `feat/<story-id>-<slug>` or `fix/<short-slug>`. PR review required.
- **No secrets** in code, fixtures, or logs. Use env vars; `.env` is git-ignored.
- **Match existing style.** Run `lint` and `typecheck` before any commit; fix what you authored, leave pre-existing lint untouched unless asked.
- **Migrations** are append-only. Never edit a merged Alembic revision; create a new one.
- **Schema changes** require model + migration + test + `docs/ARCHITECTURE.md` update if cross-cutting.

## Decision routing

| If the task is…                          | Read first                                |
| ---------------------------------------- | ----------------------------------------- |
| HTTP route / WebSocket event             | `backend/AGENTS.md`, `12-backend-routers.mdc` |
| DB schema / migration                    | `11-backend-models.mdc`                   |
| React component / page                   | `frontend/AGENTS.md`, `21-frontend-components.mdc` |
| Docker / compose / Grafana / k6 / CI     | `infra/AGENTS.md`, `30-infra.mdc`         |
| Multi-file refactor                      | Dispatch a search subagent first; do not load files eagerly. |

## Token discipline

- Never load `chat-plan.md`, `*.lock`, `node_modules/`, `.next/`, `.venv/`, `htmlcov/`, large fixtures.
- Use JIT retrieval — grep for symbols, then read only matching files.
- Reuse the backlog ID system in prompts and commits (e.g. `feat(S3.1): GitHub OAuth`).
- Stop after the assigned tasks complete; do not "while I'm here" adjacent code.

## What "done" means

A task is **DONE** only when all of these are true:

1. Code merged (or PR ready) for the exact IDs assigned.
2. Tests added/updated, all pass locally (`make test`).
3. `lint` and `typecheck` pass.
4. `docs/PROGRESS.md` updated to mark the IDs as `DONE`.
5. If architecture changed: `docs/ARCHITECTURE.md` updated.
