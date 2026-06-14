'use client'

/**
 * Client wrapper that reads the active channelId from the URL,
 * instantiates the per-channel WebSocket + Presence providers,
 * and renders the three-column shell (main + members panel).
 */

import { useParams } from 'next/navigation'
import { WebSocketProvider } from '@/contexts/WebSocketContext'
import { PresenceProvider } from '@/contexts/PresenceContext'
import { MembersPanel } from './MembersPanel'

interface ChannelShellProps {
  children: React.ReactNode
}

export function ChannelShell({ children }: ChannelShellProps) {
  const params = useParams()
  const channelId = typeof params?.channelId === 'string' ? params.channelId : undefined

  if (!channelId) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground">
        Select a channel to start chatting.
      </div>
    )
  }

  return (
    <WebSocketProvider channelId={channelId}>
      <PresenceProvider>
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <main className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</main>
          <MembersPanel channelId={channelId} />
        </div>
      </PresenceProvider>
    </WebSocketProvider>
  )
}
