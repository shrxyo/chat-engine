import '@testing-library/react/pure'

// Provide a minimal WebSocket mock so tests that import WS-dependent hooks
// don't fail in jsdom (which has no real WebSocket).
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  readyState = MockWebSocket.OPEN
  onopen: ((e: Event) => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  onclose: ((e: CloseEvent) => void) | null = null
  onerror: ((e: Event) => void) | null = null

  constructor(public url: string) {}
  send(_data: string) {}
  close() {
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) {
      this.onclose(new CloseEvent('close', { code: 1000, reason: '', wasClean: true }))
    }
  }
}

Object.defineProperty(globalThis, 'WebSocket', { value: MockWebSocket, writable: true })
