import { tintAt } from "./tints";

/** Initials only; the pastel colour takes turns by position, like the cards, and means nothing. */

export function initialsOf(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  const first = words[0][0];
  const last = words.length > 1 ? words[words.length - 1][0] : "";
  return (first + last).toUpperCase();
}

export function Avatar({ name, position = 0 }: { name: string; position?: number }) {
  return (
    <span className="ui-avatar" data-tint={tintAt(Math.abs(position))} aria-hidden="true">
      {initialsOf(name)}
    </span>
  );
}
