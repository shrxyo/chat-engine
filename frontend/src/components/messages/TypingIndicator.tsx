'use client'

interface TypingUser {
  userId: string
  userName: string
}

interface TypingIndicatorProps {
  typingUsers: TypingUser[]
}

function formatTypingText(users: TypingUser[]): string {
  if (users.length === 0) return ''
  if (users.length === 1) return `${users[0].userName} is typing`
  if (users.length === 2) return `${users[0].userName} and ${users[1].userName} are typing`
  return `${users[0].userName} and ${users.length - 1} others are typing`
}

export function TypingIndicator({ typingUsers }: TypingIndicatorProps) {
  if (typingUsers.length === 0) return null

  return (
    <div
      className="flex items-center gap-1.5 px-4 py-1 text-xs text-muted-foreground"
      role="status"
      aria-live="polite"
      aria-label={formatTypingText(typingUsers)}
    >
      {/* Animated dots */}
      <span className="flex items-center gap-0.5" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="size-1.5 animate-bounce rounded-full bg-muted-foreground"
            style={{ animationDelay: `${i * 150}ms`, animationDuration: '900ms' }}
          />
        ))}
      </span>
      <span>{formatTypingText(typingUsers)}&hellip;</span>
    </div>
  )
}
