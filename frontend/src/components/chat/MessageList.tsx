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
      <div className="flex-grow-1 d-flex flex-column align-items-center justify-content-center text-center px-3">
        <div className="empty-state-mark d-flex align-items-center justify-content-center mb-3">✦</div>
        <h1 className="h4 fw-semibold mb-1">How can I help?</h1>
        <p className="text-secondary mb-0">Ask a question to start this conversation.</p>
      </div>
    );
  }

  return (
    <div className="flex-grow-1 overflow-y-auto px-3 py-4">
      {/* Scrollbar spans the full width; only the content column is
          constrained, so lines stay a comfortable reading length on wide
          screens without the scroll container itself looking indented. */}
      <div style={{ maxWidth: 900, margin: '0 auto' }}>
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} isStreaming={message.id === DRAFT_MESSAGE_ID} />
        ))}
        {isWaitingForReply && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
