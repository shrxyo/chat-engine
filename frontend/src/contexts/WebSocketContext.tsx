'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react'
import { useSession } from 'next-auth/react'

export type WSHandler = (payload: unknown) => void

export interface WebSocketContextValue {
  isConnected: boolean
  send: (type: string, payload: unknown) => void
  subscribe: (type: string, handler: WSHandler) => () => void
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null)

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000'
const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30_000

interface WebSocketProviderProps {
  channelId: string
  children: React.ReactNode
}

export function WebSocketProvider({ channelId, children }: WebSocketProviderProps) {
  const { data: session } = useSession()
  const [isConnected, setIsConnected] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const handlersRef = useRef<Map<string, Set<WSHandler>>>(new Map())
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const attemptRef = useRef(0)
  // Track whether the provider is still mounted
  const mountedRef = useRef(true)

  const getToken = useCallback(() => {
    // next-auth v5: accessToken is surfaced via session callback in auth.ts
    return (session as { accessToken?: string } | null)?.accessToken
  }, [session])

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    const token = getToken()
    if (!token) return

    const url = `${WS_BASE}/ws/${channelId}?token=${token}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      attemptRef.current = 0
      setIsConnected(true)
    }

    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const envelope = JSON.parse(event.data) as { type: string; payload: unknown }
        const handlers = handlersRef.current.get(envelope.type)
        handlers?.forEach((h) => h(envelope.payload))
      } catch {
        // Ignore malformed frames
      }
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setIsConnected(false)
      wsRef.current = null

      // Exponential backoff with ±20 % jitter
      const base = Math.min(RECONNECT_BASE_MS * 2 ** attemptRef.current, RECONNECT_MAX_MS)
      const jitter = base * 0.2 * (Math.random() * 2 - 1)
      const delay = Math.round(base + jitter)
      attemptRef.current++

      reconnectTimerRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [channelId, getToken])

  // Connect when the token is available, reconnect if channelId changes
  useEffect(() => {
    mountedRef.current = true
    connect()

    return () => {
      mountedRef.current = false
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connect])

  const send = useCallback((type: string, payload: unknown) => {
    const ws = wsRef.current
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, payload }))
    }
  }, [])

  const subscribe = useCallback((type: string, handler: WSHandler): (() => void) => {
    const set = handlersRef.current.get(type) ?? new Set<WSHandler>()
    set.add(handler)
    handlersRef.current.set(type, set)
    return () => {
      set.delete(handler)
    }
  }, [])

  return (
    <WebSocketContext.Provider value={{ isConnected, send, subscribe }}>
      {children}
    </WebSocketContext.Provider>
  )
}

/** Reads WebSocket context. Must be used inside <WebSocketProvider>. */
export function useWebSocketContext(): WebSocketContextValue {
  const ctx = useContext(WebSocketContext)
  if (!ctx) {
    throw new Error('useWebSocketContext must be used inside <WebSocketProvider>')
  }
  return ctx
}
