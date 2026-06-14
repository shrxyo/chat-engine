# OPERATIONS — chat-engine

> Day-to-day operating manual for **human collaborators and AI agents**. Covers: how we divide work, claim it without colliding, ship it, review it, deploy it, and recover when things go wrong. Read this once at onboarding; reference per loop.

---

## 1. Mental model

This project is built **agent-first**, meaning every piece of context an AI coding agent needs is committed to the repo in a predictable place:

| Layer            | File                                                | Read frequency      |
| ---------------- | --------------------------------------------------- | ------------------- |
| Universal spec   | `AGENTS.md` (+ one per submodule)                   | Once per session    |
| Scoped rules     | `.cursor/rules/*.mdc` (auto-attached by file glob)  | Auto                |
| Backlog          | `docs/BACKLOG.md`                                   | Per task            |
| Live state       | `docs/PROGRESS.md`                                  | Every session start |
| Target arch      | `docs/ARCHITECTURE.md`                              | When designing      |
| Conventions      | `docs/CONVENTIONS.md`                               | Per language switch |
| Original brief   | `chat-plan.md`                                      | Rare; grep only     |

Two principles drive the whole operation:

1. **Token discipline.** Loading 110 KB of plan text into every agent prompt was costing the project money and degrading output. The compact backlog + scoped rules + `.cursorignore` keep per-prompt context lean.
2. **Decentralized coordination.** Many humans and agents work in parallel. Git's optimistic locking + a single `PROGRESS.md` file makes it impossible to double-book work or lose state across a context restart.

---

## 2. Roles

| Role                | Who                                       | Responsibilities                                                                 |
| ------------------- | ----------------------------------------- | -------------------------------------------------------------------------------- |
| **Maintainer**      | You (project owner)                       | Final approval on PRs, owns roadmap, edits BACKLOG, resolves disputes            |
| **Backend dev**     | Collaborators owning `backend/`           | Implement S1.x, S2.x, S3.x, S4.x (server side), S5.x, S6.x, S7.x, S8.x (server) |
| **Frontend dev**    | Collaborators owning `frontend/`          | Implement S1.3, S2.3–4, S3.1 (FE), S4.x (client), S8.x (UI), S9.x                 |
| **Infra/DevOps**    | Collaborator owning `infra/`              | Compose, Dockerfiles, CI, Fly.io, observability stack                            |
| **AI agent**        | Cursor / Claude Code with this repo open  | Implements one story at a time, scoped by `.cursor/rules/`                       |
| **Reviewer**        | Any maintainer or peer with merge rights  | Reviews PRs against the assigned story IDs                                       |

You can wear multiple hats — the convention exists so commits, PRs, and `PROGRESS.md` entries name the role acting at the time.

---

## 3. The daily loop (works for humans and agents)

```
┌─────────────────────────────────────────────────────────────────┐
│  1. ORIENT      git pull;   read PROGRESS.md;   check CI         │
│  2. CLAIM       pick top TODO in BACKLOG;   PROGRESS → IN_PROGRESS;  │
│                 push immediately so others see the claim         │
│  3. IMPLEMENT   TDD: failing test → impl → lint → typecheck → push  │
│  4. REVIEW      open PR;  request review;  apply feedback        │
│  5. DONE        merge;  PROGRESS → DONE;  delete branch          │
└─────────────────────────────────────────────────────────────────┘
```

### Step 1 — Orient

```bash
git fetch origin
git switch main && git pull --ff-only
rg "IN_PROGRESS" docs/PROGRESS.md      # what's currently claimed
gh pr list --state open                # open PRs and their state
```

If `PROGRESS.md` shows a `BLOCKED` task you can unblock, claim **that** first — unblocking others is highest leverage.

### Step 2 — Claim

The **next unclaimed** TODO in the topmost epic of `docs/BACKLOG.md` (in dependency order) is yours.

```bash
git switch -c feat/S3.1-github-oauth
# Edit docs/PROGRESS.md — set S3.1 to IN_PROGRESS with your handle and date
git add docs/PROGRESS.md
git commit -m "claim: S3.1"
git push -u origin feat/S3.1-github-oauth
```

**Optimistic locking.** If `git push` is rejected because someone pushed a claim moments earlier:

```bash
git pull --rebase origin main
# Re-read PROGRESS.md — the task you wanted is gone. Pick the next one.
```

This is the same pattern described in the AI Coding Agents research — the rebased push is your atomic commit on the claim.

### Step 3 — Implement (TDD)

The story description in `docs/BACKLOG.md` is intentionally compact. If you need fuller spec:

```bash
rg "STORY 3.1" chat-plan.md -A 40
```

Then loop:

1. **Write the failing test** in the appropriate `tests/` directory.
2. **Implement** the minimum to pass.
3. **Lint + typecheck** in the submodule you touched.
4. **Commit** with a conventional message: `feat(S3.1): add NextAuth GitHub provider`.
5. **Push often** so the working tree on `origin` is current — protects against laptop crashes and lets reviewers see incremental progress.

