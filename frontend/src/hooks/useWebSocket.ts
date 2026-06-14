'use client'

/**
 * Convenience hook for consuming the WebSocket connection.
 * Components call this instead of importing WebSocketContext directly.
 *
 * Must be used inside <WebSocketProvider>.
 */

import { useWebSocketContext } from '@/contexts/WebSocketContext'

export function useWebSocket() {
  return useWebSocketContext()
}
