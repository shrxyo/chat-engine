# AGENTS.md — frontend/

> Scope: Next.js 15 App Router, TypeScript strict, Tailwind v4, shadcn/ui. Read root `AGENTS.md` first.

## Layout

```
frontend/
├── src/
│   ├── app/             # Next.js App Router (route per directory)
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   ├── auth/signin/
│   │   └── channels/[channelId]/
│   ├── components/
│   │   ├── ui/          # shadcn primitives — DO NOT hand-edit; use `shadcn add`
│   │   ├── layout/      # ChannelSidebar, MembersPanel, ChannelHeader
│   │   ├── messages/    # MessageList, Message, MessageInput, TypingIndicator
│   │   └── search/      # SearchModal (Cmd+K)
│   ├── hooks/           # useWebSocket, useMessages, useTypingIndicator
│   ├── contexts/        # WebSocketContext, PresenceContext
│   └── lib/             # utils (`cn`), api client, query keys
└── public/              # static assets, manifest.json (Epic 9)
```

## Commands

| Action          | Command                              |
| --------------- | ------------------------------------ |
| Install         | `npm install`                        |
| Dev server      | `npm run dev`     (port 3000)        |
| Build           | `npm run build`                      |
| Tests           | `npm test`        (vitest)           |
| E2E             | `npx playwright test`                |
| Lint            | `npm run lint`    (eslint + prettier)|
| Type check      | `npx tsc --noEmit`                   |
| Add shadcn comp | `npx shadcn@latest add <name>`       |

Run from `frontend/`.

## Architectural constraints

- **TypeScript strict.** No `any` without justification. Use `unknown` + narrow.
- **Server vs client components.** Default to server. Add `"use client"` only when you need state, effects, or browser APIs.
- **Data flow.**
  - **Reads** → TanStack Query (`useQuery`, `useInfiniteQuery`). Cache key in `lib/query-keys.ts`.
  - **Writes** → REST POST or WebSocket `send()`, with optimistic update via `queryClient.setQueryData`.
  - **Local UI state** → `useState` or Zustand store (`src/stores/`).
- **WebSocket.** Exactly one connection per channel, owned by `WebSocketContext`. Components subscribe via `useWebSocket().subscribe(type, handler)`.
- **Auth.** `next-auth` session everywhere; backend JWT from `session.accessToken` is passed in `Authorization: Bearer` for REST and `?token=` for WS.
- **shadcn primitives** live under `components/ui/`. Compose them; never reach into their internals.
- **No inline styles.** Tailwind classes only. Use `cn()` from `lib/utils.ts`.
- **Accessibility.** All interactive elements keyboard-navigable. Use shadcn primitives — they're a11y-correct by default.

## Forbidden patterns

- `useEffect(() => fetch(...), [])` — use TanStack Query.
- `window.fetch` outside `lib/api.ts` — keep API surface in one place.
- Importing from `src/app/*` into `src/components/*` — components must be route-agnostic.
- Inlining secrets / API keys. Read from `process.env.NEXT_PUBLIC_*` only.

## Adding a feature (template)

1. Read the story in `docs/BACKLOG.md` (e.g. `S2.3`).
2. If new shadcn primitive needed: `npx shadcn@latest add <name>`.
3. Add hook in `src/hooks/` (logic) + component in `src/components/` (presentation).
4. Wire into a route under `src/app/`.
5. Add vitest test for the hook (mock WS or API via MSW).
6. `npm run lint && npx tsc --noEmit && npm test`.
7. Mark IDs `DONE` in `docs/PROGRESS.md`.
