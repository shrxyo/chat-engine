'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'
import { Hash, Plus } from 'lucide-react'
import { api } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { DMSection } from '@/components/layout/DMSection'
import type { Channel } from '@/types'

interface ChannelItemProps {
  channel: Channel
  isActive: boolean
  unreadCount?: number
}

function ChannelItem({ channel, isActive, unreadCount }: ChannelItemProps) {
  return (
    <Link
      href={`/channels/${channel.id}`}
      className={cn(
        'group flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
        isActive
          ? 'bg-accent text-accent-foreground font-medium'
          : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
      )}
      aria-current={isActive ? 'page' : undefined}
    >
      <Hash className="size-4 shrink-0" aria-hidden />
      <span className="min-w-0 flex-1 truncate">{channel.name}</span>
      {unreadCount && unreadCount > 0 ? (
        <Badge variant="default" className="ml-auto shrink-0 text-xs tabular-nums">
          {unreadCount > 99 ? '99+' : unreadCount}
        </Badge>
      ) : null}
    </Link>
  )
}

export function ChannelSidebar() {
  const pathname = usePathname()
  const { data: session } = useSession()
  const token = (session as { accessToken?: string } | null)?.accessToken

  const { data: channels, isLoading } = useQuery({
    queryKey: queryKeys.channels.all(),
    queryFn: () => api.channels.list(token),
    enabled: !!token,
  })

  const activeChannelId = pathname.match(/\/channels\/([^/]+)/)?.[1]

  return (
    <nav
      className="flex h-full w-60 shrink-0 flex-col overflow-y-auto border-r bg-muted/40 py-3"
      aria-label="Channels"
    >
      <div className="flex items-center justify-between px-3 pb-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Channels
        </span>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger
              className="rounded p-0.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Create channel"
            >
              <Plus className="size-4" aria-hidden />
            </TooltipTrigger>
            <TooltipContent>Create channel</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <div className="flex flex-col gap-0.5 px-2">
        {isLoading
          ? Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="mx-2 h-7 rounded-md" />
            ))
          : channels?.map((channel) => (
              <ChannelItem
                key={channel.id}
                channel={channel}
                isActive={channel.id === activeChannelId}
              />
            ))}
      </div>

      <DMSection />
    </nav>
  )
}
