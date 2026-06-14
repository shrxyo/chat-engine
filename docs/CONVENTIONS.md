# CONVENTIONS — chat-engine

> Coding standards. Cross-language items first, language-specific next. The matching `.cursor/rules/*.mdc` files enforce most of these automatically.

---

## Universal

- **Names matter.** `MessageList`, not `ML`. `current_user`, not `cu`. Spend the keystrokes; agents and humans both read these.
- **Pure functions where possible.** Side effects in services, not in components or models.
- **Errors are typed.** Throw `HTTPException` (backend) or `Error` subclasses (frontend); never `Exception("oops")`.
- **No dead code.** If a function is unused, delete it. Git remembers.
- **No commented-out code.** If you want it later, branch.
- **Logs are structured.** Backend: `structlog` with kwargs. Frontend: `console.error` only for genuine runtime errors; Sentry is the prod signal.
- **Comments explain intent or trade-offs**, not what the code does. If you find yourself explaining the code, the code is wrong.

---

## Backend (Python 3.12)

### Style

| Topic            | Rule                                                                 |
| ---------------- | -------------------------------------------------------------------- |
| Linter           | `ruff check` + `ruff format` (`E`, `F`, `I`, `UP`, `B`, `SIM`)       |
| Type checker     | `pyright` strict; CI enforces                                        |
| Line length      | 88                                                                   |
| String quotes    | Double quotes (`ruff format` default)                                |
| Imports          | Stdlib → third-party → first-party (`app.*`); auto-sorted by ruff    |
| Async            | `async def` for any I/O; `asyncio.gather` for parallel awaits        |
| Type hints       | On every function. Prefer `X | None` over `Optional[X]`.             |
| Dataclasses      | Use Pydantic / SQLModel; raw `@dataclass` only for internal helpers  |

### FastAPI specifics

- Routers in `app/routers/<resource>.py`. One `APIRouter` per file, `tags=[<resource>]`.
- Routes are thin: validate → call service / single DB op → return Pydantic schema. No business logic in routes.
- Use the dependency aliases: `SessionDep`, `CurrentUser`, `ChannelMemberDep`. Add new ones to `dependencies.py`.
- Always pass `response_model=`.
- Pagination is **cursor-based**: `?before=<uuid>&limit=<int>`.
- Soft delete only — set `deleted_at`, never `DELETE FROM`.

### SQLModel / Alembic

- One table per file under `models/`, file name = singular snake_case noun.
- Every table has `id: uuid.UUID`, `created_at`, `updated_at` (if mutable).
- Use `Field(foreign_key=...)` with explicit `ondelete=` only where deletion semantics are obvious.
- Migrations are append-only. Never edit a merged revision.

### Tests

- `pytest-asyncio` with `asyncio_mode = "auto"`. Don't decorate.
- Use `factory-boy` factories. Don't inline construct ORM objects in tests.
- Mock external APIs with `respx`. No live HTTP in tests.
- Every route: happy path + 401/403 + validation error.

### Forbidden

- `print()` for logging
- Sync I/O in async code (`requests`, `time.sleep`, blocking DB drivers)
- Wildcard imports
- Editing a merged Alembic revision
- Inline raw SQL except in migrations

---

## Frontend (TypeScript / Next.js 15)

### Style

| Topic         | Rule                                                              |
| ------------- | ----------------------------------------------------------------- |
| Linter        | ESLint (`eslint-config-next` + `@typescript-eslint/recommended`)  |
| Formatter     | Prettier + `prettier-plugin-tailwindcss`                          |
| Type checker  | `tsc --noEmit`, **strict** mode                                   |
| Imports       | Path alias `@/` → `src/`. No deep relatives.                      |
| File names    | `PascalCase.tsx` for components, `useCamelCase.ts` for hooks      |
| Exports       | Named exports for components and hooks; `default` only for routes |
| `any`         | Forbidden without an inline `// reason:` comment                  |

### React patterns

- Server Components by default. `"use client"` only when needed.
- Hooks at top, derived values next, handlers last, JSX at the end.
- No `React.FC`; declare explicit `Props` interfaces.
- Data fetching: TanStack Query only. Never `useEffect(() => fetch(...))`.
- Optimistic mutations: `useMutation` with `onMutate` rollback.
- WebSocket: one connection per channel, owned by `WebSocketContext`. Components subscribe.

### Styling

- Tailwind v4 utility classes only.
- `cn()` from `lib/utils.ts` for conditional classes.
- shadcn primitives are generated; re-run `shadcn add` to update.
- No inline `style={{...}}` except dynamic values not expressible as classes.

### Tests

- Vitest + Testing Library + MSW.
- One test file per hook / component, colocated under `__tests__/`.
- Cover: rendering, primary interaction, error / empty states.

### Forbidden

- `window.fetch` outside `lib/api.ts`
- Importing from `app/*` into `components/*`
- Inline secrets (use `NEXT_PUBLIC_*` only for non-secret config)
- `useEffect` for data fetching

---

## Git

| Topic       | Rule                                                              |
| ----------- | ----------------------------------------------------------------- |
| Branches    | `feat/<ID>-<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`   |
| Commits     | `<type>(<ID>): <imperative one-liner>` — e.g. `feat(S2.3): MessageList virtualization` |
| Commit types| `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`, `perf`  |
| Squash?     | Maintainer squashes on merge unless history is meaningful         |
| Rebase?     | Always rebase your feature branch on `main` before opening PR     |
| Force push  | Allowed on your feature branches; never to `main`                 |

---

## Documentation

- Markdown only. No HTML in docs unless rendering on GitHub Pages.
- Wrap at 100 cols for prose; tables and code blocks may exceed.
- Mermaid for diagrams (renders inline on GitHub).
- Link by relative path: `[BACKLOG](BACKLOG.md)`, not absolute URLs.
- Code references use Markdown fenced blocks with language tags.
- Update doc + code in the same PR; out-of-date docs are a bug.

---

## Environment variables

- All new env vars go in `.env.example` with a one-line comment.
- Backend reads via `pydantic-settings` (`app/config.py`); type and default belong on the `Settings` class.
- Frontend reads via `process.env.NEXT_PUBLIC_*` (client) or `process.env.*` (server). Server-only vars never get the `NEXT_PUBLIC_` prefix.
- No defaults in code for production-sensitive values (`SECRET_KEY`, `OPENAI_API_KEY`). Fail loud on missing.
