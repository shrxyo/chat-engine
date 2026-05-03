# Realtime chat platform — project overview

## Summary

This is a full-stack, production-grade real-time chat platform. The core system handles real-time messaging via WebSockets with sub-100ms latency, and is designed to scale horizontally across multiple gateway instances using Redis Pub/Sub as a fanout backbone. The tech stack spans Go or Python for the WebSocket gateway, FastAPI for the HTTP API, Next.js 15 (App Router) with TypeScript for the frontend, PostgreSQL with pgvector for persistent storage and semantic search, and Redis for pub/sub, presence tracking, and caching.

What sets the project apart from typical chat demos is its AI layer and observability story. Every message is asynchronously embedded using OpenAI's embedding API and stored as a vector in PostgreSQL, enabling semantic search (via a `Cmd+K` command palette) and a RAG pipeline for an `@assistant` bot that retrieves relevant message history before generating streaming responses. A separate worker service (built with `arq`) handles all async AI jobs — embeddings, thread summarization, and daily digest generation — keeping the main API fast and non-blocking.

The project is structured across 12 epics and ~45 stories. 

---

## Architecture diagram 1 — Request and gateway layer

This diagram shows how traffic flows from the browser through the load balancer to the WebSocket gateways, and how the AI worker plugs into that layer via Redis Pub/Sub.

```
┌─────────────────────────────────────────────┐
│              Browser client                 │
│       Next.js 15 · TypeScript · PWA         │
└──────────────┬──────────────────┬───────────┘
         HTTPS │                  │ WebSocket
               ▼                  ▼
┌─────────────────────────────────────────────┐
│              Load balancer                  │
│     nginx · round-robin · no sticky         │
└───────┬──────────────┬──────────────┬───────┘
        │              │              │
        ▼              ▼              ▼
┌────────────┐  ┌────────────┐  ┌────────────┐    ┌──────────────────┐
│ Gateway 1  │  │ Gateway 2  │  │ Gateway 3  │    │ FastAPI HTTP API  │
│ Go/Python  │  │ Go/Python  │  │ Go/Python  │    │ REST · auth ·    │
└─────┬──────┘  └─────┬──────┘  └─────┬──────┘    │ rate limits      │
      │               │               │            └────────┬─────────┘
      │    ┌──────────┴───────────┐   │                     │ enqueues jobs
      └────►    Redis Pub/Sub     ◄───┘            ┌────────▼─────────┐
           │ Fan-out across all   │                │    AI worker     │
           │ gateway instances    │◄───────────────│ arq · embeddings │
           └──────────────────────┘  streams resp  │ · RAG · digest   │
                                                   └──────────────────┘
```

### Key design decision — stateless gateways

Each gateway subscribes to Redis Pub/Sub topics for its active channels. A message arriving at Gateway 1 is published to Redis and immediately fanned out to clients on Gateways 2 and 3. This means gateways carry **no shared state** — any gateway can serve any user, enabling true horizontal scaling with round-robin load balancing and no sticky sessions.

---

## Architecture diagram 2 — Data and observability layer

This diagram shows what the API and AI worker read from and write to, plus the observability pipeline that instruments every service.

```
┌──────────────────────┐          ┌──────────────────────┐
│   FastAPI HTTP API   │          │      AI worker        │
│  reads · writes ·    │          │ reads messages ·      │
│  caches              │          │ writes vectors        │
└──┬───────────┬───────┘          └──────┬────────────────┘
   │           │                         │
   │           └──────────┬──────────────┘
   │                      │
   ▼                      ▼
┌──────────────┐  ┌───────────────────────┐  ┌────────────────────┐
│    Redis     │  │  PostgreSQL + pgvector │  │  Object storage    │
│ Cache ·      │  │ Messages · users ·     │  │  Cloudflare R2/S3  │
│ presence TTL │  │ channels · vector      │  │  presigned uploads │
│ rate limiting│  │ embeddings             │  │                    │
└──────────────┘  └───────────────────────┘  └────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                        Observability                           │
│                                                                │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐       │
│  │ OTel         │──►│ Prometheus   │──►│ Grafana      │       │
│  │ collector    │   │ scrapes      │   │ dashboards · │       │
│  │ traces·spans │   │ /metrics     │   │ SLOs         │       │
│  └──────────────┘   └──────────────┘   └──────────────┘       │
│                                                                │
│  ┌──────────────┐                                              │
│  │ Sentry       │  (frontend + backend error tracking)        │
│  │ errors·alerts│                                              │
│  └──────────────┘                                              │
└────────────────────────────────────────────────────────────────┘
```

### Storage responsibilities

| Store                      | What lives there                                                                                                                 |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Redis**                  | Pub/Sub channel topics, presence TTL keys, rate limit counters, hot read cache                                                   |
| **PostgreSQL + pgvector**  | All persistent data: users, channels, messages, reactions, memberships, and the `embedding vector(1536)` column on every message |
| **Object storage (R2/S3)** | File attachments uploaded via presigned PUT URLs — file data never routes through the API server                                 |

### Observability pipeline

Every service (gateways, API, AI worker) emits traces to the OTel collector, which fans them to Prometheus (metrics) and Jaeger/Tempo (traces). Grafana dashboards surface active connection counts, P99 message latency, embedding queue depth, and error rates. Sentry captures unhandled exceptions on both frontend and backend with full user and channel context.
