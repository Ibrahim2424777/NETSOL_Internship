// Mirrors backend/app/schemas/*.py response shapes exactly. Timestamps are
// ISO strings on the wire (not Date objects) - format at render time.

export type MessageRole = 'user' | 'assistant' | 'system';

export interface User {
  id: string;
  email: string;
  name: string;
  profile_picture: string | null;
  created_at: string;
}

export interface Chat {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  chat_id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

// The SSE payloads sent by POST /chats/{chatId}/messages - see
// backend/app/api/v1/endpoints/messages.py's _sse() calls.
export type ChatStreamEvent =
  | { type: 'user_message'; message: Message }
  | { type: 'chunk'; content: string }
  | { type: 'done'; message: Message }
  | { type: 'error'; detail: string };
