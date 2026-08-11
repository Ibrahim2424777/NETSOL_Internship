import { useState } from 'react';
import Button from 'react-bootstrap/Button';
import Dropdown from 'react-bootstrap/Dropdown';
import Offcanvas from 'react-bootstrap/Offcanvas';
import Spinner from 'react-bootstrap/Spinner';
import { Link, useNavigate } from 'react-router-dom';

import { useChats, useCreateChat, useDeleteChat, useRenameChat } from '../../hooks/useChats';
import type { Chat } from '../../types';
import { groupChatsByDate } from '../../utils/groupChatsByDate';
import { MoreIcon, PlusIcon } from '../icons';
import DeleteChatModal from './DeleteChatModal';
import RenameChatModal from './RenameChatModal';

interface ChatSidebarProps {
  activeChatId?: string;
  // Below the `md` breakpoint the sidebar becomes a true off-canvas overlay
  // (Offcanvas's `responsive` prop - inline and always visible at md+,
  // overlay controlled by show/onHide below it) - these control that overlay.
  // Desktop collapse is a separate concern, handled by the width-animated
  // wrapper in ChatPage.tsx - this component doesn't know about it.
  show: boolean;
  onHide: () => void;
}

export default function ChatSidebar({ activeChatId, show, onHide }: ChatSidebarProps) {
  const { data: chats, isLoading, isError, refetch } = useChats();
  const createChat = useCreateChat();
  const renameChat = useRenameChat();
  const deleteChat = useDeleteChat();
  const navigate = useNavigate();

  const [chatToRename, setChatToRename] = useState<Chat | null>(null);
  const [chatToDelete, setChatToDelete] = useState<Chat | null>(null);

  const handleNewChat = async () => {
    const chat = await createChat.mutateAsync(undefined);
    onHide();
    navigate(`/chat/${chat.id}`);
  };

  const handleSelectChat = () => {
    onHide();
  };

  const handleConfirmDelete = async () => {
    if (!chatToDelete) return;
    const deletedId = chatToDelete.id;
    await deleteChat.mutateAsync(deletedId);
    setChatToDelete(null);
    if (activeChatId === deletedId) {
      navigate('/chat', { replace: true });
    }
  };

  const groups = groupChatsByDate(chats ?? []);

  return (
    <Offcanvas
      show={show}
      onHide={onHide}
      responsive="md"
      className="d-flex flex-column app-sidebar border-end"
      style={{ width: 280 }}
    >
      <Offcanvas.Header closeButton className="d-md-none">
        <Offcanvas.Title as="h6">Conversations</Offcanvas.Title>
      </Offcanvas.Header>

      <div className="p-2 flex-shrink-0">
        <Button
          className="new-chat-btn w-100 d-flex align-items-center justify-content-center gap-2"
          onClick={handleNewChat}
          disabled={createChat.isPending}
        >
          {createChat.isPending ? <Spinner animation="border" size="sm" /> : <PlusIcon />}
          New Chat
        </Button>
      </div>

      <div className="flex-grow-1 overflow-y-auto px-2">
        {isLoading && (
          <div className="text-center text-secondary py-3">
            <Spinner animation="border" size="sm" />
          </div>
        )}

        {isError && (
          <div className="text-center py-3 px-2">
            <p className="text-danger small mb-2">Couldn't load your conversations.</p>
            <Button size="sm" variant="outline-secondary" onClick={() => refetch()}>
              Retry
            </Button>
          </div>
        )}

        {!isLoading && !isError && chats?.length === 0 && (
          <p className="text-secondary small text-center mt-3">No conversations yet.</p>
        )}

        {groups.map((group) => (
          <div key={group.label} className="mb-1">
            <div className="chat-group-label">{group.label}</div>
            {group.chats.map((chat) => (
              <ChatListItem
                key={chat.id}
                chat={chat}
                active={chat.id === activeChatId}
                onSelect={handleSelectChat}
                onRename={() => setChatToRename(chat)}
                onDelete={() => setChatToDelete(chat)}
              />
            ))}
          </div>
        ))}
      </div>

      <RenameChatModal
        chat={chatToRename}
        isSaving={renameChat.isPending}
        onClose={() => setChatToRename(null)}
        onConfirm={(title) => {
          if (!chatToRename) return;
          renameChat.mutate(
            { chatId: chatToRename.id, title },
            { onSuccess: () => setChatToRename(null) },
          );
        }}
      />

      <DeleteChatModal
        chat={chatToDelete}
        isDeleting={deleteChat.isPending}
        onClose={() => setChatToDelete(null)}
        onConfirm={handleConfirmDelete}
      />
    </Offcanvas>
  );
}

function ChatListItem({
  chat,
  active,
  onSelect,
  onRename,
  onDelete,
}: {
  chat: Chat;
  active: boolean;
  onSelect: () => void;
  onRename: () => void;
  onDelete: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className={`chat-item d-flex align-items-center mb-1 ${active ? 'active' : ''}`}>
      <Link
        to={`/chat/${chat.id}`}
        onClick={onSelect}
        className="chat-item-link flex-grow-1 text-truncate px-2 py-2 text-decoration-none"
        title={chat.title}
      >
        {chat.title}
      </Link>
      <Dropdown align="end" onToggle={setMenuOpen}>
        <Dropdown.Toggle
          as="button"
          className={`btn btn-sm chat-item-menu-btn text-secondary px-2 border-0 bg-transparent ${menuOpen ? 'show' : ''}`}
          id={`chat-menu-${chat.id}`}
          aria-label="Chat options"
        >
          <MoreIcon />
        </Dropdown.Toggle>
        <Dropdown.Menu>
          <Dropdown.Item onClick={onRename}>Rename</Dropdown.Item>
          <Dropdown.Item className="text-danger" onClick={onDelete}>
            Delete
          </Dropdown.Item>
        </Dropdown.Menu>
      </Dropdown>
    </div>
  );
}
