import { Link, Outlet } from 'react-router-dom';

// Shared chrome for public pages (Landing, Login, 404): a simple header
// with the app brand and a sign-in link. Chat/Profile use AppLayout instead.
export default function PublicLayout() {
  return (
    <div className="d-flex flex-column min-vh-100">
      <header className="chat-header d-flex align-items-center px-3 py-2 flex-shrink-0">
        <Link to="/" className="d-flex align-items-center gap-2 text-decoration-none">
          <span className="brand-mark" aria-hidden="true">
            ✦
          </span>
          <span className="fw-semibold text-body">My AI</span>
        </Link>
        <Link to="/login" className="btn btn-sm btn-outline-secondary ms-auto">
          Sign in
        </Link>
      </header>
      <div className="flex-grow-1 d-flex flex-column">
        <Outlet />
      </div>
    </div>
  );
}
