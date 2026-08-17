// Small display-formatting helpers for the personalized landing page
// (Phase 15) - relative timestamps for "Recent conversations" and a
// time-of-day greeting. Pure functions, no dependencies.

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

// "2m ago" / "3h ago" / "Yesterday" / "Mon" / "Jan 5" - coarser than a full
// timestamp on purpose, matching the doc's mockup (section 12) rather than
// showing an exact date/time for every row.
export function formatRelativeTime(isoDate: string): string {
  const date = new Date(isoDate);
  const diff = Date.now() - date.getTime();

  if (diff < MINUTE) return 'Just now';
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m ago`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h ago`;

  const startOfToday = new Date().setHours(0, 0, 0, 0);
  const startOfDate = new Date(date).setHours(0, 0, 0, 0);
  const dayDiff = Math.round((startOfToday - startOfDate) / DAY);

  if (dayDiff === 1) return 'Yesterday';
  if (dayDiff < 7) return date.toLocaleDateString(undefined, { weekday: 'long' });
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

// Local time of day, not the server's - Date() already reads the browser's
// clock/timezone, so no timezone handling needed here.
export function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 5) return 'Good night';
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}
