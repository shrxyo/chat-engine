/**
 * Presence (S4.2): snapshot / join / leave handling and the 20s keepalive ping.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, renderHook } from '@testing-library/react'
import { PING_INTERVAL_MS, WebSocketProvider } from '@/contexts/WebSocketContext'
import { PresenceProvider, usePresence } from '@/contexts/PresenceContext'

// Stable reference, like next-auth's: a new object per render would make the
// provider reconnect on every render.
const session = { data: { accessToken: 'test-token', user: { id: 'user-1' } } }
vi.mock('next-auth/react', () => ({ useSession: () => session }))

class FakeSocket {
  static OPEN = 1
  static instances: FakeSocket[] = []

  readyState = 0
  sent: unknown[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor(public url: string) {
    FakeSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(JSON.parse(data))
  }

  close() {
    this.readyState = 3
    this.onclose?.()
  }

  open() {
    this.readyState = FakeSocket.OPEN
    this.onopen?.()
  }

  receive(type: string, payload: unknown) {
    this.onmessage?.({ data: JSON.stringify({ type, payload }) })
  }
}

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <WebSocketProvider channelId="ch-1">
    <PresenceProvider>{children}</PresenceProvider>
  </WebSocketProvider>
)

function lastSocket(): FakeSocket {
  const ws = FakeSocket.instances.at(-1)
  if (!ws) throw new Error('no socket opened')
  return ws
}

describe('presence', () => {
  const originalWebSocket = globalThis.WebSocket

  beforeEach(() => {
    vi.useFakeTimers()
    FakeSocket.instances = []
    globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    globalThis.WebSocket = originalWebSocket
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
