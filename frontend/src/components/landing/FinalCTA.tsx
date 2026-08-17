import { Link } from 'react-router-dom';

import { useScrollReveal } from '../../hooks/useScrollReveal';

export default function FinalCTA() {
  const { ref, isVisible } = useScrollReveal<HTMLDivElement>();

  return (
    <section className="landing-section pt-0">
      <div className="container">
        <div ref={ref} className={`landing-cta-panel reveal-scale reveal ${isVisible ? 'is-visible' : ''}`}>
          <span className="landing-eyebrow">Ready when you are</span>
          <h2 className="landing-section-heading mx-auto" style={{ maxWidth: '18ch' }}>
            Your conversations. Your documents. The web. One workspace.
          </h2>
          <p className="landing-section-body mx-auto mb-4" style={{ maxWidth: '42ch' }}>
            Sign in with Google and pick up right where you left off — or start something new.
          </p>
          <Link to="/login" className="landing-btn-primary">
            Start Chatting
          </Link>
        </div>
      </div>
    </section>
  );
}
