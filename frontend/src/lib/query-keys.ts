/**
 * Centralised TanStack Query key factories.
 * All cache keys are defined here to avoid collisions and enable targeted invalidation.
 */

export const queryKeys = {
  channels: {
    all: () => ['channels'] as const,
    detail: (id: string) => ['channels', id] as const,
    members: (id: string) => ['channels', id, 'members'] as const,
    messages: (id: string) => ['channels', id, 'messages'] as const,
  },
  users: {
    me: () => ['users', 'me'] as const,
    detail: (id: string) => ['users', id] as const,
  },
} as const
