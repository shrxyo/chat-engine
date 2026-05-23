# AGENTS.md — infra/

> Scope: Docker, CI, observability stack, load tests, deployment. Read root `AGENTS.md` first.

## Layout

```
infra/
├── postgres/
│   └── init.sql               # pgvector + schema bootstrap
├── docker/                    # Dockerfiles (backend, worker, frontend, gateway)
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

## Commands

| Action                       | Command                                       |
| ---------------------------- | --------------------------------------------- |
| Bring up infra services      | `docker compose up -d postgres redis`         |
| Full stack (with observ.)    | `docker compose --profile observability up`   |
| Scale gateways               | `docker compose up --scale backend=3`         |
| Stop                         | `docker compose down`                         |
| Reset volumes                | `docker compose down -v`                      |
| Load test                    | `k6 run infra/load-tests/websocket_flood.js`  |

## Architectural constraints

- **One service per Dockerfile**, multi-stage build, non-root user.
- **No application code in `infra/`.** Configuration only.
- **Health checks** on every service. Compose gates startup order via `depends_on: condition: service_healthy`.
- **Secrets** never in `docker-compose.yml`. Use `.env` (git-ignored) + `env_file:` directive.
- **Ports** are project-pinned: Postgres 5433, Redis 6379, Backend 8000, Frontend 3000, Prometheus 9090, Grafana 3001, OTel collector 4317.
- **Migrations** run as a one-shot `release_command` in production, not on every container start.

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
