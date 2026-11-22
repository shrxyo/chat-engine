/**
 * Presence (S4.2): snapshot / join / leave handling and the 20s keepalive ping.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, renderHook } from '@testing-library/react'
import { PING_INTERVAL_MS, WebSocketProvider } from '@/contexts/WebSocketContext'
import { PresenceProvider, usePresence } from '@/contexts/PresenceContext'
import { installFakeSocket, lastSocket } from '@/test/fakeSocket'

// Stable reference, like next-auth's: a new object per render would make the
// provider reconnect on every render.
const session = { data: { accessToken: 'test-token', user: { id: 'user-1' } } }
vi.mock('next-auth/react', () => ({ useSession: () => session }))

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <WebSocketProvider channelId="ch-1">
    <PresenceProvider>{children}</PresenceProvider>
  </WebSocketProvider>
)

describe('presence', () => {
  let restoreSocket: () => void

  beforeEach(() => {
    vi.useFakeTimers()
    restoreSocket = installFakeSocket()
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    restoreSocket()
  })

  it('replaces the online set with presence.snapshot', () => {
    const { result } = renderHook(() => usePresence(), { wrapper })
    const ws = lastSocket()
    act(() => {
      ws.open()
      ws.receive('presence.join', { user_id: 'stale', channel_id: 'ch-1' })
      ws.receive('presence.snapshot', { channel_id: 'ch-1', online_user_ids: ['u1', 'u2'] })
    })

    expect(result.current.onlineCount).toBe(2)
    expect(result.current.isOnline('u1')).toBe(true)
    expect(result.current.isOnline('stale')).toBe(false)
  })

  it('applies join and leave after the snapshot', () => {
    const { result } = renderHook(() => usePresence(), { wrapper })
    const ws = lastSocket()
    act(() => {
      ws.open()
      ws.receive('presence.snapshot', { channel_id: 'ch-1', online_user_ids: ['u1'] })
      ws.receive('presence.join', { user_id: 'u2', channel_id: 'ch-1' })
      ws.receive('presence.join', { user_id: 'u2', channel_id: 'ch-1' })
      ws.receive('presence.leave', { user_id: 'u1', channel_id: 'ch-1' })
    })

    expect(result.current.onlineCount).toBe(1)
    expect(result.current.isOnline('u1')).toBe(false)
    expect(result.current.isOnline('u2')).toBe(true)
  })

  it('pings every 20s while the socket is open, and stops on close', () => {
    renderHook(() => usePresence(), { wrapper })
    const ws = lastSocket()
    act(() => ws.open())

    expect(PING_INTERVAL_MS).toBe(20_000)
    act(() => vi.advanceTimersByTime(PING_INTERVAL_MS - 1))
    expect(ws.sent).toEqual([])
    act(() => vi.advanceTimersByTime(1))
    expect(ws.sent).toEqual([{ type: 'ping', payload: {} }])
    act(() => vi.advanceTimersByTime(PING_INTERVAL_MS))
    expect(ws.sent).toHaveLength(2)

    act(() => ws.close())
    act(() => vi.advanceTimersByTime(PING_INTERVAL_MS * 2))
    expect(ws.sent).toHaveLength(2)
  })
})
