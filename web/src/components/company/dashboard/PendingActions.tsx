import { Button, Card, Tag } from "@/components/ui";

import type { DashboardData } from "./types";

const ROWS = [
  { key: "awaiting_confirmation", label: "CVs awaiting confirmation", colour: "amber" },
  { key: "failed", label: "CVs that failed to read", colour: "coral" },
  { key: "links_expiring", label: "Shared links ending soon", colour: "blue" },
] as const;

/** What waits for a person, each with its count; Review lists the items and links to them. */
export function PendingActions({
  pending,
  onOpen,
}: {
  pending: DashboardData["pending"];
  onOpen: (key: string, label: string) => void;
}) {
  const total = pending.awaiting_confirmation + pending.failed + pending.links_expiring;
  return (
    <Card className="ui-card">
      <div className="chart-card__header">
        <h2>Pending actions</h2>
        <Tag variant={total ? "warning" : "neutral"}>{total} pending</Tag>
      </div>
      <ul className="pending-list">
        {ROWS.map((row) => (
          <li key={row.key} className={`pending-row pending-row--${row.colour}`}>
            <span className={`pending-row__count pending-row__count--${row.colour}`}>
              {pending[row.key]}
            </span>
            <span className="pending-row__label">{row.label}</span>
            <Button
              variant="secondary"
              disabled={pending[row.key] === 0}
              onClick={() => onOpen(row.key, row.label)}
            >
              Review
            </Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
