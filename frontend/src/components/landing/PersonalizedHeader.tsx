import Dropdown from 'react-bootstrap/Dropdown';
import { Link, useNavigate } from 'react-router-dom';

import { useAuth } from '../../context/AuthContext';
import { useSidebar } from '../../context/SidebarContext';
import { SidebarIcon } from '../icons';

// Header for the personalized (logged-in) landing page - same structural
// role as AppLayout's Header (sidebar toggle, brand, user menu), reused
// here as its own small component rather than importing AppLayout's version
// directly, since that one is tied to the app's default purple theme and to
// `/chat`-specific routing logic (its toggle only shows on chat routes).
export default function PersonalizedHeader() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { toggleSidebar } = useSidebar();

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <header className="landing-personalized-header d-flex align-items-center gap-2 px-3 py-2">
      <button
        type="button"
        className="sidebar-icon-btn"
        onClick={toggleSidebar}
        aria-label="Toggle sidebar"
        style={{ color: 'var(--ink-text-secondary)' }}
      >
        <SidebarIcon />
      </button>
      <Link to="/" className="landing-brand">
        <span className="landing-brand-mark" aria-hidden="true">
          ✦
        </span>
        <span>My AI</span>
      </Link>

      <Dropdown align="end" className="ms-auto">
        <Dropdown.Toggle as="button" className="landing-user-pill" id="landing-user-menu">
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
            <span className="landing-user-avatar">{user?.name.charAt(0).toUpperCase()}</span>
          )}
        </Dropdown.Toggle>
        <Dropdown.Menu>
          <Dropdown.ItemText className="text-truncate small text-secondary" style={{ maxWidth: 200 }}>
            {user?.email}
          </Dropdown.ItemText>
          <Dropdown.Divider />
          <Dropdown.Item as={Link} to="/chat">
            Open chat
          </Dropdown.Item>
          <Dropdown.Item as={Link} to="/profile">
            Profile
          </Dropdown.Item>
          <Dropdown.Item onClick={handleLogout}>Log out</Dropdown.Item>
        </Dropdown.Menu>
      </Dropdown>
    </header>
  );
}
