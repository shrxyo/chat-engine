'use client'

import { createContext, useContext, useEffect, useReducer } from 'react'
import { useWebSocketContext } from './WebSocketContext'
import type { WSPresencePayload, WSPresenceSnapshotPayload } from '@/types'

// S4.2: the server sends presence.snapshot on every (re)connect, then
// join/leave deltas. Online state is per channel (this provider's socket).
type PresenceAction =
  | { type: 'snapshot'; userIds: string[] }
  | { type: 'join'; userId: string }
  | { type: 'leave'; userId: string }

function presenceReducer(state: ReadonlySet<string>, action: PresenceAction): ReadonlySet<string> {
  if (action.type === 'snapshot') return new Set(action.userIds)
  if (action.type === 'join') {
    if (state.has(action.userId)) return state
    return new Set(state).add(action.userId)
  }
  if (!state.has(action.userId)) return state
  const next = new Set(state)
  next.delete(action.userId)
  return next
}

interface PresenceContextValue {
  onlineUserIds: ReadonlySet<string>
  onlineCount: number
  isOnline: (userId: string) => boolean
}

const PresenceContext = createContext<PresenceContextValue | null>(null)

interface PresenceProviderProps {
  children: React.ReactNode
}

export function PresenceProvider({ children }: PresenceProviderProps) {
  const { subscribe } = useWebSocketContext()
  const [onlineUserIds, dispatch] = useReducer(presenceReducer, new Set<string>())

  useEffect(() => {
    const unsubSnapshot = subscribe('presence.snapshot', (payload) => {
      const p = payload as WSPresenceSnapshotPayload
      dispatch({ type: 'snapshot', userIds: p.online_user_ids })
    })
    const unsubJoin = subscribe('presence.join', (payload) => {
      const p = payload as WSPresencePayload
      dispatch({ type: 'join', userId: p.user_id })
    })
    const unsubLeave = subscribe('presence.leave', (payload) => {
      const p = payload as WSPresencePayload
      dispatch({ type: 'leave', userId: p.user_id })
    })

    return () => {
      unsubSnapshot()
      unsubJoin()
      unsubLeave()
    }
  }, [subscribe])

  const isOnline = (userId: string) => onlineUserIds.has(userId)

  return (
    <PresenceContext.Provider
      value={{ onlineUserIds, onlineCount: onlineUserIds.size, isOnline }}
    >
      {children}
    </PresenceContext.Provider>
  )
}

export function usePresence(): PresenceContextValue {
  const ctx = useContext(PresenceContext)
  if (!ctx) {
    throw new Error('usePresence must be used inside <PresenceProvider>')
  }
  return ctx
}
