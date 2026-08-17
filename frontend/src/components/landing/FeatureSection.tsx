import type { ReactNode } from 'react';

import { useScrollReveal } from '../../hooks/useScrollReveal';

type RevealVariant = 'up' | 'left' | 'right' | 'scale' | 'blur';

interface FeatureSectionProps {
  id?: string;
  eyebrow: string;
  heading: ReactNode;
  body: string;
  visual: ReactNode;
  reverse?: boolean;
  reveal?: RevealVariant;
}

const REVEAL_CLASS: Record<RevealVariant, string> = {
  up: '',
  left: 'reveal-left',
  right: 'reveal-right',
  scale: 'reveal-scale',
  blur: 'reveal-blur',
};

// Generic scroll-revealed "text + visual" row, reused for every feature in
// the landing page's scroll story (Memory, RAG, Web Search, History,
// Reliability) rather than one bespoke component per feature - only the
// content, the small illustrative `visual`, and the entrance style differ
// between them (see FeatureVisuals.tsx). `reveal` picks a genuinely
// different motion per section (fade-up/slide-left/slide-right/scale/blur)
// rather than every section using the identical animation - see the Phase
// 15.1 doc's "meaningfully different" request.
export default function FeatureSection({
  id,
  eyebrow,
  heading,
  body,
  visual,
  reverse,
  reveal = 'up',
}: FeatureSectionProps) {
  const { ref, isVisible } = useScrollReveal<HTMLDivElement>();

  return (
    <section id={id} className="landing-section">
      <div className="container">
        <div
          ref={ref}
          className={`landing-feature-row ${reverse ? 'is-reversed' : ''} reveal ${REVEAL_CLASS[reveal]} ${isVisible ? 'is-visible' : ''}`}
        >
          <div className="landing-feature-text">
            <span className="landing-eyebrow">{eyebrow}</span>
            <h2 className="landing-section-heading">{heading}</h2>
            <p className="landing-section-body">{body}</p>
          </div>
          <div className="landing-feature-visual">
            <div className="landing-visual-card">{visual}</div>
          </div>
        </div>
      </div>
    </section>
  );
}
