"use client";

import { useEffect, useState } from "react";

import { Dialog, Tag } from "@/components/ui";
import { getJson } from "@/lib/api";

const USAGE_URL = "/api/company/usage/";
const MILLISECONDS = 1000;

type Measure = { used: number; limit: number; left: number; warning: number | null };

export type PlanAndUsage = {
  plan_name: string | null;
  state: string;
  period_start: string;
  period_end: string;
  cvs: Measure;
  tokens: Measure;
  estimated_cost: string;
  projects: { used: number; limit: number };
  refresh_seconds: number;
};

const STATE_WORDS: Record<string, string> = {
  no_plan: "No plan",
  active: "Active",
  past_due: "Past due",
  cancelled: "Cancelled",
  expired: "Expired",
  granted_free: "Free plan",
};

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });

const number = (value: number) => value.toLocaleString("en-US");

/** The words of a warning: its own surface in the tag, never colour alone. */
function warningWords(label: string, warning: number | null) {
  if (warning === null) return null;
  return warning >= 100 ? `${label} limit reached` : `${label} ${warning}% used`;
}

function WarningTag({ label, warning }: { label: string; warning: number | null }) {
  const words = warningWords(label, warning);
  if (!words) return null;
  return <Tag variant={warning !== null && warning >= 100 ? "danger" : "warning"}>{words}</Tag>;
}

function Bar({ measure, label }: { measure: Measure; label: string }) {
  const percent = measure.limit ? Math.min(100, (measure.used / measure.limit) * 100) : 0;
  return (
    <span
      className="usage-bar"
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={measure.limit}
      aria-valuenow={Math.min(measure.used, measure.limit)}
    >
      <span className="usage-bar__fill" style={{ width: `${percent}%` }} />
    </span>
  );
}

/** The company's plan and usage, re-read on the interval the server asks for. */
export function usePlanAndUsage() {
  const [summary, setSummary] = useState<PlanAndUsage | null>(null);
  const refreshSeconds = summary?.refresh_seconds;

  useEffect(() => {
    let active = true;
    const load = async () => {
      const result = await getJson<PlanAndUsage>(USAGE_URL);
      if (active && result.ok) setSummary(result.data);
    };
    void load();
    if (refreshSeconds === undefined) return () => void (active = false);
    const timer = setInterval(() => void load(), refreshSeconds * MILLISECONDS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [refreshSeconds]);

  return summary;
}

/** The small meter in the top bar (owner only). Opens the details in a popup. */
export function UsageMeter() {
  const summary = usePlanAndUsage();
  if (!summary) return null;
  const worst = Math.max(summary.cvs.warning ?? 0, summary.tokens.warning ?? 0);
  return (
    <Dialog
      title="Plan and usage"
      trigger={
        <button type="button" className="usage-meter">
          <span className="usage-meter__text">
            CVs {number(summary.cvs.used)} / {number(summary.cvs.limit)}
          </span>
          <Bar measure={summary.cvs} label="CVs used this period" />
          {worst > 0 && (
            <span className="usage-meter__tag">
              <Tag variant={worst >= 100 ? "danger" : "warning"}>
                {worst >= 100 ? "Limit reached" : `${worst}% used`}
              </Tag>
            </span>
          )}
        </button>
      }
    >
      <dl className="usage-details">
        <dt>Plan</dt>
        <dd>
          {summary.plan_name ?? STATE_WORDS[summary.state]}
          {summary.plan_name && ` (${STATE_WORDS[summary.state] ?? summary.state})`}
        </dd>
        <dt>This period</dt>
        <dd>
          {formatDate(summary.period_start)} to {formatDate(summary.period_end)}
        </dd>
        <dt>CVs used</dt>
        <dd>
          {number(summary.cvs.used)} of {number(summary.cvs.limit)}, {number(summary.cvs.left)} left{" "}
          <WarningTag label="CVs" warning={summary.cvs.warning} />
        </dd>
        <dt>AI tokens used</dt>
        <dd>
          {number(summary.tokens.used)} of {number(summary.tokens.limit)}{" "}
          <WarningTag label="Tokens" warning={summary.tokens.warning} />
        </dd>
        <dt>Estimated AI cost</dt>
        <dd>${summary.estimated_cost}</dd>
        <dt>Projects used</dt>
        <dd>
          {number(summary.projects.used)} of {number(summary.projects.limit)}
        </dd>
      </dl>
    </Dialog>
  );
}
