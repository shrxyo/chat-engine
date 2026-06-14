/**
 * Centralised API client.
 * All outgoing fetch() calls must go through this module.
 * Never call window.fetch() directly elsewhere.
 */

import type { Channel, ChannelDetail, Member, Message, MessageListResponse, User } from '@/types'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function apiFetch<T>(
  path: string,
  token: string | undefined | null,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  })

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new ApiError(res.status, `API ${res.status}: ${text}`)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  channels: {
    list: (token?: string | null) => apiFetch<Channel[]>('/api/channels', token),
    detail: (id: string, token?: string | null) =>
      apiFetch<ChannelDetail>(`/api/channels/${id}`, token),
    members: (id: string, token?: string | null) =>
      apiFetch<Member[]>(`/api/channels/${id}/members`, token),
  },

  messages: {
    list: (channelId: string, cursor?: string | null, token?: string | null) => {
      const qs = cursor ? `?before=${cursor}` : ''
      return apiFetch<MessageListResponse>(
        `/api/channels/${channelId}/messages${qs}`,
        token,
      )
    },
    create: (
      channelId: string,
      payload: { content: string; reply_to_id?: string },
      token?: string | null,
    ) =>
      apiFetch<Message>(`/api/channels/${channelId}/messages`, token, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    update: (
      messageId: string,
      payload: { content: string },
      token?: string | null,
    ) =>
      apiFetch<Message>(`/api/messages/${messageId}`, token, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    delete: (messageId: string, token?: string | null) =>
      apiFetch<void>(`/api/messages/${messageId}`, token, { method: 'DELETE' }),
  },

  users: {
    me: (token?: string | null) => apiFetch<User>('/api/users/me', token),
    detail: (id: string, token?: string | null) =>
      apiFetch<User>(`/api/users/${id}`, token),
  },
} as const

export { ApiError }
