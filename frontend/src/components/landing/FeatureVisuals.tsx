// Small illustrative visuals used inside each FeatureSection on the
// logged-out marketing page (Phase 15, sections 8-10). These are static
// mockups, not live data - the personalized landing page's
// RecentConversations component is the one place real API data is shown
// (see section 12 vs section 11's distinction between an illustrative
// feature demo and actual user data).
import { CheckIcon, DocumentIcon, GlobeIcon, ShieldIcon } from '../icons';

export function MemoryVisual() {
  return (
    <>
      <div className="landing-memory-turn">
        <span className="landing-memory-label">You</span>
        <span className="landing-memory-text">Explain LangGraph.</span>
      </div>
      <div className="landing-memory-turn">
        <span className="landing-memory-label">AI</span>
        <span className="landing-memory-text">
          LangGraph lets you build stateful, multi-step AI workflows as a graph of steps.
        </span>
      </div>
      <div className="landing-memory-turn">
        <span className="landing-memory-label">You</span>
        <span className="landing-memory-text">Why is that useful?</span>
      </div>
      <div className="landing-memory-turn">
        <span className="landing-memory-label">AI</span>
        <span className="landing-memory-text">Because it lets each step branch, retry, or loop on its own...</span>
        <span className="landing-memory-badge">
          <CheckIcon width="0.85em" height="0.85em" /> Context remembered
        </span>
      </div>
    </>
  );
}

export function RagVisual() {
  return (
    <div className="landing-rag-flow">
      <div className="landing-rag-step">
        <DocumentIcon width="1em" height="1em" /> your-document.pdf
      </div>
      <span className="landing-rag-arrow">↓</span>
      <div className="landing-rag-step">AI Retrieval</div>
      <span className="landing-rag-arrow">↓</span>
      <div className="landing-rag-step">Relevant passages found</div>
      <span className="landing-rag-arrow">↓</span>
      <div className="landing-rag-step is-accent">Grounded answer</div>
    </div>
  );
}

export function WebSearchVisual() {
  return (
    <>
      <span className="landing-search-mock-toggle">
        <GlobeIcon width="0.9em" height="0.9em" /> Web search: ON
      </span>
      <p className="mt-3 mb-3" style={{ fontSize: '0.88rem', color: 'var(--ink-text-secondary)', lineHeight: 1.6 }}>
        Pakistan's next Test match begins August 19, part of a three-match series in England.
      </p>
      <div className="landing-memory-label mb-1">Sources</div>
      <div className="landing-citation-chip">
        <GlobeIcon width="0.9em" height="0.9em" /> ICC Future Tours Programme
      </div>
      <div className="landing-citation-chip">
        <GlobeIcon width="0.9em" height="0.9em" /> Official series schedule
      </div>
    </>
  );
}

export function HistoryVisual() {
  const items = ['LangGraph explanation', 'Understanding RAG', 'Trip planning notes'];
  return (
    <div>
      {items.map((title, i) => (
        <div key={title} className={`landing-history-mock-item ${i === 0 ? 'is-highlighted' : ''}`}>
          <span>{title}</span>
          <span style={{ color: 'var(--ink-text-muted)', fontSize: '0.75rem', flexShrink: 0 }}>
            {i === 0 ? '2m ago' : i === 1 ? '1h ago' : 'Yesterday'}
          </span>
        </div>
      ))}
    </div>
  );
}

export function ReliabilityVisual() {
  return (
    <div className="landing-reliability-flow justify-content-center">
      <div className="landing-reliability-node">
        <span className="landing-reliability-node-mark is-accent">
          <ShieldIcon />
        </span>
        Gemini
      </div>
      <span className="landing-reliability-connector" aria-hidden="true" />
      <div className="landing-reliability-node">
        <span className="landing-reliability-node-mark">
          <CheckIcon />
        </span>
        Groq fallback
      </div>
      <span className="landing-reliability-connector" aria-hidden="true" />
      <div className="landing-reliability-node">
        <span className="landing-reliability-node-mark is-accent">✦</span>
        Your answer
      </div>
    </div>
  );
}
