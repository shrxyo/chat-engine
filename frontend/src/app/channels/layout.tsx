import { ChannelSidebar } from '@/components/layout/ChannelSidebar'
import { ChannelShell } from '@/components/layout/ChannelShell'

interface ChannelsLayoutProps {
  children: React.ReactNode
}

/**
 * Three-panel Discord-style layout:
 *   [ ChannelSidebar | <page children> | MembersPanel ]
 *
 * ChannelShell is a client component that reads the active channelId from
 * the URL via useParams() and provides WebSocketContext + PresenceContext.
 */
export default function ChannelsLayout({ children }: ChannelsLayoutProps) {
  return (
    <div className="flex h-screen overflow-hidden">
      <ChannelSidebar />
      <ChannelShell>{children}</ChannelShell>
    </div>
  )
}
