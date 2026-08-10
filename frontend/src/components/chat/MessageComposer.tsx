import { useState } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';

interface MessageComposerProps {
  onSend: (content: string) => void;
  disabled: boolean;
}

export default function MessageComposer({ onSend, disabled }: MessageComposerProps) {
  const [value, setValue] = useState('');

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue('');
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
    <Form onSubmit={handleSubmit} className="border-top p-3 flex-shrink-0">
      <div className="d-flex gap-2 align-items-end">
        <Form.Control
          as="textarea"
          rows={1}
          placeholder="Message the assistant…"
          value={value}
          disabled={disabled}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          style={{ resize: 'none' }}
        />
        <Button type="submit" disabled={disabled || !value.trim()}>
          Send
        </Button>
      </div>
    </Form>
  );
}
