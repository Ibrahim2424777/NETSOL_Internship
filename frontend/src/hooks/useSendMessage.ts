import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useRef, useState } from 'react';

import { streamChatMessage } from '../services/chatStream';
import type { Message } from '../types';
import { chatKeys, messageKeys } from './queryKeys';

// A stable placeholder id for the assistant's in-progress reply, so it can
// be found and replaced (by onDone) or removed (on error) in the cache.
// Only one send can be in flight per chat at a time - the composer disables
// itself while isStreaming is true - so this doesn't need to be unique
// beyond that. Exported so callers (ChatPage) can tell "streaming, but no
// content yet" (show a loading indicator) apart from "streaming, draft
// bubble already visible" without duplicating this string.
export const DRAFT_MESSAGE_ID = 'assistant-draft';

export function useSendMessage(chatId: string) {
  const queryClient = useQueryClient();
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const appendMessage = useCallback(
    (message: Message) => {
      queryClient.setQueryData<Message[]>(messageKeys.list(chatId), (old = []) => [...old, message]);
    },
    [chatId, queryClient],
  );

  const upsertDraft = useCallback(
    (content: string) => {
      queryClient.setQueryData<Message[]>(messageKeys.list(chatId), (old = []) => {
        const withoutDraft = old.filter((m) => m.id !== DRAFT_MESSAGE_ID);
        const draft: Message = {
          id: DRAFT_MESSAGE_ID,
          chat_id: chatId,
          role: 'assistant',
          content,
          timestamp: new Date().toISOString(),
        };
        return [...withoutDraft, draft];
      });
    },
    [chatId, queryClient],
  );

  const removeDraft = useCallback(() => {
    queryClient.setQueryData<Message[]>(messageKeys.list(chatId), (old = []) =>
      old.filter((m) => m.id !== DRAFT_MESSAGE_ID),
    );
  }, [chatId, queryClient]);

  // Un-sends a specific message (the user's, per removed_message_id on the
  // error event) - the backend has already deleted its own copies (Redis +
  // Postgres) by the time this event arrives, so this just brings the UI
  // back in sync with that, rather than leaving a question visible that
  // never actually got answered.
  const removeMessageById = useCallback(
    (id: string) => {
      queryClient.setQueryData<Message[]>(messageKeys.list(chatId), (old = []) =>
        old.filter((m) => m.id !== id),
      );
    },
    [chatId, queryClient],
  );

  const sendMessage = useCallback(
    async (content: string, webSearch = false) => {
      setError(null);
      setIsStreaming(true);
      let draft = '';
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        await streamChatMessage(
          chatId,
          content,
          webSearch,
          {
            onUserMessage: (event) => appendMessage(event.message),
            onChunk: (event) => {
              draft += event.content;
              upsertDraft(draft);
            },
            onDone: (event) => {
              // route is transient (Phase 14) - only ever known for the
              // message just streamed in, so it's attached here rather than
              // coming from the message object itself.
              const message: Message =
                event.route != null ? { ...event.message, route: event.route } : event.message;
              queryClient.setQueryData<Message[]>(messageKeys.list(chatId), (old = []) => [
                ...old.filter((m) => m.id !== DRAFT_MESSAGE_ID),
                message,
              ]);
              // The chat's title/updated_at may have changed (sidebar
              // ordering bumps on every message) - refetch the list.
              queryClient.invalidateQueries({ queryKey: chatKeys.list() });
            },
            onError: (detail, removedMessageId) => {
              removeDraft();
              if (removedMessageId) {
                removeMessageById(removedMessageId);
              }
              setError(detail);
            },
          },
          controller.signal,
        );
      } catch (err) {
        if (!controller.signal.aborted) {
          removeDraft();
          setError(err instanceof Error ? err.message : 'Something went wrong sending your message.');
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [chatId, appendMessage, upsertDraft, removeDraft, removeMessageById, queryClient],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const dismissError = useCallback(() => {
    setError(null);
  }, []);

  return { sendMessage, cancel, isStreaming, error, dismissError };
}
