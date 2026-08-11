// Sends a message and consumes the Server-Sent Events stream from
// POST /chats/{chatId}/messages (backend/app/api/v1/endpoints/messages.py).
//
// This is the one call in the app that uses fetch() instead of the shared
// Axios client: reading a streaming response body chunk-by-chunk via
// ReadableStream is what fetch is good at, and Axios's browser adapter
// doesn't offer a meaningfully better story for it - so rather than fight
// the tool, this one call is hand-rolled, including its own auth-retry
// logic (mirroring apiClient's interceptor) since it can't benefit from
// Axios's interceptors.
import { refreshAccessToken } from './authRefresh';
import { getAuthState } from './authStore';
import type { ChatStreamEvent } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export interface StreamCallbacks {
  onUserMessage?: (event: Extract<ChatStreamEvent, { type: 'user_message' }>) => void;
  onChunk?: (event: Extract<ChatStreamEvent, { type: 'chunk' }>) => void;
  onDone?: (event: Extract<ChatStreamEvent, { type: 'done' }>) => void;
  onError?: (detail: string, removedMessageId?: string) => void;
}

async function postMessage(chatId: string, content: string, token: string | null, signal?: AbortSignal) {
  return fetch(`${API_BASE_URL}/chats/${chatId}/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    credentials: 'include',
    body: JSON.stringify({ content }),
    signal,
  });
}

export async function streamChatMessage(
  chatId: string,
  content: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  let response = await postMessage(chatId, content, getAuthState().accessToken, signal);

  if (response.status === 401) {
    const newToken = await refreshAccessToken();
    response = await postMessage(chatId, content, newToken, signal);
  }

  if (!response.ok || !response.body) {
    callbacks.onError?.(await extractErrorDetail(response));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      dispatchEvent(rawEvent, callbacks);
      boundary = buffer.indexOf('\n\n');
    }
  }
}

function dispatchEvent(rawEvent: string, callbacks: StreamCallbacks): void {
  const dataLine = rawEvent
    .split('\n')
    .find((line) => line.startsWith('data: '));
  if (!dataLine) return;

  const event = JSON.parse(dataLine.slice('data: '.length)) as ChatStreamEvent;
  switch (event.type) {
    case 'user_message':
      callbacks.onUserMessage?.(event);
      break;
    case 'chunk':
      callbacks.onChunk?.(event);
      break;
    case 'done':
      callbacks.onDone?.(event);
      break;
    case 'error':
      callbacks.onError?.(event.detail, event.removed_message_id);
      break;
  }
}

async function extractErrorDetail(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: string };
    return data.detail ?? `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}
