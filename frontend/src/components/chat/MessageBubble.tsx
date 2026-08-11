import { Suspense, lazy, memo } from 'react';

import type { Message } from '../../types';
import { DocumentIcon } from '../icons';

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

// User messages render as a right-aligned gradient bubble (a human typing a
// chat message generally isn't trying to write Markdown, so plain text with
// preserved line breaks is enough). Assistant messages render left-aligned
// as flowing content with a small avatar/label instead of a boxed bubble -
// the reply is the primary content, not something competing visually with
// the user's own messages - mirroring the convention most modern AI chat
// products (ChatGPT/Claude) use.
//
// Wrapped in memo(): during streaming, useSendMessage.ts replaces the whole
// messages array on every chunk, but only the in-progress draft message's
// object reference actually changes - every other message in the list keeps
// its old reference. Without memo, React would still re-render every bubble
// in a long conversation on every single chunk; with it, only the draft's
// bubble does.
function MessageBubble({ message, isStreaming = false }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="d-flex justify-content-end mb-4 message-enter">
        <div className="message-bubble message-bubble-user px-3 py-2">
          <span style={{ whiteSpace: 'pre-wrap' }}>{message.content}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-4 message-enter" style={{ maxWidth: '75ch' }}>
      <div className="d-flex align-items-center gap-2 mb-2">
        <span className="assistant-avatar d-inline-flex align-items-center justify-content-center" aria-hidden="true">
          ✦
        </span>
        <span className="small fw-medium text-secondary">Assistant</span>
      </div>
      <div className="message-bubble-assistant ps-1">
        <Suspense fallback={<span style={{ whiteSpace: 'pre-wrap' }}>{message.content}</span>}>
          <MarkdownMessage content={message.content} />
        </Suspense>
        {isStreaming && <span className="streaming-cursor" aria-hidden="true" />}
        {!isStreaming && message.sources && message.sources.length > 0 && (
          <div className="sources-panel mt-3 pt-2">
            <div className="sources-panel-title mb-1">Sources</div>
            {message.sources.map((s, i) => (
              <div className="source-chip" key={i}>
                <DocumentIcon className="flex-shrink-0" />
                <span>
                  {s.source}
                  {s.page != null && <span className="text-muted"> · p. {s.page}</span>}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default memo(MessageBubble);
