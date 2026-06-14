'use client'

import { useQuery } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'
import { Hash } from 'lucide-react'
import { api } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Skeleton } from '@/components/ui/skeleton'

interface ChannelHeaderProps {
  channelId: string
}

export function ChannelHeader({ channelId }: ChannelHeaderProps) {
  const { data: session } = useSession()
  const token = (session as { accessToken?: string } | null)?.accessToken

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

  const otherMember = channel?.is_dm
    ? channel.members.find((m) => m.user_id !== currentUser?.id)
    : undefined

  const { data: otherUser, isLoading: otherUserLoading } = useQuery({
    queryKey: queryKeys.users.detail(otherMember?.user_id ?? ''),
    queryFn: () => api.users.detail(otherMember!.user_id, token),
    enabled: !!token && !!otherMember,
  })

  if (isLoading || (channel?.is_dm && otherUserLoading)) {
    return (
      <header className="flex h-12 shrink-0 items-center gap-3 border-b px-4">
        <Skeleton className="size-7 rounded-full" />
        <Skeleton className="h-4 w-32 rounded" />
      </header>
    )
  }

  if (!channel) return null

  if (channel.is_dm && otherUser) {
    const initials = otherUser.name
      .split(' ')
      .map((part) => part[0])
      .join('')
      .slice(0, 2)
      .toUpperCase()

    return (
      <header className="flex h-12 shrink-0 items-center gap-3 border-b px-4">
        <Avatar className="size-7">
          <AvatarImage src={otherUser.avatar_url ?? undefined} alt={otherUser.name} />
          <AvatarFallback className="text-xs">{initials}</AvatarFallback>
        </Avatar>
        <h1 className="truncate text-sm font-semibold">{otherUser.name}</h1>
      </header>
    )
  }

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
      <Hash className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0">
        <h1 className="truncate text-sm font-semibold">{channel.name}</h1>
        {channel.description ? (
          <p className="truncate text-xs text-muted-foreground">{channel.description}</p>
        ) : null}
      </div>
    </header>
  )
}

/** Returns display info for the channel header and message input. */
export function useChannelDisplayInfo(channelId: string): {
  displayName: string
  isDm: boolean
} {
  const { data: session } = useSession()
  const token = (session as { accessToken?: string } | null)?.accessToken

  const { data: channel } = useQuery({
    queryKey: queryKeys.channels.detail(channelId),
    queryFn: () => api.channels.detail(channelId, token),
    enabled: !!token,
  })

  const { data: currentUser } = useQuery({
    queryKey: queryKeys.users.me(),
    queryFn: () => api.users.me(token),
    enabled: !!token,
  })

  const otherMember = channel?.is_dm
    ? channel.members.find((m) => m.user_id !== currentUser?.id)
    : undefined

  const { data: otherUser } = useQuery({
    queryKey: queryKeys.users.detail(otherMember?.user_id ?? ''),
    queryFn: () => api.users.detail(otherMember!.user_id, token),
    enabled: !!token && !!otherMember,
  })

  if (!channel) return { displayName: channelId, isDm: false }
  if (channel.is_dm && otherUser) return { displayName: otherUser.name, isDm: true }
  return { displayName: channel.name, isDm: false }
}
