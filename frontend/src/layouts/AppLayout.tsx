import Container from 'react-bootstrap/Container';
import Dropdown from 'react-bootstrap/Dropdown';
import Nav from 'react-bootstrap/Nav';
import Navbar from 'react-bootstrap/Navbar';
import { Link, Outlet, useNavigate } from 'react-router-dom';

import { useAuth } from '../context/AuthContext';

// Shared chrome for every authenticated page (Chat, Profile): a top navbar
// with the current user's avatar/name and a Profile/Logout menu. The page
// itself renders into <Outlet /> below it.
export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="d-flex flex-column vh-100">
      <Navbar bg="dark" data-bs-theme="dark" className="border-bottom border-secondary-subtle flex-shrink-0">
        <Container fluid className="px-3">
          <Navbar.Brand as={Link} to="/chat">
            AI Chatbot
          </Navbar.Brand>
          <Nav className="ms-auto">
            <Dropdown align="end">
              <Dropdown.Toggle
                as="button"
                className="btn btn-dark d-flex align-items-center gap-2 border-0"
                id="user-menu"
              >
                {user?.profile_picture ? (
                  <img
                    src={user.profile_picture}
                    alt=""
                    width={28}
                    height={28}
                    className="rounded-circle"
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <span
                    className="rounded-circle bg-secondary d-inline-flex align-items-center justify-content-center"
                    style={{ width: 28, height: 28, fontSize: '0.75rem' }}
                  >
                    {user?.name.charAt(0).toUpperCase()}
                  </span>
                )}
                <span>{user?.name}</span>
              </Dropdown.Toggle>
              <Dropdown.Menu>
                <Dropdown.Item as={Link} to="/profile">
                  Profile
                </Dropdown.Item>
                <Dropdown.Divider />
                <Dropdown.Item onClick={handleLogout}>Log out</Dropdown.Item>
              </Dropdown.Menu>
            </Dropdown>
          </Nav>
        </Container>
      </Navbar>
      {/* minHeight: 0 overrides flexbox's default min-height: auto, which
          would otherwise let this child grow past the viewport instead of
          letting its own contents (the chat page's message list) scroll
          internally - not a standard Bootstrap utility, hence the inline style. */}
      <div className="flex-grow-1" style={{ minHeight: 0 }}>
        <Outlet />
      </div>
    </div>
  );
}
