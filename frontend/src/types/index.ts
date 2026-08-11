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

export interface MessageSource {
  source: string;
  page: number | null;
}

export interface Message {
  id: string;
  chat_id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
  // Present only on a RAG-grounded assistant reply (Phase 12) - which
  // ingested document chunks the answer drew on. Absent/null otherwise.
  sources?: MessageSource[] | null;
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
  // removed_message_id is set when the user's message was un-sent because
  // the assistant failed to respond - the id to remove from the UI so a
  // retry doesn't look like the same question was sent twice.
  | { type: 'error'; detail: string; removed_message_id?: string };
