// Small hand-rolled inline SVG icons, matching the existing convention set
// by GoogleSignInButton's Google mark - no icon library dependency for a
// handful of simple glyphs (Phase 12.5 explicitly prefers this over adding
// a new dependency). All are 1em square, inherit currentColor, and accept
// className so callers control sizing via font-size.

import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement>;

const base = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  width: '1em',
  height: '1em',
};

export function SidebarIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="9" y1="4" x2="9" y2="20" />
    </svg>
  );
}

export function PlusIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

export function SendIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <line x1="12" y1="19" x2="12" y2="5" />
      <polyline points="6 11 12 5 18 11" />
    </svg>
  );
}

export function MoreIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" stroke="none" {...props}>
      <circle cx="12" cy="5" r="1.6" />
      <circle cx="12" cy="12" r="1.6" />
      <circle cx="12" cy="19" r="1.6" />
    </svg>
  );
}

export function DocumentIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

// Web search (Phase 14.6) - the composer's search toggle button and the
// citation chips on a web_search-routed reply, same visual language as
// DocumentIcon's use in the RAG sources panel.
export function GlobeIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

// Landing page (Phase 15) - the Memory feature section's icon.
export function BrainIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M9 4a2.5 2.5 0 0 0-2.5 2.5v.5A2.5 2.5 0 0 0 4 9.5v1a2.5 2.5 0 0 0 1 2 2.5 2.5 0 0 0-1 2v1a2.5 2.5 0 0 0 2.5 2.5v.5A2.5 2.5 0 0 0 9 21" />
      <path d="M15 4a2.5 2.5 0 0 1 2.5 2.5v.5a2.5 2.5 0 0 1 2.5 2.5v1a2.5 2.5 0 0 1-1 2 2.5 2.5 0 0 1 1 2v1a2.5 2.5 0 0 1-2.5 2.5v.5a2.5 2.5 0 0 1-2.5 2.5" />
      <path d="M9 4v17M15 4v17" />
    </svg>
  );
}

// Landing page (Phase 15) - the AI Model Reliability feature section's icon.
export function ShieldIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

// Landing page (Phase 15) - "context remembered" / "included" badges.
export function CheckIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

// Landing page (Phase 15) - CTA links ("Explore features →").
export function ArrowRightIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="12 5 19 12 12 19" />
    </svg>
  );
}
