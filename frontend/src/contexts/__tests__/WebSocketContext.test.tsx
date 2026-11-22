/**
 * Connection status + reconnect signal (S4.3).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, renderHook } from '@testing-library/react'
import { useWebSocket } from '@/hooks/useWebSocket'
import { WebSocketProvider } from '@/contexts/WebSocketContext'
import { FakeSocket, installFakeSocket, lastSocket } from '@/test/fakeSocket'

const session = { data: { accessToken: 'test-token', user: { id: 'user-1' } } }
vi.mock('next-auth/react', () => ({ useSession: () => session }))

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <WebSocketProvider channelId="ch-1">{children}</WebSocketProvider>
)

describe('WebSocketProvider status', () => {
  let restoreSocket: () => void

  beforeEach(() => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0.5) // no jitter
    restoreSocket = installFakeSocket()
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.restoreAllMocks()
    restoreSocket()
  })

  it('is connecting until the first open, then open with no reconnects', () => {
    const { result } = renderHook(() => useWebSocket(), { wrapper })
    expect(result.current.status).toBe('connecting')
    expect(result.current.isConnected).toBe(false)

    act(() => lastSocket().open())
    expect(result.current.status).toBe('open')
    expect(result.current.isConnected).toBe(true)
    expect(result.current.reconnectCount).toBe(0)
  })

  it('a failed first attempt is still connecting, not reconnecting', () => {
    const { result } = renderHook(() => useWebSocket(), { wrapper })
    act(() => lastSocket().close())
    expect(result.current.status).toBe('connecting')

    act(() => vi.advanceTimersByTime(1000))
    act(() => lastSocket().open())
    expect(result.current.reconnectCount).toBe(0)
  })

  it('drop → reconnecting; next open bumps reconnectCount', () => {
    const { result } = renderHook(() => useWebSocket(), { wrapper })
    act(() => lastSocket().open())

    act(() => lastSocket().close())
    expect(result.current.status).toBe('reconnecting')
    expect(result.current.isConnected).toBe(false)

    // Backoff 1s, then 2s after a failed retry.
    act(() => vi.advanceTimersByTime(1000))
    expect(FakeSocket.instances).toHaveLength(2)
    act(() => lastSocket().close())
    expect(result.current.status).toBe('reconnecting')
    act(() => vi.advanceTimersByTime(1999))
    expect(FakeSocket.instances).toHaveLength(2)
    act(() => vi.advanceTimersByTime(1))
    act(() => lastSocket().open())

    expect(result.current.status).toBe('open')
    expect(result.current.reconnectCount).toBe(1)

    act(() => lastSocket().close())
    act(() => vi.advanceTimersByTime(1000))
    act(() => lastSocket().open())
    expect(result.current.reconnectCount).toBe(2)
  })
})
