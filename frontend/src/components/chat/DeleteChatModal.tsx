import Button from 'react-bootstrap/Button';
import Modal from 'react-bootstrap/Modal';

import type { Chat } from '../../types';

interface DeleteChatModalProps {
  chat: Chat | null;
  isDeleting: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export default function DeleteChatModal({ chat, isDeleting, onClose, onConfirm }: DeleteChatModalProps) {
  return (
    <Modal show={chat !== null} onHide={onClose} centered>
      <Modal.Header closeButton>
        <Modal.Title as="h6">Delete chat</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        Delete <strong>{chat?.title}</strong>? This permanently removes the conversation and all its
        messages.
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="danger" onClick={onConfirm} disabled={isDeleting}>
          {isDeleting ? 'Deleting…' : 'Delete'}
        </Button>
      </Modal.Footer>
    </Modal>
  );
}
