'use client'

import { useCallback, useEffect, useRef } from 'react'
import { useInfiniteQuery, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'
import { api } from '@/lib/api'
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

interface UseMessagesReturn {
  messages: Message[]
  isLoading: boolean
  isFetchingNextPage: boolean
  hasNextPage: boolean
  fetchNextPage: () => void
  sendMessage: (content: string) => void
  editMessage: (messageId: string, content: string) => void
  deleteMessage: (messageId: string) => void
}

export function useMessages(channelId: string): UseMessagesReturn {
  const { data: session } = useSession()
  const token = (session as { accessToken?: string } | null)?.accessToken
  const currentUserId = session?.user?.id as string | undefined

  const queryClient = useQueryClient()
  const { send, subscribe } = useWebSocket()

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
    sendMessage,
    editMessage,
    deleteMessage,
  }
}
