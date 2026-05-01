# chat-engine

A production-grade real-time chat platform with WebSocket-based messaging, horizontal scaling via Redis Pub/Sub, and an AI layer for semantic search and RAG-powered assistant responses.

## Tech stack

- **Frontend** — Next.js 15 (App Router), TypeScript, PWA
- **Backend API** — FastAPI, Python
- **WebSocket gateway** — Python (stateless, horizontally scalable)
- **AI worker** — arq, OpenAI embeddings, RAG pipeline
- **Database** — PostgreSQL + pgvector
- **Cache / Pub-Sub** — Redis
- **Object storage** — Cloudflare R2 / S3
- **Observability** — OpenTelemetry, Prometheus, Grafana, Sentry
- **Infra** — Docker, GitHub Actions, Fly.io

## Architecture

> Coming soon.

## Local setup

```bash
# Install dependencies (see backend/ and frontend/ READMEs once added)
make dev     # start backend + frontend dev servers
make test    # run all tests
make lint    # lint all services
make build   # build all services
```

## Project structure

```
chat-engine/
├── backend/    # FastAPI HTTP API + WebSocket gateway + AI worker
├── frontend/   # Next.js 15 TypeScript app
└── infra/      # Docker, CI, deployment configs
```
