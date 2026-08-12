import { useLayoutEffect, useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import Form from 'react-bootstrap/Form';

import { GlobeIcon, SendIcon } from '../icons';

interface MessageComposerProps {
  onSend: (content: string, webSearch: boolean) => void;
  disabled: boolean;
}

export default function MessageComposer({ onSend, disabled }: MessageComposerProps) {
  const [value, setValue] = useState('');
  // Per-message, not a chat-level setting - resets after each send rather
  // than staying "on" for the rest of the conversation, so it's a deliberate
  // choice every time rather than an easy-to-forget sticky mode.
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grows with content up to CSS's max-height (200px, then scrolls) -
  // resetting to 'auto' first is what lets the browser recompute a
  // *smaller* scrollHeight too, e.g. after deleting several lines of text.
  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [value]);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed, webSearchEnabled);
    setValue('');
    setWebSearchEnabled(false);
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends, Shift+Enter inserts a newline - the standard chat-app convention.
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <Form onSubmit={handleSubmit} className="composer-shell p-3 flex-shrink-0">
      <div className="composer d-flex align-items-end gap-2">
        <Form.Control
          ref={textareaRef}
          as="textarea"
          rows={1}
          placeholder="Ask anything..."
          value={value}
          disabled={disabled}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          className="composer-textarea"
        />
        <button
          type="submit"
          className="composer-send-btn"
          disabled={disabled || !value.trim()}
          aria-label="Send message"
        >
          <SendIcon />
        </button>
      </div>
      <div className="d-flex mt-2">
        <button
          type="button"
          className={`composer-tool-toggle d-inline-flex align-items-center gap-1 ${webSearchEnabled ? 'is-active' : ''}`}
          disabled={disabled}
          onClick={() => setWebSearchEnabled((enabled) => !enabled)}
          aria-pressed={webSearchEnabled}
        >
          <GlobeIcon />
          <span>Web search</span>
        </button>
      </div>
    </Form>
  );
}
