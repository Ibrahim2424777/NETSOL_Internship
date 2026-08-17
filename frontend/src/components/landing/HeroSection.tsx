import { Link } from 'react-router-dom';

import { CheckIcon, DocumentIcon, GlobeIcon } from '../icons';

// The hero's visual (Phase 15 section 5, "Option A - floating chat
// interface"): a small, static mock of the actual chat UI, not a real
// screenshot or a stock image - built from the same visual language
// (rounded bubbles, gold instead of the app's purple accent) as the real
// MessageBubble/MessageComposer, so it reads as "this app", not generic
// marketing art.
function HeroVisual() {
  return (
    <div className="position-relative">
      <div
        className="landing-glow-orb"
        style={{ width: 320, height: 320, background: 'var(--gold)', opacity: 0.18, top: -60, right: -40 }}
        aria-hidden="true"
      />
      <div className="landing-mock-window mx-auto">
        <div className="landing-mock-titlebar">
          <span className="landing-mock-dot" />
          <span className="landing-mock-dot" />
          <span className="landing-mock-dot" />
          <span className="ms-2" style={{ fontSize: '0.78rem', color: 'var(--ink-text-secondary)' }}>
            AI Assistant
          </span>
        </div>
        <div className="landing-mock-body">
          <div className="landing-mock-bubble is-user">Explain LangGraph, and check if it's on the news.</div>
          <div className="landing-mock-bubble is-ai">
            LangGraph lets you build stateful, multi-step AI workflows. Based on a quick search, it's actively used
            in production agent systems as of this year.
          </div>
          <div className="landing-mock-tags">
            <span className="landing-mock-tag">
              <CheckIcon width="0.85em" height="0.85em" /> Remembered context
            </span>
            <span className="landing-mock-tag">
              <GlobeIcon width="0.85em" height="0.85em" /> Web Search
            </span>
            <span className="landing-mock-tag">
              <DocumentIcon width="0.85em" height="0.85em" /> Document knowledge
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function HeroSection() {
  return (
    <section className="landing-hero">
      <div
        className="landing-glow-orb"
        style={{ width: 480, height: 480, background: 'var(--gold-deep)', opacity: 0.16, top: '10%', left: '-10%' }}
        aria-hidden="true"
      />
      <div className="container position-relative" style={{ zIndex: 1 }}>
        <div className="row align-items-center g-5">
          <div className="col-lg-6">
            <span className="landing-eyebrow">Your personalized AI workspace</span>
            <h1 className="landing-hero-heading">
              AI that <span className="landing-gradient-text">remembers</span> what matters.
            </h1>
            <p className="landing-hero-sub">
              Chat naturally, ask questions about your own documents, and pull in current information from the web
              — all in one place, with every conversation kept exactly where you left it.
            </p>
            <div className="landing-hero-ctas">
              <Link to="/login" className="landing-btn-primary">
                Start Chatting
              </Link>
              <a href="#features" className="landing-btn-secondary">
                Explore Features
              </a>
            </div>
          </div>
          <div className="col-lg-6">
            <HeroVisual />
          </div>
        </div>
      </div>
    </section>
  );
}
