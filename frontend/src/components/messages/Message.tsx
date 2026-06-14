'use client'

import { useState } from 'react'
import { format, isToday, isYesterday } from 'date-fns'
import { MoreHorizontal, Pencil, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { Message as MessageType } from '@/types'

function formatMessageTime(isoString: string): string {
  const date = new Date(isoString)
  if (isToday(date)) return format(date, 'HH:mm')
  if (isYesterday(date)) return `Yesterday ${format(date, 'HH:mm')}`
  return format(date, 'MMM d, HH:mm')
}

interface MessageProps {
  message: MessageType
  currentUserId: string | undefined
  onEdit: (messageId: string, content: string) => void
  onDelete: (messageId: string) => void
}

export function Message({ message, currentUserId, onEdit, onDelete }: MessageProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState(message.content)

  const isOwn = message.user_id === currentUserId
  const initials = message.user_id.slice(0, 2).toUpperCase()

  function handleSaveEdit() {
    const trimmed = editContent.trim()
    if (trimmed && trimmed !== message.content) {
      onEdit(message.id, trimmed)
    }
    setIsEditing(false)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSaveEdit()
    }
    if (e.key === 'Escape') {
      setEditContent(message.content)
      setIsEditing(false)
    }
  }

  return (
    <article
      className={cn(
        'group relative flex gap-3 px-4 py-1 hover:bg-accent/30',
        message.pending && 'opacity-60',
        message.failed && 'opacity-60',
      )}
      aria-label={`Message from user ${message.user_id}`}
    >
      {/* Avatar */}
      <Avatar className="mt-0.5 size-9 shrink-0">
        <AvatarFallback className="text-xs">{initials}</AvatarFallback>
      </Avatar>

      <div className="min-w-0 flex-1">
        {/* Header: username + timestamp */}
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-semibold">{message.user_id.slice(0, 8)}</span>
          <time
            dateTime={message.created_at}
            className="text-xs text-muted-foreground"
          >
            {formatMessageTime(message.created_at)}
          </time>
          {message.edited_at && (
            <span className="text-xs text-muted-foreground">(edited)</span>
          )}
          {message.pending && (
            <span className="text-xs text-muted-foreground" aria-label="Sending">
              sending…
            </span>
          )}
          {message.failed && (
            <span className="text-xs text-destructive">Failed to send</span>
          )}
        </div>

        {/* Body */}
        {isEditing ? (
          <textarea
            className="mt-1 w-full resize-none rounded-md border bg-background px-2 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={handleSaveEdit}
            rows={Math.max(1, editContent.split('\n').length)}
            autoFocus
          />
        ) : (
          <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">
            {message.content}
          </p>
        )}
      </div>

      {/* Action menu — visible on hover, only for message owner */}
      {isOwn && !message.pending && (
        <div className="absolute right-4 top-1 hidden group-hover:flex">
          <DropdownMenu>
            <DropdownMenuTrigger
              className="inline-flex size-7 items-center justify-center rounded-md p-0 text-sm transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              aria-label="Message actions"
            >
              <MoreHorizontal className="size-4" aria-hidden />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onSelect={() => {
                  setEditContent(message.content)
                  setIsEditing(true)
                }}
              >
                <Pencil className="mr-2 size-4" aria-hidden />
                Edit
              </DropdownMenuItem>
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onSelect={() => onDelete(message.id)}
              >
                <Trash2 className="mr-2 size-4" aria-hidden />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}
    </article>
  )
}
