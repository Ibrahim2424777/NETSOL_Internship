import { Link, Outlet, useLocation } from 'react-router-dom';

// Shared chrome for public pages (Login, 404): a simple header with the app
// brand and a sign-in link. Chat/Profile use AppLayout instead.
//
// `/` (LandingPage) is the one exception, in BOTH its auth states: the
// logged-out marketing page has its own full navbar (LandingHeader, styled
// for the black/gold landing design system) and the logged-in personalized
// page has its own header+sidebar shell (PersonalizedHeader) - either way,
// stacking this layout's plain "Sign in" header above either would just be
// a redundant/mismatched second header. So this layout steps out of the way
// entirely for `/` and lets LandingPage own 100% of its own chrome.
export default function PublicLayout() {
  const location = useLocation();
  const isLandingPage = location.pathname === '/';

  if (isLandingPage) {
    return <Outlet />;
  }

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
