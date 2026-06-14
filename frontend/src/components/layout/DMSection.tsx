'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'
import { api } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { cn } from '@/lib/utils'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Skeleton } from '@/components/ui/skeleton'
import type { DMChannel } from '@/types'

interface DMItemProps {
  dm: DMChannel
  isActive: boolean
}

function DMItem({ dm, isActive }: DMItemProps) {
  const { other_user: otherUser } = dm
  const initials = otherUser.name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  return (
    <Link
      href={`/channels/${dm.id}`}
      className={cn(
        'group flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
        isActive
          ? 'bg-accent text-accent-foreground font-medium'
          : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
      )}
      aria-current={isActive ? 'page' : undefined}
    >
      <Avatar className="size-5 shrink-0">
        <AvatarImage src={otherUser.avatar_url ?? undefined} alt={otherUser.name} />
        <AvatarFallback className="text-[10px]">{initials}</AvatarFallback>
      </Avatar>
      <span className="min-w-0 flex-1 truncate">{otherUser.name}</span>
    </Link>
  )
}

export function DMSection() {
  const pathname = usePathname()
  const { data: session } = useSession()
  const token = (session as { accessToken?: string } | null)?.accessToken

  const { data: dms, isLoading } = useQuery({
    queryKey: queryKeys.dm.all(),
    queryFn: () => api.dm.list(token),
    enabled: !!token,
  })

  const activeChannelId = pathname.match(/\/channels\/([^/]+)/)?.[1]

  return (
    <div className="mt-4 flex flex-col">
      <p className="px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Direct Messages
      </p>

      <div className="flex flex-col gap-0.5 px-2">
        {isLoading
          ? Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="mx-2 h-7 rounded-md" />
            ))
          : dms?.map((dm) => (
              <DMItem key={dm.id} dm={dm} isActive={dm.id === activeChannelId} />
            ))}
      </div>
    </div>
  )
}
