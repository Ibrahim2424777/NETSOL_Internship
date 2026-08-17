import { useEffect, useRef, useState } from 'react';

// Reveals an element once it scrolls into view - drives the landing page's
// scroll-triggered fade/slide sections (Phase 15). Fires once (the observer
// disconnects itself on first intersection) rather than toggling visibility
// on every scroll in/out, so content doesn't vanish again if the user
// scrolls back up - that reads as glitchy, not polished.
//
// No animation library involved (Intersection Observer is a native browser
// API) - this only ever adds/removes a CSS class; the actual fade/slide
// motion lives in styles/landing.css as plain CSS transitions, which already
// respect the app's global `prefers-reduced-motion` rule (collapses
// transition-duration to ~0, so content still appears, just without the
// animation - see index.css).
export function useScrollReveal<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.15, rootMargin: '0px 0px -10% 0px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return { ref, isVisible };
}
