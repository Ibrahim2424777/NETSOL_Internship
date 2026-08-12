// Mirrors backend/app/schemas/*.py response shapes exactly. Timestamps are
// ISO strings on the wire (not Date objects) - format at render time.

export type MessageRole = 'user' | 'assistant' | 'system';

// Which capability answered a given turn (Phase 14, "sports" replaced with
// "web_search" in Phase 14.6). Only ever attached client-side to the 'done'
// SSE event for the message just received; never persisted, so it's absent
// again after a page refresh (see messages.py's _route_taken).
export type MessageRoute = 'normal' | 'rag' | 'web_search';

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
  // Present only for web search sources (Phase 14.6) - a clickable link to
  // the cited page. Null/absent for RAG document sources.
  url?: string | null;
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
  // Transient client-side annotation (Phase 14) - see MessageRoute above.
  // Never comes from the REST API, only attached in-memory when a 'done'
  // SSE event arrives, so it's absent for messages loaded via GET.
  route?: MessageRoute | null;
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
  | { type: 'done'; message: Message; route?: MessageRoute | null }
  // removed_message_id is set when the user's message was un-sent because
  // the assistant failed to respond - the id to remove from the UI so a
  // retry doesn't look like the same question was sent twice.
  | { type: 'error'; detail: string; removed_message_id?: string };
