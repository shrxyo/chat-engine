/**
 * Tests for useWebSocket hook (reads WebSocketContext).
 */

import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useWebSocket } from '../useWebSocket'
import { WebSocketProvider } from '@/contexts/WebSocketContext'

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { accessToken: 'test-token', user: { id: 'user-1' } } }),
}))

describe('useWebSocket', () => {
  it('throws when used outside WebSocketProvider', () => {
    expect(() => {
      renderHook(() => useWebSocket())
    }).toThrow('useWebSocketContext must be used inside <WebSocketProvider>')
  })

  it('returns send and subscribe functions when inside provider', () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <WebSocketProvider channelId="ch-1">{children}</WebSocketProvider>
    )

    const { result } = renderHook(() => useWebSocket(), { wrapper })

    expect(typeof result.current.send).toBe('function')
    expect(typeof result.current.subscribe).toBe('function')
  })

  it('subscribe returns an unsubscribe function', () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <WebSocketProvider channelId="ch-1">{children}</WebSocketProvider>
    )

    const { result } = renderHook(() => useWebSocket(), { wrapper })
    const unsub = result.current.subscribe('message.new', () => {})
    expect(typeof unsub).toBe('function')
  })
})
