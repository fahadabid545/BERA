import { Card, TextLink } from "@/components/ui";

import type { Counts } from "./types";

export const COUNT_CARDS = [
  { key: "projects", label: "Projects" },
  { key: "scored", label: "CVs scored" },
  { key: "shortlisted", label: "Shortlisted" },
  { key: "interviewed", label: "Interviewed" },
  { key: "on_hold", label: "On hold" },
  { key: "selected", label: "Selected" },
  { key: "rejected", label: "Rejected" },
] as const;

export type CountKey = (typeof COUNT_CARDS)[number]["key"];

/** One card for each figure of the period: the name and the number, nothing else. The number
 * of projects opens the projects page; every other number opens the list of candidates behind
 * it. */
export function CountCards({
  counts,
  onOpen,
}: {
  counts: Counts;
  onOpen: (key: Exclude<CountKey, "projects">, label: string) => void;
}) {
  return (
    <div className="dashboard__counts">
      {COUNT_CARDS.map(({ key, label }) => (
        <Card key={key} className="ui-card count-card">
          <span className="count-card__label">{label}</span>
          {key === "projects" ? (
            <TextLink className="count-card__number" href="/company/projects">
              {counts[key]}
            </TextLink>
          ) : (
            <button
              type="button"
              className="count-card__number"
              aria-label={`${label}: ${counts[key]}`}
              onClick={() => onOpen(key, label)}
            >
              {counts[key]}
            </button>
          )}
        </Card>
      ))}
    </div>
  );
}
