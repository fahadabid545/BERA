const SECOND = 1000;
const MINUTE = 60;
const HOUR = 60;
const DAY = 24;

/** "2 min ago", "3 h ago", "5 d ago": how long before `now` something happened. */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const minutes = Math.max(0, Math.floor((now - new Date(iso).getTime()) / (SECOND * MINUTE)));
  if (minutes < 1) return "Just now";
  if (minutes < HOUR) return `${minutes} min ago`;
  const hours = Math.floor(minutes / HOUR);
  if (hours < DAY) return `${hours} h ago`;
  return `${Math.floor(hours / DAY)} d ago`;
}
