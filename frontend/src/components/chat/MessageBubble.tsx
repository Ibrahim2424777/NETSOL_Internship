import { Suspense, lazy, memo } from 'react';

import type { Message } from '../../types';

// Lazy-loaded: react-markdown + remark-gfm + react-syntax-highlighter (with
// its language grammars) are the single heaviest dependency in this app,
// and Landing/Login/an-empty-chat never need any of it. Splitting it into
// its own chunk keeps it out of the initial bundle entirely - it only
// downloads the first time an assistant message actually needs rendering.
const MarkdownMessage = lazy(() => import('./MarkdownMessage'));

interface MessageBubbleProps {
  message: Message;
  // True only for the single assistant message currently streaming in -
  // shows a blinking cursor at the end, removed once it's finalized.
  isStreaming?: boolean;
}

// User messages render as plain text (white-space: pre-wrap preserves the
// line breaks they actually typed). Assistant messages render as Markdown -
// that's the convention this mirrors (ChatGPT/Claude etc.): a model is
// likely to format its replies, a human typing a chat message generally
// isn't trying to write Markdown.
//
// Wrapped in memo(): during streaming, useSendMessage.ts replaces the whole
// messages array on every chunk, but only the in-progress draft message's
// object reference actually changes - every other message in the list keeps
// its old reference. Without memo, React would still re-render every bubble
// in a long conversation on every single chunk; with it, only the draft's
// bubble does.
function MessageBubble({ message, isStreaming = false }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <div className={`d-flex mb-3 ${isUser ? 'justify-content-end' : 'justify-content-start'}`}>
      <div
        className={`message-bubble px-3 py-2 rounded-3 ${isUser ? 'bg-primary text-white' : 'bg-body-secondary'}`}
        style={{ wordBreak: 'break-word' }}
      >
        {isUser ? (
          <span style={{ whiteSpace: 'pre-wrap' }}>{message.content}</span>
        ) : (
          <>
            <Suspense fallback={<span style={{ whiteSpace: 'pre-wrap' }}>{message.content}</span>}>
              <MarkdownMessage content={message.content} />
            </Suspense>
            {isStreaming && <span className="streaming-cursor" aria-hidden="true" />}
          </>
        )}
      </div>
    </div>
  );
}

export default memo(MessageBubble);
