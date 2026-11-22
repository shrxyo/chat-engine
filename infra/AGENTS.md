# AGENTS.md — infra/

> Scope: Docker, CI, observability stack, load tests, deployment. Read root `AGENTS.md` first.

## Layout

```
infra/
├── nginx/
│   └── nginx.conf             # LB: round-robin over backend replicas, WS upgrade
├── postgres/
│   └── init.sql               # pgvector + schema bootstrap
├── grafana/
│   ├── dashboards/            # dashboard JSON (provisioned)
│   └── provisioning/          # datasources, dashboard providers
├── prometheus/
│   └── prometheus.yml         # scrape targets
├── otel/
│   └── collector-config.yaml  # OTLP collector
├── load-tests/                # k6 scripts
└── fly/                       # fly.toml per service (when Epic 11 lands)
```

> Dockerfiles live next to their service code: `backend/Dockerfile`, `frontend/Dockerfile`. Multi-stage builds, non-root runtime users. A future `gateway/Dockerfile` and `worker/Dockerfile` will follow the same convention.

## Commands

| Action                              | Command                                                |
| ----------------------------------- | ------------------------------------------------------ |
| **Full stack (recommended)**        | `docker compose up`                                    |
| Infra only (postgres + redis)       | `docker compose up -d postgres redis`                  |
| Full stack with observability       | `docker compose --profile observability up`            |
| Scale backend replicas              | `docker compose up --scale backend=3` (nginx picks up new replicas via DNS; no restart) |
| Stop all                            | `docker compose down`                                  |
| Stop and remove volumes             | `docker compose down -v`                               |
| Rebuild images after code change    | `docker compose build`                                 |
| Load test                           | `make load-test VUS=200` (k6 in Docker; see `infra/load-tests/compose.loadtest.yml`) |

## Architectural constraints

- **One service per Dockerfile**, multi-stage build, non-root user.
- **No application code in `infra/`.** Configuration only.
- **Health checks** on every service. Compose gates startup order via `depends_on: condition: service_healthy`.
- **Secrets** never in `docker-compose.yml`. Use `.env` (git-ignored) + `env_file:` directive.
- **Ports** are project-pinned: Postgres 5433, Redis 6379, Backend 8000 (nginx → replicas; backends have no host port), Frontend 3000, Prometheus 9090, Grafana 3001, OTel collector 4317.
- **Migrations** run once per `docker compose up` in the one-shot `migrate` service; `backend` waits for it (`service_completed_successfully`) and starts with `RUN_MIGRATIONS=false` so scaled replicas never race on DDL. Outside compose, `backend/docker-entrypoint.sh` still migrates by default. In production they will move to a one-shot `release_command`.

## CI/CD

GitHub Actions live in `.github/workflows/`. Jobs in parallel:

| Job              | Trigger      | Owner       |
| ---------------- | ------------ | ----------- |
| `backend-lint`   | every push   | backend team|
| `backend-test`   | every push   | backend team|
| `frontend-lint`  | every push   | frontend team|
| `frontend-test` | every push   | frontend team|
| `e2e`            | every PR     | both teams  |
| `build-images`   | merge `main` | infra       |
| `deploy-fly`     | merge `main` | infra       |
| `preview-deploy` | every PR     | infra       |

A red CI is a blocker. Don't merge with red.

## Forbidden

- Editing `infra/postgres/init.sql` after first migration ships — use Alembic.
- Hardcoded image tags (`latest`). Always pin (`pg16`, `redis:7-alpine`, etc.).
- Long-running containers in CI without timeouts.
