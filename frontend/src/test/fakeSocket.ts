/**
 * Minimal WebSocket stand-in for tests. Install with `installFakeSocket()`
 * in beforeEach and restore with the returned function in afterEach.
 */

export class FakeSocket {
  static OPEN = 1
  static instances: FakeSocket[] = []

  readyState = 0
  sent: unknown[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor(public url: string) {
    FakeSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(JSON.parse(data))
  }

  close() {
    this.readyState = 3
    this.onclose?.()
  }

  open() {
    this.readyState = FakeSocket.OPEN
    this.onopen?.()
  }

  receive(type: string, payload: unknown) {
    this.onmessage?.({ data: JSON.stringify({ type, payload }) })
  }
}

export function lastSocket(): FakeSocket {
  const ws = FakeSocket.instances.at(-1)
  if (!ws) throw new Error('no socket opened')
  return ws
}

export function installFakeSocket(): () => void {
  const original = globalThis.WebSocket
  FakeSocket.instances = []
  globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket
  return () => {
    globalThis.WebSocket = original
  }
}
