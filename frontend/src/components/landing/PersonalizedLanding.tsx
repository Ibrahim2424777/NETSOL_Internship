import Spinner from 'react-bootstrap/Spinner';
import { useNavigate } from 'react-router-dom';

import ChatSidebar from '../../components/chat/ChatSidebar';
import { useAuth } from '../../context/AuthContext';
import { SidebarProvider, useSidebar } from '../../context/SidebarContext';
import { useCreateChat } from '../../hooks/useChats';
import '../../styles/landing.css';
import { getGreeting } from '../../utils/timeFormat';
import { PlusIcon } from '../icons';
import FeatureHighlights from './FeatureHighlights';
import PersonalizedHeader from './PersonalizedHeader';
import RecentConversations from './RecentConversations';

// The logged-in landing experience (Phase 15 sections 3, 12, 13) - a
// personalized dashboard rather than the marketing page, reusing the same
// ChatSidebar/SidebarProvider/collapse pattern ChatPage uses (see
// index.css's .sidebar-collapse-wrapper) so navigating a chat from here
// feels like the same app, not a different product bolted onto the front.
//
// Own SidebarProvider (not the app-wide one from AppLayout) since `/` is
// rendered through PublicLayout, not AppLayout - see PublicLayout.tsx for
// why this page gets its own full-shell treatment instead of the plain
// public header.
export default function PersonalizedLanding() {
  return (
    <SidebarProvider>
      <PersonalizedLandingShell />
    </SidebarProvider>
  );
}

function PersonalizedLandingShell() {
  const { user } = useAuth();
  const { showSidebar, sidebarCollapsed, closeMobileSidebar } = useSidebar();
  const createChat = useCreateChat();
  const navigate = useNavigate();

  const handleNewChat = async () => {
    const chat = await createChat.mutateAsync(undefined);
    navigate(`/chat/${chat.id}`);
  };

  return (
    <div className="landing-page d-flex flex-column vh-100">
      <PersonalizedHeader />
      <div className="d-flex flex-grow-1" style={{ minHeight: 0 }}>
        <div className={`sidebar-collapse-wrapper ${sidebarCollapsed ? 'is-collapsed' : ''}`}>
          <ChatSidebar show={showSidebar} onHide={closeMobileSidebar} />
        </div>

        <div className="flex-grow-1 overflow-y-auto">
          <div className="container py-4 py-md-5" style={{ maxWidth: 760 }}>
            <span className="landing-eyebrow">{getGreeting()}</span>
            <h1 className="landing-greeting mt-1 mb-2">{user?.name ?? 'there'}</h1>
            <p className="mb-4" style={{ color: 'var(--ink-text-secondary)' }}>
              Ready to continue where you left off?
            </p>

            <button
              type="button"
              className="landing-new-chat-card mb-4"
              onClick={handleNewChat}
              disabled={createChat.isPending}
            >
              {createChat.isPending ? <Spinner animation="border" size="sm" /> : <PlusIcon width="1.2em" height="1.2em" />}
              Start a new conversation
            </button>

            <RecentConversations />
            <FeatureHighlights />
          </div>
        </div>
      </div>
    </div>
  );
}
