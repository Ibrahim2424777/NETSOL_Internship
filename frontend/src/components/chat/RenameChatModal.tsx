import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import Modal from 'react-bootstrap/Modal';

import type { Chat } from '../../types';

interface RenameChatModalProps {
  chat: Chat | null;
  isSaving: boolean;
  onClose: () => void;
  onConfirm: (title: string) => void;
}

export default function RenameChatModal({ chat, isSaving, onClose, onConfirm }: RenameChatModalProps) {
  const [title, setTitle] = useState('');

  // Re-seed the input whenever a different chat is opened for renaming.
  useEffect(() => {
    if (chat) setTitle(chat.title);
  }, [chat]);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = title.trim();
    if (trimmed) onConfirm(trimmed);
  };

  return (
    <Modal show={chat !== null} onHide={onClose} centered>
      <Form onSubmit={handleSubmit}>
        <Modal.Header closeButton>
          <Modal.Title as="h6">Rename chat</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form.Control
            autoFocus
            value={title}
            maxLength={255}
            onChange={(event) => setTitle(event.target.value)}
          />
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={isSaving || !title.trim()}>
            Save
          </Button>
        </Modal.Footer>
      </Form>
    </Modal>
  );
}
