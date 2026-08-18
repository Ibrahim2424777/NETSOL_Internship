import { Suspense, lazy, memo } from 'react';

import type { Message } from '../../types';
import { CloudIcon, DocumentIcon, GlobeIcon, MailIcon, SparkleIcon } from '../icons';

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

// Maps MCP tool names (agent_node.py's tools_used) to a short, human label
// and icon for the tool-use indicator (Phase 17 doc section 20 - "small
// polished indicator", not a raw list of function names). Grouped by
// category (weather/email) rather than shown per-tool, so e.g. a turn that
// called both get_current_weather and get_weather_forecast still shows one
// chip, not two identical-looking "weather" chips.
const TOOL_CATEGORIES: { label: string; icon: typeof CloudIcon; tools: string[] }[] = [
  { label: 'Checked the weather', icon: CloudIcon, tools: ['get_current_weather', 'get_weather_forecast'] },
  { label: 'Sent an email', icon: MailIcon, tools: ['send_email'] },
  { label: 'Checked your email', icon: MailIcon, tools: ['list_recent_emails', 'read_email'] },
];

function toolIndicators(toolsUsed: string[]): { label: string; icon: typeof CloudIcon }[] {
  const used = new Set(toolsUsed);
  const indicators: { label: string; icon: typeof CloudIcon }[] = TOOL_CATEGORIES.filter((category) =>
    category.tools.some((tool) => used.has(tool)),
  ).map(({ label, icon }) => ({ label, icon }));
  const known = new Set(TOOL_CATEGORIES.flatMap((category) => category.tools));
  if (toolsUsed.some((tool) => !known.has(tool))) {
    indicators.push({ label: 'Used a tool', icon: SparkleIcon });
  }
  return indicators;
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

  const indicators = message.toolsUsed && message.toolsUsed.length > 0 ? toolIndicators(message.toolsUsed) : [];

  return (
    <div className="mb-4 message-enter" style={{ maxWidth: '75ch' }}>
      <div className="d-flex align-items-center gap-2 mb-2">
        <span className="assistant-avatar d-inline-flex align-items-center justify-content-center" aria-hidden="true">
          ✦
        </span>
        <span className="small fw-medium text-secondary">Assistant</span>
        {indicators.map(({ label, icon: Icon }) => (
          <span className="tool-use-chip d-inline-flex align-items-center gap-1" key={label}>
            <Icon className="flex-shrink-0" />
            {label}
          </span>
        ))}
      </div>
      <div className="message-bubble-assistant ps-1">
        <Suspense fallback={<span style={{ whiteSpace: 'pre-wrap' }}>{message.content}</span>}>
          <MarkdownMessage content={message.content} />
        </Suspense>
        {isStreaming && <span className="streaming-cursor" aria-hidden="true" />}
        {/* One list, two kinds of entries: RAG document chunks (page, no
            url) and web search citations (url, no page) - see
            MessageSource. A source's own shape (not message.route) decides
            how each chip renders, so this stays correct even if a future
            route mixes both in one reply. */}
        {!isStreaming && message.sources && message.sources.length > 0 && (
          <div className="sources-panel mt-3 pt-2">
            <div className="sources-panel-title mb-1">Sources</div>
            {message.sources.map((s, i) => (
              <div className="source-chip" key={i}>
                {s.url ? <GlobeIcon className="flex-shrink-0" /> : <DocumentIcon className="flex-shrink-0" />}
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noopener noreferrer">
                    {s.source}
                  </a>
                ) : (
                  <span>
                    {s.source}
                    {s.page != null && <span className="text-muted"> · p. {s.page}</span>}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default memo(MessageBubble);
