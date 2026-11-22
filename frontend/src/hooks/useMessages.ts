'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useInfiniteQuery, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'
import { api, ApiError } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { useWebSocket } from './useWebSocket'
import type {
  Message,
  MessageListResponse,
  WSMessageDeletePayload,
  WSMessageEditPayload,
  WSMessageNewPayload,
} from '@/types'

type MessagesInfiniteData = InfiniteData<MessageListResponse, string | null>

/** Returns all messages across all fetched pages in chronological order. */
export function flattenMessages(data: MessagesInfiniteData | undefined): Message[] {
  if (!data) return []
  // Pages are fetched newest-first; reverse so oldest page comes first
  return [...data.pages].reverse().flatMap((p) => [...p.messages].reverse())
}

/** Largest gap merged in place after a reconnect; anything bigger reloads (S4.3). */
export const GAP_FILL_LIMIT = 200

/** Newest-first, by (created_at, id): the server's order. */
function compareNewestFirst(a: Message, b: Message): number {
  if (a.created_at !== b.created_at) return a.created_at < b.created_at ? 1 : -1
  return a.id < b.id ? 1 : a.id > b.id ? -1 : 0
}

/**
 * Merge gap-fill results into the newest page (newest-first). Dedupes by id;
 * live messages that arrived on the new socket may already be there.
 * Pending (unconfirmed) messages stay in front: they carry client clocks.
 */
export function mergeGapIntoPage(pageMessages: Message[], fetched: Message[]): Message[] {
  const pending = pageMessages.filter((m) => m.pending)
  const byId = new Map<string, Message>()
  for (const m of pageMessages) if (!m.pending) byId.set(m.id, m)
  for (const m of fetched) byId.set(m.id, m)
  return [...pending, ...[...byId.values()].sort(compareNewestFirst)]
}

/** Id of the newest server-confirmed message we hold, if any. */
function newestConfirmedId(data: MessagesInfiniteData | undefined): string | undefined {
  return data?.pages[0]?.messages.find((m) => !m.pending)?.id
}

interface UseMessagesReturn {
  messages: Message[]
  isLoading: boolean
  isFetchingNextPage: boolean
  hasNextPage: boolean
  fetchNextPage: () => void
  /** True while fetching messages missed during a disconnect. */
  isCatchingUp: boolean
  sendMessage: (content: string) => void
  editMessage: (messageId: string, content: string) => void
  deleteMessage: (messageId: string) => void
}

