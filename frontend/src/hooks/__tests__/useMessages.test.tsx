/**
 * Tests for useMessages hook.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { WebSocketProvider } from '@/contexts/WebSocketContext'
import { useMessages, flattenMessages } from '../useMessages'
import type { MessageListResponse } from '@/types'
import type { InfiniteData } from '@tanstack/react-query'

vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: { accessToken: 'test-token', user: { id: 'user-1', name: 'Alice' } },
  }),
}))

vi.mock('@/lib/api', () => ({
  api: {
    messages: {
      list: vi.fn(
        (): Promise<MessageListResponse> =>
          Promise.resolve({
            messages: [
              {
                id: 'msg-1',
                channel_id: 'ch-1',
                user_id: 'user-2',
                content: 'Hello',
                reply_to_id: null,
                edited_at: null,
                created_at: '2024-01-01T12:00:00Z',
              },
            ],
            has_more: false,
          }),
      ),
    },
  },
}))

function createWrapper(channelId: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider channelId={channelId}>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
  }
}

describe('flattenMessages', () => {
  it('returns empty array for undefined data', () => {
    expect(flattenMessages(undefined)).toEqual([])
  })

  it('reverses pages and messages to get chronological order', () => {
    const data: InfiniteData<MessageListResponse, string | null> = {
      pages: [
        {
          messages: [
            {
              id: 'b',
              channel_id: 'c',
              user_id: 'u',
              content: 'B',
              reply_to_id: null,
              edited_at: null,
              created_at: '2024-01-01T12:01:00Z',
            },
            {
              id: 'a',
              channel_id: 'c',
              user_id: 'u',
              content: 'A',
              reply_to_id: null,
              edited_at: null,
              created_at: '2024-01-01T12:00:00Z',
            },
          ],
          has_more: false,
        },
      ],
      pageParams: [null],
    }
    const result = flattenMessages(data)
    expect(result.map((m) => m.id)).toEqual(['a', 'b'])
  })
})

describe('useMessages', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loads messages from the API', async () => {
    const { result } = renderHook(() => useMessages('ch-1'), {
      wrapper: createWrapper('ch-1'),
    })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.messages).toHaveLength(1)
    expect(result.current.messages[0].content).toBe('Hello')
  })

  it('sendMessage adds a pending message optimistically', async () => {
    const { result } = renderHook(() => useMessages('ch-1'), {
      wrapper: createWrapper('ch-1'),
    })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      result.current.sendMessage('Hi there')
    })

    await waitFor(() => {
      const pending = result.current.messages.find((m) => m.pending)
      expect(pending).toBeDefined()
      expect(pending?.content).toBe('Hi there')
    })
  })
})
