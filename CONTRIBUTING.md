# Contributing to chat-engine

Thanks for taking the time to read this. This project is built **agent-first**, which means humans and AI agents share the same workflow. The rules below apply to everyone.

## TL;DR

1. Read `AGENTS.md` (root) + the submodule `AGENTS.md` for the area you'll touch.
2. Check `docs/PROGRESS.md`. Pick an unclaimed TODO from `docs/BACKLOG.md`.
3. Branch `feat/<ID>-<slug>`. Mark the ID `IN_PROGRESS` in `PROGRESS.md`. Push.
4. TDD. Lint + typecheck + tests must be green.
5. Open a PR titled `<type>(<ID>): <summary>`.
6. Reviewer merges. You mark the ID `DONE` in `PROGRESS.md` as part of the PR.

The full operational manual lives in [`docs/OPERATIONS.md`](docs/OPERATIONS.md). Read it once at onboarding.

## Setup

```bash
git clone <repo>; cd chat-engine
cp .env.example .env
docker compose up -d postgres redis
make -C backend install
make -C frontend install
make test        # everything green = ready
make dev         # backend :8000, frontend :3000
```

If a fresh clone doesn't pass `make test`, that's a bug — file it as a `chore:` PR fixing setup, not a workaround in your local env.

## What we're building

Realtime chat platform with WebSockets, semantic search via pgvector, and an AI assistant via RAG. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the target system and [`docs/BACKLOG.md`](docs/BACKLOG.md) for the full feature list keyed by ID (`S<epic>.<story>`).

## Code style

- See [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md). The `.cursor/rules/*.mdc` rules and the linters enforce most of it automatically.
- Backend: `ruff check && ruff format && pyright`.
- Frontend: `eslint && prettier --check && tsc --noEmit`.

## Tests

- Backend: `pytest` with `factory-boy` fixtures from `backend/tests/`. Run `make -C backend test`.
- Frontend: `vitest` + Testing Library + MSW. Run `npm test --prefix frontend`.
- E2E: Playwright. Run `npx playwright test` from `frontend/`.
- New code requires tests. Coverage gate is **70%** post-`S10.1`.

## Pull requests

- Title: `<type>(<ID>): <summary>` (e.g. `feat(S2.3): MessageList virtualization`).
- One story per PR unless explicitly bundled in the backlog.
- The PR must touch `docs/PROGRESS.md` flipping the IDs to `DONE`.
- CI must be green before requesting review.
- Reviewers check against the [PR review checklist](docs/OPERATIONS.md#4--review).

## AI agents

If you are running an AI coding agent against this repo:

- The agent must read `AGENTS.md` and `docs/PROGRESS.md` first. The `.cursor/rules/` directory configures Cursor to do this automatically.
- Constrain the agent to specific story IDs. Don't say "build the chat app" — say "implement S2.3 only".
- Verify the agent's plan before letting it write code (Plan Mode / Ask Mode).
- The agent should follow the workflow in `.cursor/rules/40-workflow.mdc` end-to-end (claim → TDD → push → PR).
- Review the agent's PR like a human's. Trust but verify.

## Adding new features that aren't in the backlog

1. Open a `discussion` or `chore:` PR proposing the addition to `docs/BACKLOG.md` with a new ID.
2. Maintainer reviews and merges the backlog entry first.
3. Then you claim and implement it normally.

This keeps the backlog the single source of truth for "what does this project do".

## Security

- Never commit `.env` files, OAuth secrets, or API keys. `.gitignore` enforces this.
- If you find a security issue, email the maintainer privately — don't open a public issue.

## License

MIT. See [`LICENSE`](LICENSE).
