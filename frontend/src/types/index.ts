// Shared TypeScript types mirroring backend Pydantic schemas

export interface User {
  id: string
  email: string
  name: string
  avatar_url: string | null
  created_at: string
  updated_at: string
}

export type MemberRole = 'owner' | 'admin' | 'member'

export interface Member {
  user_id: string
  channel_id: string
  role: MemberRole
  joined_at: string
}

export interface Channel {
  id: string
  name: string
  description: string | null
  is_dm: boolean
  created_by: string
  created_at: string
  updated_at: string
}

export interface ChannelDetail extends Channel {
  members: Member[]
}

export interface Message {
  id: string
  channel_id: string
  user_id: string
  content: string
  reply_to_id: string | null
  edited_at: string | null
  created_at: string
  /** Client-only: true while awaiting server confirmation. */
  pending?: boolean
  /** Client-only: true if WS send failed. */
  failed?: boolean
}

export interface MessageListResponse {
  messages: Message[]
  has_more: boolean
}

// ---------------------------------------------------------------------------
// WebSocket event types (mirrors backend schemas/ws.py WSMessageType)
// ---------------------------------------------------------------------------

export type WSMessageType =
  | 'message.new'
  | 'message.edit'
  | 'message.delete'
  | 'message.reaction'
  | 'typing.start'
  | 'typing.stop'
  | 'presence.join'
  | 'presence.leave'
  | 'error'

export interface WSEnvelope<T = unknown> {
  type: WSMessageType
  payload: T
}

export interface WSMessageNewPayload {
  id: string
  channel_id: string
  user_id: string
  content: string
  reply_to_id: string | null
  edited_at: string | null
  created_at: string
}

export interface WSMessageEditPayload {
  message_id: string
  content: string
  edited_at: string
}

export interface WSMessageDeletePayload {
  message_id: string
}

export interface WSTypingPayload {
  user_id: string
  user_name: string
}

export interface WSPresencePayload {
  user_id: string
  user_name: string
}

export interface WSErrorPayload {
  message: string
}