For multi-task stories: one task per commit, all commits on the same branch.

### Step 4 — Review

```bash
make test && make lint                 # green required
gh pr create --fill
```

**Review checklist** (the reviewer applies):

- [ ] PR title is `<type>(<ID>): <summary>` (e.g. `feat(S3.1): GitHub OAuth`)
- [ ] Only the assigned story IDs are touched (scope discipline)
- [ ] Tests added/updated, all green in CI
- [ ] `lint` + `typecheck` green
- [ ] `docs/PROGRESS.md` flips IDs to `DONE` in this PR
- [ ] If schema changed: Alembic migration is present and reviewed
- [ ] If architecture changed: `docs/ARCHITECTURE.md` updated
- [ ] No secrets, no `.env`, no large fixtures committed
- [ ] No `print()` / `console.log` / debug leftovers

Reviewers may request changes via PR comments. The PR author pushes follow-up commits to the same branch.

### Step 5 — Done

Maintainer merges (squash-merge unless the history is meaningful). `PROGRESS.md` is now the canonical record. The branch is deleted on merge.

---

## 4. Handling AI agents

### When kicking off an agent session

Give the agent **exactly** this opening prompt template (token-tight, no waste):

```
Read AGENTS.md, then docs/PROGRESS.md. Pick the next unclaimed TODO in
docs/BACKLOG.md from epic <N>. Follow the workflow in .cursor/rules/40-workflow.mdc.
You have permission to claim, branch, commit, and open the PR. Stop when the
PR is open. Do not modify any task outside the IDs you claim.
```

Optionally pre-assign:

```
Implement S3.1 only. Branch feat/S3.1-github-oauth. Open the PR when green.
```

### What agents do automatically

- Read `AGENTS.md` and `docs/PROGRESS.md`.
- Auto-attach the relevant `.cursor/rules/*.mdc` based on the files they edit.
- Skip `chat-plan.md`, lockfiles, and binaries (per `.cursorignore`).
- Update `PROGRESS.md` on claim, block, done.

### What you must do for an agent

