'use client'

import { useCallback, useRef } from 'react'
import { Paperclip, Send, Smile } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

// A curated set of common emoji for the quick-picker
const QUICK_EMOJI = ['👍', '❤️', '😂', '🎉', '🔥', '👀', '✅', '🙏', '💯', '😊']

interface MessageInputProps {
  channelName: string
  isDm?: boolean
  onSend: (content: string) => void
  onTyping?: () => void
  onStopTyping?: () => void
  disabled?: boolean
}

export function MessageInput({
  channelName,
  isDm = false,
  onSend,
  onTyping,
  onStopTyping,
  disabled = false,
}: MessageInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  /** Grow the textarea to fit its content, capped at ~8 rows. */
  function autoGrow(el: HTMLTextAreaElement) {
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }

  function resetHeight(el: HTMLTextAreaElement) {
    el.style.height = 'auto'
  }

  const submit = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    const content = el.value.trim()
    if (!content) return

    onSend(content)
    onStopTyping?.()
    el.value = ''
    resetHeight(el)
    el.focus()
  }, [onSend, onStopTyping])

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    autoGrow(e.target)
    if (e.target.value.trim()) {
      onTyping?.()
    } else {
      onStopTyping?.()
    }
  }

  function insertEmoji(emoji: string) {
    const el = textareaRef.current
    if (!el) return
    const start = el.selectionStart ?? el.value.length
    const end = el.selectionEnd ?? el.value.length
    el.value = el.value.slice(0, start) + emoji + el.value.slice(end)
    el.selectionStart = el.selectionEnd = start + emoji.length
    autoGrow(el)
    el.focus()
    onTyping?.()
  }

  const placeholder = isDm ? `Message ${channelName}` : `Message #${channelName}`

  return (
    <div className="border-t bg-background px-4 py-3">
      <div
        className={cn(
          'flex items-end gap-2 rounded-xl border bg-muted/30 px-3 py-2 transition-colors',
          'focus-within:border-ring focus-within:ring-1 focus-within:ring-ring',
        )}
      >
        {/* Emoji picker */}
        <DropdownMenu>
          <DropdownMenuTrigger
            className="mb-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50"
            aria-label="Insert emoji"
            disabled={disabled}
          >
            <Smile className="size-4" aria-hidden />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" className="grid grid-cols-5 gap-0 p-1">
            {QUICK_EMOJI.map((emoji) => (
              <DropdownMenuItem
                key={emoji}
                className="flex items-center justify-center text-lg"
                onSelect={() => insertEmoji(emoji)}
              >
                {emoji}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Text area */}
        <textarea
          ref={textareaRef}
          rows={1}
          placeholder={placeholder}
          className="max-h-[200px] flex-1 resize-none bg-transparent text-sm leading-relaxed placeholder:text-muted-foreground focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
          disabled={disabled}
          onKeyDown={handleKeyDown}
          onChange={handleInput}
          aria-label={placeholder}
          aria-multiline
        />

        {/* File attach trigger (placeholder — file upload is S8.3) */}
        <Button
          variant="ghost"
          size="icon"
          className="mb-0.5 size-7 shrink-0 text-muted-foreground"
          aria-label="Attach file (coming soon)"
          disabled
        >
          <Paperclip className="size-4" aria-hidden />
        </Button>

        {/* Send button */}
        <Button
          size="icon"
          className="mb-0.5 size-7 shrink-0"
          aria-label="Send message"
          disabled={disabled}
          onClick={submit}
        >
          <Send className="size-4" aria-hidden />
        </Button>
      </div>

      <p className="mt-1 text-center text-xs text-muted-foreground">
        <kbd className="rounded border px-1 font-mono">Enter</kbd> to send &nbsp;·&nbsp;
        <kbd className="rounded border px-1 font-mono">Shift+Enter</kbd> for newline
      </p>
    </div>
  )
}
