"use client";

import { ButtonLink, Card, Tag } from "@/components/ui";

import { usePlanAndUsage, type PlanAndUsage } from "../UsageMeter";

const PERCENT = 100;
const number = (value: number) => value.toLocaleString("en-US");

function Row({
  label,
  used,
  limit,
  warning,
}: {
  label: string;
  used: number;
  limit: number;
  warning?: number | null;
}) {
  return (
    <li className="usage-card__row">
      <span>{label}</span>
      <span
        className="usage-bar"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={limit}
        aria-valuenow={Math.min(used, limit)}
      >
        <span
          className="usage-bar__fill"
          style={{ width: `${limit ? Math.min(PERCENT, (used * PERCENT) / limit) : 0}%` }}
        />
      </span>
      <span>
        {number(used)} / {number(limit)}
      </span>
      {warning ? (
        <Tag variant={warning >= PERCENT ? "danger" : "warning"}>
          {warning >= PERCENT ? "Limit reached" : `${warning}% used`}
        </Tag>
      ) : null}
    </li>
  );
}

function Rows({ summary }: { summary: PlanAndUsage }) {
  return (
    <ul className="usage-card__list">
      <Row
        label="CVs"
        used={summary.cvs.used}
        limit={summary.cvs.limit}
        warning={summary.cvs.warning}
      />
      <Row label="Projects" used={summary.projects.used} limit={summary.projects.limit} />
    </ul>
  );
}

/** The plan's limits and how much of each is used this period. Only the owner may see it, so
 * a member's dashboard simply leaves it out. */
export function UsageCard() {
  const summary = usePlanAndUsage();
  if (!summary) return null;
  return (
    <Card className="ui-card">
      <div className="chart-card__header">
        <h2>Usage this period</h2>
        <ButtonLink variant="secondary" href="/company/billing">
          Usage and billing
        </ButtonLink>
      </div>
      <Rows summary={summary} />
    </Card>
  );
}