- Confirm the agent **picked the intended story** before letting it implement (`Plan Mode` / `Ask Mode` exists for exactly this — don't skip).
- Review the PR like any human PR.
- If the agent stalls or hallucinates, halt the session and restart with a fresh context. `PROGRESS.md` makes restart lossless.

### Parallel agents

Multiple agents can run concurrently as long as each works on a **non-overlapping submodule or epic**. Safe pairings:

| Agent A      | Agent B           | Safe?              |
| ------------ | ----------------- | ------------------ |
| `backend/`   | `frontend/`       | Yes                |
| `S5.1` (worker) | `S2.3` (frontend) | Yes                |
| `S6.1` (refactor ConnectionManager) | anything that touches ws.py | **No — block one** |

The push-rejection mechanism is a safety net, not a coordination strategy. Avoid known overlap by reading `PROGRESS.md` before claiming.

---

## 5. Branch / commit / PR conventions

| Object   | Pattern                                                                 |
| -------- | ----------------------------------------------------------------------- |
| Branch   | `feat/<ID>-<slug>`, `fix/<short-slug>`, `chore/<short-slug>`, `docs/<short-slug>` |
| Commit   | `<type>(<ID>): <imperative one-liner>` (e.g. `feat(S2.3): wire MessageList to TanStack Query`) |
| PR title | Same format as the merge commit                                         |
| PR body  | Filled by `gh pr create --fill`; add a "Why" section if non-obvious     |

Conventional commit types we use: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`, `perf`.

---

## 6. Per-submodule maintenance cheatsheet

### `backend/`

```bash
cd backend
uv sync                               # install / refresh deps
make run                              # uvicorn :8000, hot reload
make migration name="add_<thing>"     # new Alembic revision
make migrate                          # apply migrations
make test                             # pytest with coverage
make lint typecheck                   # ruff + ruff format + pyright
uv run python scripts/seed.py         # seed dev data
```

**Owner duties**

- Keep `pyproject.toml` dependencies tight; new deps require justification in PR.
- Watch the coverage gate; if it slips below 70% the build fails (post-`S10.1`).
- Review every Alembic migration generated by `--autogenerate` — it routinely misses things.
- Schema changes require updates in `models/`, `schemas/`, `routers/`, tests, and (if cross-cutting) `docs/ARCHITECTURE.md`.

### `frontend/`

```bash
cd frontend
npm install
npm run dev                            # next dev :3000
npm test                               # vitest
npx playwright test                    # E2E
npm run lint
npx tsc --noEmit
npx shadcn@latest add <component>      # only way to add UI primitives
```

**Owner duties**

- Never hand-edit `components/ui/*`. Re-run `shadcn add` to upgrade.
- Watch bundle size on PRs (run `npm run build` locally if you touch a lot of dependencies).
- Keep TypeScript strict — `any` requires an inline justification comment.

### `infra/`

```bash
docker compose up -d                              # base services
docker compose --profile observability up -d      # + Prometheus/Grafana/OTel/Jaeger
docker compose up --scale backend=3               # multi-instance test (after S6.1)
docker compose down -v                            # nuke everything
k6 run infra/load-tests/websocket_flood.js        # post-S6.4
```

**Owner duties**

- Re-pin image tags quarterly. Never `:latest`.
- Treat `infra/postgres/init.sql` as bootstrap-only; everything else through Alembic.
- Keep CI wall time under 5 minutes; profile + split slow jobs.

---

## 7. CI / CD operations

| Event                  | What happens                                                                     |
| ---------------------- | -------------------------------------------------------------------------------- |
| Push any branch        | `backend-lint`, `backend-test`, `frontend-lint`, `frontend-test` run in parallel |
| Open / update a PR     | Above + `e2e` (Playwright) + `preview-deploy` to Fly                              |
| Merge to `main`        | Above + `build-images` (GHCR) + `deploy-fly` (production rolling deploy)         |
| Close PR (any state)   | `preview-destroy` removes the per-PR Fly app + database                          |

**If CI is red:**

- Open the failing job log; fix in a new commit on the PR branch.
- Don't bypass with `--no-verify`. Don't disable checks. If a check is genuinely broken, fix the check in a separate PR.

**If production is on fire:**

- Roll back: `flyctl releases list -a chat-engine-backend` → `flyctl releases rollback <prev>` (similarly for frontend / worker).
- Open an incident issue: title `INCIDENT: <one-liner>`, body covering symptoms, timeline, blast radius, mitigation. Close once a fix is merged with a postmortem section.

---

## 8. Releases & versioning

This is an academic / portfolio project; we don't cut numbered releases. We do:

- Tag the "v1.0 ship-ready" commit (end of `S12.x`) for the resume bullet.
- Keep `main` always deployable.
- Use changelog automation later if needed (`release-please`).

---

## 9. Secrets

- Never commit `.env`, `.env.local`, `.env.production`. `.gitignore` enforces this; review your `git status` before every commit.
- Prod secrets live in **Fly.io secrets** (`flyctl secrets set/list`). Each environment (preview / staging / prod) has its own set.
- Rotate the JWT `SECRET_KEY` quarterly and on any suspected leak. Rotation invalidates all sessions; communicate to users.
- API keys for OpenAI / Sentry are per-environment. Never share dev keys to prod.
- See `.env.example` for the canonical list of required environment variables.

---

## 10. Onboarding a new collaborator (15-minute checklist)

```bash
# 1. Clone and install
git clone <repo>; cd chat-engine
cp .env.example .env                  # fill in DEV values, ask maintainer for OAuth IDs
docker compose up -d postgres redis
make -C backend install
make -C frontend install

# 2. Verify
make test                             # backend + frontend tests green
make dev                              # backend :8000, frontend :3000

# 3. Read (in order)
#    - AGENTS.md (root)
#    - docs/PROGRESS.md
#    - docs/BACKLOG.md
#    - docs/OPERATIONS.md (this file)
#    - The submodule AGENTS.md you'll work in

# 4. First task
#    Claim a tiny task in PROGRESS.md to learn the loop. Suggested: a docs PR.
```

If anything in the install path doesn't work in a fresh checkout, **that's a bug** — file it as a `chore:` PR fixing the setup, not a workaround in your local environment.

---

## 11. Common operational problems

| Symptom                                                  | Cause                                                          | Fix                                                                 |
| -------------------------------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------- |
| `git push` rejected with "fetch first"                   | Someone pushed; usually a claim collision                      | `git pull --rebase`, re-check `PROGRESS.md`, retry                  |
| Alembic autogenerate produced an empty migration         | Model not imported in `alembic/env.py`'s metadata target       | Add the import; re-run autogenerate                                 |
| WebSocket closes with code 4001 immediately              | JWT missing / expired / not in `?token=` query param           | Verify NextAuth session has `accessToken`; re-sign in               |
| Postgres connection pool exhausted under load test       | Long-running queries holding sessions; pool too small          | Profile slow queries; raise pool max (post-`S6.5`); add async timeouts |
| Frontend hot reload broken after adding shadcn primitive | Generated file conflict                                        | `rm -rf .next`, restart `npm run dev`                               |
| AI agent edits files outside its task                   | Missing scope discipline; rule not auto-attached               | Cancel session; restart with explicit IDs only; add glob to `.cursor/rules/`. |
| Coverage drops below 70% after a feature                | Tests skipped or coverage gate ignored                         | Block merge; add tests; do not adjust the gate                       |

---

## 12. Living document

Update this file when:

- A new role joins.
- A workflow step changes (e.g. we adopt `gh-merge-queue`).
- A common operational problem keeps biting people — add it to section 11.

PRs touching `docs/OPERATIONS.md` carry the `docs/` branch prefix and don't require an ID. Maintainer review only.