export function useMessages(channelId: string): UseMessagesReturn {
  const { data: session } = useSession()
  const token = (session as { accessToken?: string } | null)?.accessToken
  const currentUserId = session?.user?.id as string | undefined

  const queryClient = useQueryClient()
  const { send, subscribe, reconnectCount } = useWebSocket()
  const [isCatchingUp, setIsCatchingUp] = useState(false)

  // Map of content → tempId for pending messages (used to reconcile server echo)
  const pendingByContent = useRef<Map<string, string>>(new Map())

  const queryKey = queryKeys.channels.messages(channelId)

  const { data, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage } =
    useInfiniteQuery<MessageListResponse, Error, MessagesInfiniteData, readonly string[], string | null>({
      queryKey,
      queryFn: ({ pageParam }) => api.messages.list(channelId, pageParam, token),
      initialPageParam: null,
      getNextPageParam: (lastPage) => {
        if (!lastPage.has_more) return undefined
        const oldest = lastPage.messages.at(-1)
        return oldest?.id ?? undefined
      },
    })

  // ---------------------------------------------------------------------------
  // WebSocket event handlers
  // ---------------------------------------------------------------------------

  useEffect(() => {
    const unsubNew = subscribe('message.new', (payload) => {
      const msg = payload as WSMessageNewPayload
      if (msg.channel_id !== channelId) return

      queryClient.setQueryData<MessagesInfiniteData>(queryKey, (old) => {
        if (!old) return old

        const newMessage: Message = {
          id: msg.id,
          channel_id: msg.channel_id,
          user_id: msg.user_id,
          content: msg.content,
          reply_to_id: msg.reply_to_id,
          edited_at: msg.edited_at,
          created_at: msg.created_at,
        }

        // If this is our own echo, remove the matching pending message
        let firstPage = old.pages[0]
        if (msg.user_id === currentUserId) {
          const tempId = pendingByContent.current.get(msg.content)
          if (tempId) {
            pendingByContent.current.delete(msg.content)
            firstPage = {
              ...firstPage,
              messages: firstPage.messages.filter((m) => m.id !== tempId),
            }
          }
        }

        // Prepend confirmed message to the first (newest) page
        const updatedFirstPage = {
          ...firstPage,
          messages: [newMessage, ...firstPage.messages.filter((m) => m.id !== msg.id)],
        }

        return {
          ...old,
          pages: [updatedFirstPage, ...old.pages.slice(1)],
        }
      })
    })

    const unsubEdit = subscribe('message.edit', (payload) => {
      const p = payload as WSMessageEditPayload
      queryClient.setQueryData<MessagesInfiniteData>(queryKey, (old) => {
        if (!old) return old
        return {
          ...old,
          pages: old.pages.map((page) => ({
            ...page,
            messages: page.messages.map((m) =>
              m.id === p.message_id
                ? { ...m, content: p.content, edited_at: p.edited_at }
                : m,
            ),
          })),
        }
      })
    })

    const unsubDelete = subscribe('message.delete', (payload) => {
      const p = payload as WSMessageDeletePayload
      queryClient.setQueryData<MessagesInfiniteData>(queryKey, (old) => {
        if (!old) return old
        return {
          ...old,
          pages: old.pages.map((page) => ({
            ...page,
            messages: page.messages.filter((m) => m.id !== p.message_id),
          })),
        }
      })
    })

    return () => {
      unsubNew()
      unsubEdit()
      unsubDelete()
    }
  }, [subscribe, queryClient, queryKey, channelId, currentUserId])

  // ---------------------------------------------------------------------------
  // Reconnect gap fill (S4.3)
  // ---------------------------------------------------------------------------

  // Start from the count at mount, so mounting on an already-reconnected
  // socket does not trigger a fill.
  const handledReconnectRef = useRef(reconnectCount)

  useEffect(() => {
    if (reconnectCount === handledReconnectRef.current) return
    handledReconnectRef.current = reconnectCount

    const current = queryClient.getQueryData<MessagesInfiniteData>(queryKey)
    if (!current) return // initial load still in flight; it will see everything
    const afterId = newestConfirmedId(current)
    const reload = () => queryClient.resetQueries({ queryKey, exact: true })
    if (!afterId) {
      void reload()
      return
    }

    let cancelled = false
    setIsCatchingUp(true)
    queryClient
      .fetchQuery({
        queryKey: queryKeys.channels.messagesAfter(channelId, afterId),
        queryFn: () => api.messages.listAfter(channelId, afterId, GAP_FILL_LIMIT, token),
        staleTime: 0,
        gcTime: 0,
        retry: false,
      })
      .then(
        async (gap) => {
          if (cancelled) return
          if (gap.has_more) {
            // More than GAP_FILL_LIMIT missed: start over from the newest page.
            await reload()
            return
          }
          queryClient.setQueryData<MessagesInfiniteData>(queryKey, (old) => {
            if (!old) return old
            let firstPage = old.pages[0]
            // Our own messages whose echo was lost in the gap: drop the pending copy.
            for (const m of gap.messages) {
              const tempId = m.user_id === currentUserId && pendingByContent.current.get(m.content)
              if (tempId) {
                pendingByContent.current.delete(m.content)
                firstPage = { ...firstPage, messages: firstPage.messages.filter((p) => p.id !== tempId) }
              }
            }
            return {
              ...old,
              pages: [
                { ...firstPage, messages: mergeGapIntoPage(firstPage.messages, gap.messages) },
                ...old.pages.slice(1),
              ],
            }
          })
        },
        async (err: unknown) => {
          if (cancelled) return
          // 400: cursor unknown to the server, so reload. Anything else
          // (network): refetch the loaded pages and keep showing them meanwhile.
          if (err instanceof ApiError && err.status === 400) await reload()
          else await queryClient.invalidateQueries({ queryKey, exact: true })
        },
      )
      .finally(() => {
        if (!cancelled) setIsCatchingUp(false)
      })

    return () => {
      cancelled = true
      setIsCatchingUp(false)
    }
    // queryKey is rebuilt every render, so it is left out; channelId covers it.
  }, [reconnectCount, channelId, queryClient, token, currentUserId])

  // ---------------------------------------------------------------------------
  // Mutations
  // ---------------------------------------------------------------------------

  const sendMessage = useCallback(
    (content: string) => {
      if (!content.trim() || !currentUserId) return

      const tempId = crypto.randomUUID()
      const pendingMsg: Message = {
        id: tempId,
        channel_id: channelId,
        user_id: currentUserId,
        content,
        reply_to_id: null,
        edited_at: null,
        created_at: new Date().toISOString(),
        pending: true,
      }

      // Track for reconciliation
      pendingByContent.current.set(content, tempId)

      // Optimistically add to the front of the first page
      queryClient.setQueryData<MessagesInfiniteData>(queryKey, (old) => {
        if (!old) {
          return {
            pages: [{ messages: [pendingMsg], has_more: false }],
            pageParams: [null],
          }
        }
        const firstPage = old.pages[0]
        return {
          ...old,
          pages: [
            { ...firstPage, messages: [pendingMsg, ...firstPage.messages] },
            ...old.pages.slice(1),
          ],
        }
      })

      // Send over WS — server will broadcast echo confirming the message
      send('message.new', { content })
    },
    [channelId, currentUserId, queryClient, queryKey, send],
  )

  const editMessage = useCallback(
    (messageId: string, content: string) => {
      send('message.edit', { message_id: messageId, content })
    },
    [send],
  )

  const deleteMessage = useCallback(
    (messageId: string) => {
      send('message.delete', { message_id: messageId })
    },
    [send],
  )

  return {
    messages: flattenMessages(data),
    isLoading,
    isFetchingNextPage,
    hasNextPage: hasNextPage ?? false,
    fetchNextPage,
    isCatchingUp,
    sendMessage,
    editMessage,
    deleteMessage,
  }
}
