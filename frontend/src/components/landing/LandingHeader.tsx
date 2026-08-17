import { Link } from 'react-router-dom';

// Sticky navbar for the logged-out marketing landing page. "Features" is an
// in-page anchor (not a separate route) - the doc explicitly warns against
// linking to pages that don't exist (Pricing/About/Blog), so this only ever
// links to real destinations: an in-page section and the existing login flow.
export default function LandingHeader() {
  return (
    <header className="landing-header">
      <div className="container d-flex align-items-center py-3 gap-4">
        <Link to="/" className="landing-brand">
          <span className="landing-brand-mark" aria-hidden="true">
            ✦
          </span>
          <span>My AI</span>
        </Link>

        <nav className="d-none d-md-flex align-items-center gap-4 ms-3" aria-label="Primary">
          <a href="#features" className="landing-nav-link">
            Features
          </a>
        </nav>

        <Link to="/login" className="landing-btn-primary ms-auto py-2 px-3">
          Start Chatting
        </Link>
      </div>
    </header>
  );
}
