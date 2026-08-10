import Container from 'react-bootstrap/Container';
import Nav from 'react-bootstrap/Nav';
import Navbar from 'react-bootstrap/Navbar';
import { Link, Outlet } from 'react-router-dom';

// Shared chrome for public pages (Landing, Login, 404): a simple header
// with the app brand and a sign-in link. Chat/Profile use AppLayout instead.
export default function PublicLayout() {
  return (
    <div className="d-flex flex-column min-vh-100">
      <Navbar bg="dark" data-bs-theme="dark">
        <Container>
          <Navbar.Brand as={Link} to="/">
            AI Chatbot
          </Navbar.Brand>
          <Nav className="ms-auto">
            <Nav.Link as={Link} to="/login">
              Sign in
            </Nav.Link>
          </Nav>
        </Container>
      </Navbar>
      <div className="flex-grow-1 d-flex flex-column">
        <Outlet />
      </div>
    </div>
  );
}
