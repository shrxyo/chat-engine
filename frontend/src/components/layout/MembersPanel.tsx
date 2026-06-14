'use client'

import { useQuery } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'
import { api } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { usePresence } from '@/contexts/PresenceContext'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { Member } from '@/types'

interface MemberRowProps {
  member: Member
  isOnline: boolean
}

function MemberRow({ member, isOnline }: MemberRowProps) {
  const initials = member.user_id.slice(0, 2).toUpperCase()

  return (
    <div className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-accent/50">
      <div className="relative shrink-0">
        <Avatar className="size-7">
          <AvatarImage src={undefined} alt="" />
          <AvatarFallback className="text-xs">{initials}</AvatarFallback>
        </Avatar>
        <span
          className={cn(
            'absolute -bottom-0.5 -right-0.5 size-2.5 rounded-full ring-2 ring-background',
            isOnline ? 'bg-green-500' : 'bg-muted-foreground',
          )}
          aria-label={isOnline ? 'Online' : 'Offline'}
        />
      </div>
      <span className="min-w-0 flex-1 truncate text-sm">
        {member.user_id.slice(0, 8)}
      </span>
      <span className="shrink-0 text-xs capitalize text-muted-foreground">
        {member.role}
      </span>
    </div>
  )
}

interface MembersPanelProps {
  channelId: string
}

export function MembersPanel({ channelId }: MembersPanelProps) {
  const { data: session } = useSession()
  const token = (session as { accessToken?: string } | null)?.accessToken
  const { isOnline } = usePresence()

  const { data: members, isLoading } = useQuery({
    queryKey: queryKeys.channels.members(channelId),
    queryFn: () => api.channels.members(channelId, token),
    enabled: !!token,
  })

  const online = members?.filter((m) => isOnline(m.user_id)) ?? []
  const offline = members?.filter((m) => !isOnline(m.user_id)) ?? []

  return (
    <aside
      className="flex h-full w-56 shrink-0 flex-col overflow-y-auto border-l bg-muted/40 py-3"
      aria-label="Members"
    >
      <p className="px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Members
      </p>

      {isLoading ? (
        <div className="flex flex-col gap-2 px-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-8 rounded-md" />
          ))}
        </div>
      ) : (
        <div className="flex flex-col gap-0.5 px-2">
          {online.length > 0 && (
            <>
              <p className="px-2 py-1 text-xs font-semibold uppercase text-muted-foreground">
                Online — {online.length}
              </p>
              {online.map((m) => (
                <MemberRow key={m.user_id} member={m} isOnline />
              ))}
            </>
          )}
          {offline.length > 0 && (
            <>
              <p className="px-2 py-1 text-xs font-semibold uppercase text-muted-foreground">
                Offline — {offline.length}
              </p>
              {offline.map((m) => (
                <MemberRow key={m.user_id} member={m} isOnline={false} />
              ))}
            </>
          )}
        </div>
      )}
    </aside>
  )
}
