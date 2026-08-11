import Alert from 'react-bootstrap/Alert';
import Button from 'react-bootstrap/Button';
import { useParams } from 'react-router-dom';

import ChatSidebar from '../components/chat/ChatSidebar';
import MessageComposer from '../components/chat/MessageComposer';
import MessageList from '../components/chat/MessageList';
import { useSidebar } from '../context/SidebarContext';
import { useMessages } from '../hooks/useMessages';
import { DRAFT_MESSAGE_ID, useSendMessage } from '../hooks/useSendMessage';

export default function ChatPage() {
  const { chatId } = useParams<{ chatId: string }>();
  const { showSidebar, sidebarCollapsed, closeMobileSidebar } = useSidebar();

  return (
    <div className="d-flex h-100">
      <div className={`sidebar-collapse-wrapper ${sidebarCollapsed ? 'is-collapsed' : ''}`}>
        <ChatSidebar activeChatId={chatId} show={showSidebar} onHide={closeMobileSidebar} />
      </div>
      <div className="d-flex flex-column flex-grow-1" style={{ minWidth: 0 }}>
        {chatId ? <ActiveConversation chatId={chatId} /> : <EmptyState />}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex-grow-1 d-flex flex-column align-items-center justify-content-center text-center px-3">
      <div className="empty-state-mark d-flex align-items-center justify-content-center mb-3">✦</div>
      <h1 className="h4 fw-semibold mb-1">How can I help?</h1>
      <p className="text-secondary mb-0">Select a conversation, or start a new one.</p>
    </div>
  );
}

function ActiveConversation({ chatId }: { chatId: string }) {
  const { data: messages, isLoading, isError, refetch } = useMessages(chatId);
  const { sendMessage, isStreaming, error, dismissError } = useSendMessage(chatId);

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
        <Alert variant="danger" className="mx-3 mb-0" dismissible onClose={dismissError}>
          {error}
        </Alert>
      )}
      <MessageComposer onSend={sendMessage} disabled={isStreaming} />
    </>
  );
}
