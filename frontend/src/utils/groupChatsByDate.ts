import type { Chat } from '../types';

export interface ChatGroup {
  label: string;
  chats: Chat[];
}

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

// Buckets chats by their last-activity date into "Today" / "Yesterday" /
// "This week" / "Older" - purely a display grouping over data the sidebar
// already has (chats are already sorted most-recent-first by the API), no
// extra fetch involved.
export function groupChatsByDate(chats: Chat[]): ChatGroup[] {
  const today = startOfDay(new Date());
  const yesterday = today - 86_400_000;
  const weekAgo = today - 7 * 86_400_000;

  const buckets: Record<string, Chat[]> = { Today: [], Yesterday: [], 'This week': [], Older: [] };

  for (const chat of chats) {
    const day = startOfDay(new Date(chat.updated_at));
    if (day === today) buckets.Today.push(chat);
    else if (day === yesterday) buckets.Yesterday.push(chat);
    else if (day > weekAgo) buckets['This week'].push(chat);
    else buckets.Older.push(chat);
  }

  return Object.entries(buckets)
    .filter(([, chats]) => chats.length > 0)
    .map(([label, chats]) => ({ label, chats }));
}
