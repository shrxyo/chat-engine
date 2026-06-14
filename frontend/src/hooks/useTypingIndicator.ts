'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useWebSocket } from './useWebSocket'
import type { WSTypingPayload } from '@/types'

interface TypingUser {
  userId: string
  userName: string
}

const TYPING_TIMEOUT_MS = 3000

interface UseTypingIndicatorReturn {
  typingUsers: TypingUser[]
  notifyTyping: () => void
  notifyStopTyping: () => void
}

export function useTypingIndicator(currentUserId: string | undefined): UseTypingIndicatorReturn {
  const { send, subscribe } = useWebSocket()
  const [typingUsers, setTypingUsers] = useState<TypingUser[]>([])

  // Per-user timers to auto-expire typing state
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  useEffect(() => {
    const unsubStart = subscribe('typing.start', (payload) => {
      const p = payload as WSTypingPayload
      if (p.user_id === currentUserId) return

      // Reset expiry timer
      const existing = timersRef.current.get(p.user_id)
      if (existing) clearTimeout(existing)

      setTypingUsers((prev) => {
        if (prev.some((u) => u.userId === p.user_id)) return prev
        return [...prev, { userId: p.user_id, userName: p.user_name }]
      })

      const timer = setTimeout(() => {
        setTypingUsers((prev) => prev.filter((u) => u.userId !== p.user_id))
        timersRef.current.delete(p.user_id)
      }, TYPING_TIMEOUT_MS)

      timersRef.current.set(p.user_id, timer)
    })

    const unsubStop = subscribe('typing.stop', (payload) => {
      const p = payload as WSTypingPayload
      const timer = timersRef.current.get(p.user_id)
      if (timer) {
        clearTimeout(timer)
        timersRef.current.delete(p.user_id)
      }
      setTypingUsers((prev) => prev.filter((u) => u.userId !== p.user_id))
    })

    return () => {
      unsubStart()
      unsubStop()
      timersRef.current.forEach(clearTimeout)
      timersRef.current.clear()
    }
  }, [subscribe, currentUserId])

  // Debounce outgoing typing.stop so we don't spam the server
  const stopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const notifyTyping = useCallback(() => {
    send('typing.start', {})
    if (stopTimerRef.current) clearTimeout(stopTimerRef.current)
    stopTimerRef.current = setTimeout(() => {
      send('typing.stop', {})
      stopTimerRef.current = null
    }, TYPING_TIMEOUT_MS)
  }, [send])

  const notifyStopTyping = useCallback(() => {
    if (stopTimerRef.current) {
      clearTimeout(stopTimerRef.current)
      stopTimerRef.current = null
    }
    send('typing.stop', {})
  }, [send])

  return { typingUsers, notifyTyping, notifyStopTyping }
}
