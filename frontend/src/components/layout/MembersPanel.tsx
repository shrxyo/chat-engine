'use client'

import { useRouter } from 'next/navigation'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'
import { MessageCircle } from 'lucide-react'
import { api } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { usePresence } from '@/contexts/PresenceContext'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { Member, User } from '@/types'

interface MemberRowProps {
  member: Member
  user: User | undefined
  isOnline: boolean
  isCurrentUser: boolean
  onSendDm: (userId: string) => void
  isSendingDm: boolean
}

function MemberRow({
  member,
  user,
  isOnline,
  isCurrentUser,
  onSendDm,
  isSendingDm,
}: MemberRowProps) {
  const displayName = user?.name ?? member.user_id.slice(0, 8)
  const initials = user?.name
    ? user.name
        .split(' ')
        .map((part) => part[0])
        .join('')
        .slice(0, 2)
        .toUpperCase()
    : member.user_id.slice(0, 2).toUpperCase()

  return (
    <div className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-accent/50">
      <DropdownMenu>
        <DropdownMenuTrigger
          className="relative shrink-0 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`Actions for ${displayName}`}
        >
          <Avatar className="size-7">
            <AvatarImage src={user?.avatar_url ?? undefined} alt={displayName} />
            <AvatarFallback className="text-xs">{initials}</AvatarFallback>
          </Avatar>
          <span
            className={cn(
              'absolute -bottom-0.5 -right-0.5 size-2.5 rounded-full ring-2 ring-background',
              isOnline ? 'bg-green-500' : 'bg-muted-foreground',
            )}
            aria-label={isOnline ? 'Online' : 'Offline'}
          />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          {!isCurrentUser && (
            <DropdownMenuItem
              disabled={isSendingDm}
              onClick={() => onSendDm(member.user_id)}
            >
              <MessageCircle className="size-4" aria-hidden />
              Send DM
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <span className="min-w-0 flex-1 truncate text-sm">{displayName}</span>
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
  const router = useRouter()
  const queryClient = useQueryClient()
  const { data: session } = useSession()
  const token = (session as { accessToken?: string } | null)?.accessToken
  const { isOnline } = usePresence()

  const { data: channel, isLoading } = useQuery({
    queryKey: queryKeys.channels.detail(channelId),
    queryFn: () => api.channels.detail(channelId, token),
    enabled: !!token,
  })

  const { data: currentUser } = useQuery({
    queryKey: queryKeys.users.me(),
    queryFn: () => api.users.me(token),
    enabled: !!token,
  })

  const members = channel?.members

  const sendDmMutation = useMutation({
    mutationFn: (userId: string) => api.dm.create(userId, token),
    onSuccess: (dm) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.dm.all() })
      router.push(`/channels/${dm.id}`)
    },
  })

  const userQueries = useQuery({
    queryKey: ['members-users', channelId, members?.map((m) => m.user_id).join(',')],
    queryFn: async () => {
      if (!members || !token) return new Map<string, User>()
      const users = await Promise.all(
        members.map((m) => api.users.detail(m.user_id, token)),
      )
      return new Map(users.map((u) => [u.id, u]))
    },
    enabled: !!token && !!members && members.length > 0,
  })

  const userMap = userQueries.data ?? new Map<string, User>()

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
                <MemberRow
                  key={m.user_id}
                  member={m}
                  user={userMap.get(m.user_id)}
                  isOnline
                  isCurrentUser={m.user_id === currentUser?.id}
                  onSendDm={(userId) => sendDmMutation.mutate(userId)}
                  isSendingDm={sendDmMutation.isPending}
                />
              ))}
            </>
          )}
          {offline.length > 0 && (
            <>
              <p className="px-2 py-1 text-xs font-semibold uppercase text-muted-foreground">
                Offline — {offline.length}
              </p>
              {offline.map((m) => (
                <MemberRow
                  key={m.user_id}
                  member={m}
                  user={userMap.get(m.user_id)}
                  isOnline={false}
                  isCurrentUser={m.user_id === currentUser?.id}
                  onSendDm={(userId) => sendDmMutation.mutate(userId)}
                  isSendingDm={sendDmMutation.isPending}
                />
              ))}
            </>
          )}
        </div>
      )}
    </aside>
  )
}
