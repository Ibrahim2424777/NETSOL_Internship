import { useEffect, useRef } from 'react';

import { DRAFT_MESSAGE_ID } from '../../hooks/useSendMessage';
import type { Message } from '../../types';
import MessageBubble from './MessageBubble';
import TypingIndicator from './TypingIndicator';

interface MessageListProps {
  messages: Message[];
  isWaitingForReply: boolean;
}

export default function MessageList({ messages, isWaitingForReply }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastMessage = messages[messages.length - 1];

  // Re-runs on every streamed chunk too, not just when a message is added -
  // lastMessage.content changes on each chunk while the assistant's reply
  // is still streaming in, and we want to keep following it.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, lastMessage?.content]);

  if (messages.length === 0 && !isWaitingForReply) {
    return (
      <div className="d-flex flex-grow-1 align-items-center justify-content-center text-secondary">
        <p className="mb-0">Send a message to start the conversation.</p>
      </div>
    );
  }

  return (
    <div className="flex-grow-1 overflow-y-auto px-3 py-3">
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} isStreaming={message.id === DRAFT_MESSAGE_ID} />
      ))}
      {isWaitingForReply && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  );
}
