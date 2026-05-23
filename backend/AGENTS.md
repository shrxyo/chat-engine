# AGENTS.md — backend/

> Scope: Python 3.12 FastAPI service + arq AI worker. Read root `AGENTS.md` first.

## Layout

```
backend/
├── src/app/
│   ├── main.py          # FastAPI factory + lifespan
│   ├── config.py        # pydantic-settings (env-driven)
│   ├── database.py      # async SQLAlchemy engine + session
│   ├── dependencies.py  # FastAPI Depends (auth, session, channel-membership)
│   ├── models/          # SQLModel tables (1 file per table)
│   ├── schemas/         # Pydantic request/response (never reuse models)
│   ├── routers/         # 1 file per route group; thin, delegates to services
│   ├── services/        # Business logic (testable in isolation)
│   └── worker/          # arq AI worker (Epic 5)
├── alembic/             # Migrations — append-only
├── tests/               # pytest, conftest.py owns DB fixture
└── scripts/             # one-off CLI scripts (seed, etc.)
```

## Commands

| Action            | Command                                           |
| ----------------- | ------------------------------------------------- |
| Install           | `uv sync`                                         |
| Run dev server    | `make run`  (uvicorn, hot reload)                 |
| Run worker (arq)  | `make worker`                                     |
| New migration     | `make migration name="add_foo"`                   |
| Apply migrations  | `make migrate`                                    |
| Tests             | `make test`                                       |
| Lint + format     | `make lint`                                       |
| Type check        | `make typecheck`                                  |
| Seed dev data     | `uv run python scripts/seed.py`                   |

All `make` targets must be run from `backend/`.

## Architectural constraints

- Routers are **thin**: validate input → call service → return schema. No business logic in routes.
- Services are **pure async functions** taking `AsyncSession` and primitives. No global state except the connection manager.
- One `WebSocket` event handler per type in `routers/ws.py`. Add new types in `schemas/ws.py` `WSMessageType` enum.
- All writes happen inside `async with AsyncSessionLocal()` blocks or via the `SessionDep`. Never share sessions across requests.
- Broadcasts go through both `publish()` (Redis) and `manager.broadcast_to_channel()` until Epic 6 lands; the Redis listener is no-op until then.
- Soft delete (`deleted_at`) only — never `DELETE FROM`. Filter `deleted_at IS NULL` in reads.
- Auth on WebSocket: token via `?token=` query param. Validate before `ws.accept()`.

## Testing rules

- All HTTP routes have at least: happy path + 401/403 + validation error.
- Use `tests/factories.py` (factory-boy) for fixtures. Never inline `User(...)` in tests.
- WebSocket tests in `tests/test_ws.py` use FastAPI `TestClient.websocket_connect`.
- Run `make test` — coverage threshold is `--cov-fail-under=70` once Epic 10 lands.

## Forbidden patterns

- `print()` for logging — use `structlog.get_logger(__name__)`.
- `time.sleep` in async code — use `asyncio.sleep`.
- Sync `requests`/`httpx.Client` — use `httpx.AsyncClient`.
- Editing a merged Alembic revision — always add a new one.
- `from app.models import *` — explicit imports only.

## Adding a new feature (template)

1. Read the relevant story in `docs/BACKLOG.md` (e.g. `S2.4 — Direct messages`).
2. If schema change: edit `models/`, then `alembic revision --autogenerate`.
3. Add Pydantic schema in `schemas/`.
4. Write router/service stub + failing tests in `tests/test_<area>.py`.
5. Implement until tests pass.
6. `make lint && make typecheck && make test`.
7. Mark IDs `DONE` in `docs/PROGRESS.md`.
