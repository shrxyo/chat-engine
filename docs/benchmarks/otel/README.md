# Cross-instance trace (S7.2, sprint T6)

`cross-instance-trace.png` shows one `message.new` from the Jaeger UI, captured 2026-11-21 with 3 backend replicas behind nginx and 6 sockets in one channel spread across them. `cross-instance-trace.json` is the same trace from the Jaeger API.

Replicas are told apart by `service.instance.id` (container hostname), visible in each span's Process tags:

| Span | Replica | Duration |
|------|---------|----------|
| `ws.message.new` (root, incl. `db.persist` 8.1ms) | `f96d52cf3f13` | 9.13ms |
| `pubsub.publish` | `f96d52cf3f13` | 0.66ms |
| `pubsub.deliver` | `b3f52d210a2d` | 0.72ms |
| `pubsub.deliver` | `f96d52cf3f13` | 0.64ms |
| `pubsub.deliver` | `b338c7826a87` | 0.69ms |

All 5 traced messages in that run covered all 3 replicas. Light load in dev mode with SQL echo on, so this is not a benchmark.
