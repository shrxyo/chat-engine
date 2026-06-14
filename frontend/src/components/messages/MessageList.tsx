'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { format, isToday, isYesterday, isSameDay } from 'date-fns'
import { useSession } from 'next-auth/react'
import { useMessages } from '@/hooks/useMessages'
import { useTypingIndicator } from '@/hooks/useTypingIndicator'
import { Message } from './Message'
import { TypingIndicator } from './TypingIndicator'
import { MessageInput } from './MessageInput'
import { ChannelHeader, useChannelDisplayInfo } from '@/components/layout/ChannelHeader'
import { Skeleton } from '@/components/ui/skeleton'
import type { Message as MessageType } from '@/types'

// ---------------------------------------------------------------------------
// Day separator helpers
// ---------------------------------------------------------------------------

function dayLabel(isoString: string): string {
  const d = new Date(isoString)
  if (isToday(d)) return 'Today'
  if (isYesterday(d)) return 'Yesterday'
  return format(d, 'MMMM d, yyyy')
}

type ListItem =
  | { kind: 'day'; label: string; key: string }
  | { kind: 'message'; message: MessageType; key: string }

function buildItems(messages: MessageType[]): ListItem[] {
  const items: ListItem[] = []
  let lastDate: Date | null = null

  for (const msg of messages) {
    const msgDate = new Date(msg.created_at)
    if (!lastDate || !isSameDay(lastDate, msgDate)) {
      items.push({ kind: 'day', label: dayLabel(msg.created_at), key: `day-${msg.created_at}` })
      lastDate = msgDate
    }
    items.push({ kind: 'message', message: msg, key: msg.id })
  }

  return items
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface MessageListProps {
  channelId: string
}

export function MessageList({ channelId }: MessageListProps) {
  const { data: session } = useSession()
  const currentUserId = session?.user?.id as string | undefined
  const { displayName: channelName, isDm } = useChannelDisplayInfo(channelId)

  const { messages, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage, sendMessage, editMessage, deleteMessage } =
    useMessages(channelId)
  const { typingUsers, notifyTyping, notifyStopTyping } = useTypingIndicator(currentUserId)

  const items = buildItems(messages)

  const parentRef = useRef<HTMLDivElement>(null)

  // Track whether the user has scrolled up so we don't hijack their position
  const [userScrolledUp, setUserScrolledUp] = useState(false)
  const prevMessageCountRef = useRef(0)

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: (index) => {
      const item = items[index]
      return item?.kind === 'day' ? 40 : 64
    },
    overscan: 8,
  })

  const virtualItems = virtualizer.getVirtualItems()
  const totalSize = virtualizer.getTotalSize()

  // ---------------------------------------------------------------------------
  // IntersectionObserver for infinite scroll (top sentinel)
  // ---------------------------------------------------------------------------
  const topSentinelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const sentinel = topSentinelRef.current
    if (!sentinel || !hasNextPage) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && !isFetchingNextPage) {
          fetchNextPage()
        }
      },
      { root: parentRef.current, threshold: 0 },
    )

    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  // ---------------------------------------------------------------------------
  // Auto-scroll to bottom on new messages (unless scrolled up)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const el = parentRef.current
    if (!el) return

    const newCount = messages.length
    if (newCount === prevMessageCountRef.current) return
    prevMessageCountRef.current = newCount

    if (!userScrolledUp) {
      // Scroll to the last virtual item
      virtualizer.scrollToIndex(items.length - 1, { align: 'end' })
    }
  }, [messages.length, items.length, userScrolledUp, virtualizer])

  // Detect user scroll direction to set userScrolledUp
  const handleScroll = useCallback(() => {
    const el = parentRef.current
    if (!el) return
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setUserScrolledUp(distFromBottom > 120)
  }, [])

  if (isLoading) {
    return (
      <div className="flex flex-1 flex-col gap-4 p-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex gap-3">
            <Skeleton className="size-9 shrink-0 rounded-full" />
            <div className="flex flex-1 flex-col gap-1.5">
              <Skeleton className="h-3 w-24 rounded" />
              <Skeleton className="h-4 w-full rounded" />
              <Skeleton className="h-4 w-3/4 rounded" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <ChannelHeader channelId={channelId} />

      {/* Scrollable message area */}
      <div
        ref={parentRef}
        className="flex-1 overflow-y-auto"
        onScroll={handleScroll}
      >
        {/* Top sentinel for infinite scroll */}
        <div ref={topSentinelRef} className="h-px" aria-hidden />

        {isFetchingNextPage && (
          <div className="flex justify-center py-3">
            <Skeleton className="h-4 w-32 rounded" />
          </div>
        )}

        {/* Virtual list container */}
        <div style={{ height: `${totalSize}px`, position: 'relative' }}>
          {virtualItems.map((vItem) => {
            const item = items[vItem.index]
            if (!item) return null

            return (
              <div
                key={item.key}
                data-index={vItem.index}
                ref={virtualizer.measureElement}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  transform: `translateY(${vItem.start}px)`,
                }}
              >
                {item.kind === 'day' ? (
                  <DaySeparator label={item.label} />
                ) : (
                  <Message
                    message={item.message}
                    currentUserId={currentUserId}
                    onEdit={editMessage}
                    onDelete={deleteMessage}
                  />
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Typing indicator */}
      <TypingIndicator typingUsers={typingUsers} />

      {/* Message input */}
      <MessageInput
        channelName={channelName}
        isDm={isDm}
        onSend={sendMessage}
        onTyping={notifyTyping}
        onStopTyping={notifyStopTyping}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Day separator sub-component
// ---------------------------------------------------------------------------

interface DaySeparatorProps {
  label: string
}

function DaySeparator({ label }: DaySeparatorProps) {
  return (
    <div
      className="flex items-center gap-3 px-4 py-2"
      role="separator"
      aria-label={label}
    >
      <div className="h-px flex-1 bg-border" aria-hidden />
      <span className="shrink-0 rounded-full border px-3 py-0.5 text-xs font-medium text-muted-foreground">
        {label}
      </span>
      <div className="h-px flex-1 bg-border" aria-hidden />
    </div>
  )
}
