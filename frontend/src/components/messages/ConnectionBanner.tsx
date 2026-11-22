'use client'

import { cn } from '@/lib/utils'

interface ConnectionBannerProps {
  /** Socket dropped and is retrying with backoff. */
  isReconnecting: boolean
  /** Socket is back; fetching messages missed while it was down. */
  isCatchingUp: boolean
}

/** S4.3: tells the user the live feed is (or was just) interrupted. */
export function ConnectionBanner({ isReconnecting, isCatchingUp }: ConnectionBannerProps) {
  if (!isReconnecting && !isCatchingUp) return null

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'border-b px-4 py-1.5 text-center text-xs font-medium',
        isReconnecting
          ? 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400'
          : 'border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-400',
      )}
    >
      {isReconnecting ? 'Reconnecting…' : 'Reconnected — catching up…'}
    </div>
  )
}
