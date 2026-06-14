'use client'

import { createContext, useContext, useEffect, useReducer } from 'react'
import { useWebSocketContext } from './WebSocketContext'
import type { WSPresencePayload } from '@/types'

export interface OnlineUser {
  userId: string
  userName: string
}

type PresenceAction =
  | { type: 'join'; user: OnlineUser }
  | { type: 'leave'; userId: string }

function presenceReducer(state: Map<string, OnlineUser>, action: PresenceAction): Map<string, OnlineUser> {
  const next = new Map(state)
  if (action.type === 'join') {
    next.set(action.user.userId, action.user)
  } else {
    next.delete(action.userId)
  }
  return next
}

interface PresenceContextValue {
  onlineUsers: Map<string, OnlineUser>
  isOnline: (userId: string) => boolean
}

const PresenceContext = createContext<PresenceContextValue | null>(null)

interface PresenceProviderProps {
  children: React.ReactNode
}

export function PresenceProvider({ children }: PresenceProviderProps) {
  const { subscribe } = useWebSocketContext()
  const [onlineUsers, dispatch] = useReducer(
    presenceReducer,
    new Map<string, OnlineUser>(),
  )

  useEffect(() => {
    const unsubJoin = subscribe('presence.join', (payload) => {
      const p = payload as WSPresencePayload
      dispatch({ type: 'join', user: { userId: p.user_id, userName: p.user_name } })
    })
    const unsubLeave = subscribe('presence.leave', (payload) => {
      const p = payload as WSPresencePayload
      dispatch({ type: 'leave', userId: p.user_id })
    })

    return () => {
      unsubJoin()
      unsubLeave()
    }
  }, [subscribe])

  const isOnline = (userId: string) => onlineUsers.has(userId)

  return (
    <PresenceContext.Provider value={{ onlineUsers, isOnline }}>
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
