import Spinner from 'react-bootstrap/Spinner';
import { Link } from 'react-router-dom';

import { useChats } from '../../hooks/useChats';
import { formatRelativeTime } from '../../utils/timeFormat';
import { ArrowRightIcon } from '../icons';

const RECENT_LIMIT = 5;

// Real recent-conversation data (Phase 15 section 12) - reuses useChats()
// as-is rather than a new endpoint/hook: the list is already sorted
// most-recent-first by the API and already React-Query-cached from any
// earlier visit to /chat in this session, so this is just a client-side
// slice, not a second network round trip in the common case.
export default function RecentConversations() {
  const { data: chats, isLoading, isError, refetch } = useChats();
  const recent = (chats ?? []).slice(0, RECENT_LIMIT);

  return (
    <div className="landing-recent-card p-3 p-md-4">
      <div className="d-flex align-items-center justify-content-between mb-2">
        <h2 className="h6 fw-semibold mb-0" style={{ color: 'var(--ink-text)' }}>
          Recent conversations
        </h2>
        {recent.length > 0 && (
          <Link
            to="/chat"
            className="d-inline-flex align-items-center gap-1 text-decoration-none"
            style={{ color: 'var(--gold)', fontSize: '0.82rem', fontWeight: 500 }}
          >
            View all <ArrowRightIcon width="0.85em" height="0.85em" />
          </Link>
        )}
      </div>

      {isLoading && (
        <div className="text-center py-4">
          <Spinner animation="border" size="sm" style={{ color: 'var(--gold)' }} />
        </div>
      )}

      {isError && (
        <div className="text-center py-3">
          <p className="small mb-2" style={{ color: 'var(--ink-text-secondary)' }}>
            Couldn't load your conversations.
          </p>
          <button type="button" className="landing-btn-secondary py-1 px-3" onClick={() => refetch()}>
            Retry
          </button>
        </div>
      )}

      {!isLoading && !isError && recent.length === 0 && (
        <div className="text-center py-4">
          <p className="mb-3" style={{ color: 'var(--ink-text-secondary)' }}>
            No conversations yet.
          </p>
          <Link to="/chat" className="landing-btn-primary py-2 px-3">
            Start your first conversation
          </Link>
        </div>
      )}

      {!isLoading &&
        !isError &&
        recent.map((chat) => (
          <Link key={chat.id} to={`/chat/${chat.id}`} className="landing-recent-item">
            <span className="landing-recent-item-title">{chat.title}</span>
            <span className="landing-recent-item-time">{formatRelativeTime(chat.updated_at)}</span>
          </Link>
        ))}
    </div>
  );
}
