import '../../styles/landing.css';

import FeatureSection from './FeatureSection';
import {
  HistoryVisual,
  MemoryVisual,
  RagVisual,
  ReliabilityVisual,
  WebSearchVisual,
} from './FeatureVisuals';
import FinalCTA from './FinalCTA';
import HeroSection from './HeroSection';
import LandingFooter from './LandingFooter';
import LandingHeader from './LandingHeader';

// The logged-out marketing page (Phase 15). Tells a short story as the user
// scrolls - hero, then one section per real capability the app has, ending
// in a CTA - rather than a flat grid of feature cards (section 26/27).
// Every claim here matches an actual, shipped capability (RAG, Web Search,
// Gemini+Groq fallback, conversation memory/history) - see each
// FeatureSection's copy, which deliberately avoids overclaiming (section 31).
export default function MarketingLanding() {
  return (
    <div className="landing-page">
      <LandingHeader />

      <HeroSection />

      <FeatureSection
        id="features"
        eyebrow="Memory"
        heading="Your conversation has context."
        body="You don't have to repeat yourself. The assistant remembers relevant parts of your conversation, so a follow-up question actually feels like a follow-up."
        visual={<MemoryVisual />}
        reveal="left"
      />

      <FeatureSection
        eyebrow="Document RAG"
        heading="Your documents. Your knowledge."
        body="Ask questions about an indexed document and get answers grounded in what it actually says - retrieved passages are handed to the model as real context, not guessed from memory."
        visual={<RagVisual />}
        reverse
        reveal="scale"
      />

      <FeatureSection
        eyebrow="Web search"
        heading="When you need what's happening now."
        body="Turn on Web Search for a message and get an answer grounded in current information, with clickable sources - search the web when you need it, on your terms."
        visual={<WebSearchVisual />}
        reveal="right"
      />

      <FeatureSection
        eyebrow="Conversation history"
        heading="Every conversation, right where you left it."
        body="Your previous conversations stay available, so you can return to an idea whenever you want - not just the last few minutes of it."
        visual={<HistoryVisual />}
        reverse
        reveal="blur"
      />

      <FeatureSection
        eyebrow="Reliability"
        heading="Built to keep answering."
        body="Gemini is the primary model. If it hits a rate limit or a temporary outage, your conversation transparently continues on a backup model instead of just failing."
        visual={<ReliabilityVisual />}
        reveal="up"
      />

      <FinalCTA />
      <LandingFooter />
    </div>
  );
}
