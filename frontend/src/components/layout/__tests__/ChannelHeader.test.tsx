/**
 * ChannelHeader shows how many members are online (S4.2).
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChannelHeader } from '../ChannelHeader'
import { WebSocketProvider } from '@/contexts/WebSocketContext'
import { PresenceProvider } from '@/contexts/PresenceContext'

const session = { data: { accessToken: 'test-token', user: { id: 'u1' } } }
vi.mock('next-auth/react', () => ({ useSession: () => session }))

vi.mock('@/lib/api', () => ({
  api: {
    channels: {
      detail: vi.fn(() =>
        Promise.resolve({
          id: 'ch-1',
          name: 'general',
          description: null,
          is_dm: false,
          members: [],
        }),
      ),
    },
    users: { me: vi.fn(() => Promise.resolve({ id: 'u1', name: 'Alice' })) },
  },
}))

type Listener = (e: { data: string }) => void
const sockets: { onmessage: Listener | null }[] = []
class FakeSocket {
  static OPEN = 1
  readyState = 1
  onopen: (() => void) | null = null
  onmessage: Listener | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor() {
    sockets.push(this)
  }
  send() {}
  close() {}
}

function renderHeader() {
  globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <WebSocketProvider channelId="ch-1">
        <PresenceProvider>
          <ChannelHeader channelId="ch-1" />
        </PresenceProvider>
      </WebSocketProvider>
    </QueryClientProvider>,
  )
}

function serverSends(type: string, payload: unknown) {
  act(() => sockets.at(-1)?.onmessage?.({ data: JSON.stringify({ type, payload }) }))
}

describe('ChannelHeader online count', () => {
  const originalWebSocket = globalThis.WebSocket
  afterEach(() => {
    cleanup()
    globalThis.WebSocket = originalWebSocket
  })

  it('shows the number of online members and follows join/leave', async () => {
    renderHeader()
    expect(await screen.findByText('general')).toBeTruthy()

    serverSends('presence.snapshot', { channel_id: 'ch-1', online_user_ids: ['u1', 'u2'] })
    expect(screen.getByText('2 online')).toBeTruthy()

    serverSends('presence.join', { user_id: 'u3', channel_id: 'ch-1' })
    expect(screen.getByText('3 online')).toBeTruthy()

    serverSends('presence.leave', { user_id: 'u2', channel_id: 'ch-1' })
    expect(screen.getByText('2 online')).toBeTruthy()
  })
})
