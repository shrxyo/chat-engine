/**
 * Reconnect gap fill (S4.3): after a reconnect, fetch messages after the
 * newest one we have, merge + dedupe; a gap over 200 reloads from scratch.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { WebSocketProvider } from '@/contexts/WebSocketContext'
import { GAP_FILL_LIMIT, mergeGapIntoPage, useMessages } from '../useMessages'
import { api, ApiError } from '@/lib/api'
import { installFakeSocket, lastSocket } from '@/test/fakeSocket'
import type { Message, MessageListResponse } from '@/types'

const session = { data: { accessToken: 'test-token', user: { id: 'user-1', name: 'Alice' } } }
vi.mock('next-auth/react', () => ({ useSession: () => session }))

vi.mock('@/lib/api', () => {
  class ApiError extends Error {
    constructor(
      public readonly status: number,
      message: string,
    ) {
      super(message)
    }
  }
  return { ApiError, api: { messages: { list: vi.fn(), listAfter: vi.fn() } } }
})

const list = vi.mocked(api.messages.list)
const listAfter = vi.mocked(api.messages.listAfter)

function msg(n: number, overrides: Partial<Message> = {}): Message {
  return {
    id: `m${n}`,
    channel_id: 'ch-1',
    user_id: 'user-2',
    content: `msg ${n}`,
    reply_to_id: null,
    edited_at: null,
    created_at: `2026-01-01T12:00:${String(n).padStart(2, '0')}`,
    ...overrides,
  }
}

/** API pages are newest-first. */
function page(ns: number[], has_more = false): MessageListResponse {
  return { messages: ns.map((n) => msg(n)).reverse(), has_more }
}

function wsNew(m: Message) {
  lastSocket().receive('message.new', m)
}

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <WebSocketProvider channelId="ch-1">{children}</WebSocketProvider>
    </QueryClientProvider>
  )
  return renderHook(() => useMessages('ch-1'), { wrapper })
}

async function reconnect() {
  act(() => lastSocket().close())
  await act(async () => {
    vi.advanceTimersByTime(1500)
  })
  act(() => lastSocket().open())
}

const ids = (messages: Message[]) => messages.map((m) => m.id)

describe('mergeGapIntoPage', () => {
  it('dedupes by id, sorts confirmed newest-first, keeps pending in front', () => {
    const pending = { ...msg(99, { id: 'tmp' }), pending: true }
    const merged = mergeGapIntoPage(
      [pending, msg(5), msg(2)],
      [msg(5), msg(4), msg(3)],
    )
    expect(ids(merged)).toEqual(['tmp', 'm5', 'm4', 'm3', 'm2'])
  })

  it('breaks created_at ties by id like the server', () => {
    const t = '2026-01-01T12:00:00'
    const merged = mergeGapIntoPage(
      [msg(1, { id: 'b', created_at: t })],
      [msg(2, { id: 'c', created_at: t }), msg(3, { id: 'a', created_at: t })],
    )
    expect(ids(merged)).toEqual(['c', 'b', 'a'])
  })
})

describe('useMessages gap fill', () => {
  let restoreSocket: () => void

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
    restoreSocket = installFakeSocket()
    list.mockReset().mockResolvedValue(page([1, 2, 3]))
    listAfter.mockReset().mockResolvedValue(page([]))
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.restoreAllMocks()
    restoreSocket()
  })

  it('does not gap-fill on the first connect', async () => {
    const { result } = setup()
    act(() => lastSocket().open())
    await waitFor(() => expect(result.current.messages).toHaveLength(3))
    expect(listAfter).not.toHaveBeenCalled()
  })

  it('on reconnect fetches after the newest confirmed message and merges', async () => {
    const { result } = setup()
    act(() => lastSocket().open())
    await waitFor(() => expect(result.current.messages).toHaveLength(3))
    act(() => wsNew(msg(4)))

    const gap = deferred<MessageListResponse>()
    listAfter.mockReturnValueOnce(gap.promise)
    await reconnect()

    expect(listAfter).toHaveBeenCalledWith('ch-1', 'm4', GAP_FILL_LIMIT, 'test-token')
    expect(result.current.isCatchingUp).toBe(true)

    // A live message on the new socket lands before the gap response.
    act(() => wsNew(msg(8)))
    await act(async () => gap.resolve(page([5, 6, 7, 8])))

    await waitFor(() => expect(result.current.isCatchingUp).toBe(false))
    expect(ids(result.current.messages)).toEqual(['m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8'])
    expect(list).toHaveBeenCalledTimes(1)
  })

  it('reconciles our own pending message delivered during the gap', async () => {
    const { result } = setup()
    act(() => lastSocket().open())
    await waitFor(() => expect(result.current.messages).toHaveLength(3))

    act(() => result.current.sendMessage('sent just before the drop'))
    listAfter.mockResolvedValueOnce({
      messages: [msg(4, { user_id: 'user-1', content: 'sent just before the drop' })],
      has_more: false,
    })
    await reconnect()

    await waitFor(() => expect(result.current.messages.at(-1)?.id).toBe('m4'))
    expect(result.current.messages.some((m) => m.pending)).toBe(false)
  })

  it('a gap over the limit reloads the newest page instead of merging', async () => {
    const { result } = setup()
    act(() => lastSocket().open())
    await waitFor(() => expect(result.current.messages).toHaveLength(3))

    listAfter.mockResolvedValueOnce(page([4, 5], true))
    list.mockResolvedValueOnce(page([50, 51, 52], true))
    await reconnect()

    await waitFor(() => expect(ids(result.current.messages)).toEqual(['m50', 'm51', 'm52']))
    expect(list).toHaveBeenCalledTimes(2)
    expect(list).toHaveBeenLastCalledWith('ch-1', null, 'test-token')
    expect(result.current.isCatchingUp).toBe(false)
  })

  it('an unknown cursor (400) reloads too', async () => {
    const { result } = setup()
    act(() => lastSocket().open())
    await waitFor(() => expect(result.current.messages).toHaveLength(3))

    listAfter.mockRejectedValueOnce(new ApiError(400, 'bad cursor'))
    list.mockResolvedValueOnce(page([9]))
    await reconnect()

    await waitFor(() => expect(ids(result.current.messages)).toEqual(['m9']))
  })

  it('an empty channel just refetches', async () => {
    list.mockResolvedValue(page([]))
    const { result } = setup()
    act(() => lastSocket().open())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    list.mockResolvedValueOnce(page([1]))
    await reconnect()

    await waitFor(() => expect(ids(result.current.messages)).toEqual(['m1']))
    expect(listAfter).not.toHaveBeenCalled()
  })
})
