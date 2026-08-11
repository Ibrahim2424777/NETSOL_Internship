import Dropdown from 'react-bootstrap/Dropdown';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';

import { SidebarIcon } from '../components/icons';
import { useAuth } from '../context/AuthContext';
import { SidebarProvider, useSidebar } from '../context/SidebarContext';

// Shared chrome for every authenticated page (Chat, Profile): one slim
// header with the sidebar toggle, brand, and a Profile/Logout menu. The
// page itself renders into <Outlet /> below it. SidebarProvider lives here
// (not inside ChatPage) so this header's toggle button and ChatPage's
// actual sidebar can share state without a parent/child relationship.
export default function AppLayout() {
  return (
    <SidebarProvider>
      <div className="d-flex flex-column vh-100">
        <Header />
        {/* minHeight: 0 overrides flexbox's default min-height: auto, which
            would otherwise let this child grow past the viewport instead of
            letting its own contents (the chat page's message list) scroll
            internally - not a standard Bootstrap utility, hence the inline style. */}
        <div className="flex-grow-1" style={{ minHeight: 0 }}>
          <Outlet />
        </div>
      </div>
    </SidebarProvider>
  );
}

function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { toggleSidebar } = useSidebar();
  const onChatRoute = location.pathname.startsWith('/chat');

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <header className="chat-header d-flex align-items-center gap-2 px-3 py-2 flex-shrink-0">
      {onChatRoute && (
        <button
          type="button"
          className="sidebar-icon-btn"
          onClick={toggleSidebar}
          aria-label="Toggle sidebar"
        >
          <SidebarIcon />
        </button>
      )}
      <Link to="/chat" className="d-flex align-items-center gap-2 text-decoration-none">
        <span className="brand-mark" aria-hidden="true">
          ✦
        </span>
        <span className="fw-semibold text-body">My AI</span>
      </Link>

      <Dropdown align="end" className="ms-auto">
        <Dropdown.Toggle
          as="button"
          className="btn d-flex align-items-center gap-2 border-0 bg-transparent p-1"
          id="user-menu"
        >
          {user?.profile_picture ? (
            <img
              src={user.profile_picture}
              alt=""
              width={30}
              height={30}
              className="rounded-circle"
              referrerPolicy="no-referrer"
            />
          ) : (
            <span
              className="rounded-circle d-inline-flex align-items-center justify-content-center text-white"
              style={{ width: 30, height: 30, fontSize: '0.75rem', background: 'var(--app-accent-gradient)' }}
            >
              {user?.name.charAt(0).toUpperCase()}
            </span>
          )}
        </Dropdown.Toggle>
        <Dropdown.Menu>
          <Dropdown.ItemText className="text-truncate small text-secondary" style={{ maxWidth: 200 }}>
            {user?.email}
          </Dropdown.ItemText>
          <Dropdown.Divider />
          <Dropdown.Item as={Link} to="/profile">
            Profile
          </Dropdown.Item>
          <Dropdown.Item onClick={handleLogout}>Log out</Dropdown.Item>
        </Dropdown.Menu>
      </Dropdown>
    </header>
  );
}
