import { useScrollReveal } from '../../hooks/useScrollReveal';
import { BrainIcon, DocumentIcon, GlobeIcon, ShieldIcon } from '../icons';

const HIGHLIGHTS = [
  {
    icon: BrainIcon,
    title: 'Memory',
    body: 'The assistant remembers relevant context from earlier in a conversation, so follow-ups actually feel like follow-ups.',
  },
  {
    icon: DocumentIcon,
    title: 'Document RAG',
    body: 'Ask questions about an indexed document and get answers grounded in what it actually says.',
  },
  {
    icon: GlobeIcon,
    title: 'Web Search',
    body: 'Turn on Web Search for a message to get an answer grounded in current information, with clickable sources.',
  },
  {
    icon: ShieldIcon,
    title: 'Reliability',
    body: 'Gemini is the primary model - if it hits a limit, your conversation transparently continues on a backup model.',
  },
];

// A compact "what this app can do" reminder on the personalized (logged-in)
// landing page - the marketing page's full scroll-story already covers this
// for logged-out visitors, but a returning signed-in user never sees that
// page, so without this they'd have no in-app way to (re)discover Web
// Search/RAG/reliability exist at all.
export default function FeatureHighlights() {
  const { ref, isVisible } = useScrollReveal<HTMLDivElement>();

  return (
    <div ref={ref} className={`reveal mt-4 ${isVisible ? 'is-visible' : ''}`}>
      <span className="landing-eyebrow">Explore</span>
      <h2 className="h5 fw-semibold mt-1 mb-3" style={{ color: 'var(--ink-text)' }}>
        What you can do here
      </h2>
      <div className="row g-3">
        {HIGHLIGHTS.map(({ icon: Icon, title, body }, i) => (
          <div className="col-sm-6" key={title}>
            <div
              className="landing-card landing-highlight-card p-3 h-100"
              style={{ transitionDelay: `${i * 90}ms` }}
            >
              <span className="landing-card-icon mb-2">
                <Icon />
              </span>
              <h3 className="h6 mb-1" style={{ color: 'var(--ink-text)' }}>
                {title}
              </h3>
              <p className="small mb-0" style={{ color: 'var(--ink-text-secondary)' }}>
                {body}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
