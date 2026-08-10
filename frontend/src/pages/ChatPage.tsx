import { useState } from 'react';
import Alert from 'react-bootstrap/Alert';
import Button from 'react-bootstrap/Button';
import { useParams } from 'react-router-dom';

import ChatSidebar from '../components/chat/ChatSidebar';
import MessageComposer from '../components/chat/MessageComposer';
import MessageList from '../components/chat/MessageList';
import { useChat } from '../hooks/useChats';
import { useMessages } from '../hooks/useMessages';
import { DRAFT_MESSAGE_ID, useSendMessage } from '../hooks/useSendMessage';

export default function ChatPage() {
  const { chatId } = useParams<{ chatId: string }>();
  const [showSidebar, setShowSidebar] = useState(false);

  return (
    <div className="d-flex h-100">
      <ChatSidebar activeChatId={chatId} show={showSidebar} onHide={() => setShowSidebar(false)} />
      <div className="d-flex flex-column flex-grow-1" style={{ minWidth: 0 }}>
        {/* Sidebar is an off-canvas overlay below the md breakpoint (see
            ChatSidebar's use of Offcanvas's responsive prop), so on small
            screens there's no other way to reach it without this. */}
        <MobileHeader chatId={chatId} onOpenSidebar={() => setShowSidebar(true)} />
        {chatId ? <ActiveConversation chatId={chatId} /> : <EmptyState />}
      </div>
    </div>
  );
}

function MobileHeader({ chatId, onOpenSidebar }: { chatId?: string; onOpenSidebar: () => void }) {
  const { data: chat } = useChat(chatId);

  return (
    <div className="d-md-none d-flex align-items-center gap-2 border-bottom px-2 py-2 flex-shrink-0">
      <button
        type="button"
        className="btn btn-outline-secondary btn-sm"
        onClick={onOpenSidebar}
        aria-label="Open conversations"
      >
        ☰
      </button>
      <span className="text-truncate fw-medium">{chat?.title ?? 'Chat'}</span>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex-grow-1 d-flex align-items-center justify-content-center text-secondary">
      <p className="mb-0">Select a conversation, or start a new one.</p>
    </div>
  );
}

function ActiveConversation({ chatId }: { chatId: string }) {
  const { data: messages, isLoading, isError, refetch } = useMessages(chatId);
  const { sendMessage, isStreaming, error } = useSendMessage(chatId);

  const list = messages ?? [];
  // Only show the "Thinking…" indicator in the gap before the first chunk
  // arrives - once it does, the assistant's draft reply is already in the
  // list and renders as a normal (if still-growing) bubble.
  const isWaitingForFirstChunk = isStreaming && !list.some((m) => m.id === DRAFT_MESSAGE_ID);

  if (isLoading) {
    return <div className="flex-grow-1" />;
  }

  if (isError) {
    return (
      <div className="flex-grow-1 d-flex flex-column align-items-center justify-content-center gap-2 text-secondary">
        <p className="text-danger mb-0">Couldn't load this conversation.</p>
        <Button size="sm" variant="outline-secondary" onClick={() => refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <>
      <MessageList messages={list} isWaitingForReply={isWaitingForFirstChunk} />
      {error && (
        <Alert variant="danger" className="mx-3 mb-0">
          {error}
        </Alert>
      )}
      <MessageComposer onSend={sendMessage} disabled={isStreaming} />
    </>
  );
}
