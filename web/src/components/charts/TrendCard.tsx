"use client";

import { useState } from "react";

import { Select } from "@/components/ui";

import { ChartCard } from "./ChartCard";
import { Trend, type TrendMetric } from "./Trend";

export type TrendData = {
  days: number;
  /** The periods to offer; leave out when the page picks the period itself. */
  choices?: number[];
  start: string;
  metrics: Record<string, TrendMetric>;
};

export const CV_METRICS = [
  { value: "uploaded", label: "CVs uploaded" },
  { value: "scored", label: "CVs scored" },
];

/** The trend chart with its two choices: what to count and over how many days. The days go to
 * the server (it picks the periods), so the parent reads them; a page that picks the period
 * itself passes no `onDays` and the period choice is left out. */
export function TrendCard({
  trend,
  onDays,
  metrics = CV_METRICS,
}: {
  trend: TrendData;
  onDays?: (days: number) => void;
  /** What can be counted: the names the server sends, with their labels. */
  metrics?: { value: string; label: string }[];
}) {
  const options = metrics.filter((item) => trend.metrics[item.value]);
  const [chosen, setMetric] = useState(options[0]?.value ?? "");
  const metric = options.some((item) => item.value === chosen) ? chosen : options[0]?.value;
  return (
    <ChartCard
      title="Trend"
      controls={
        <>
          <Select
            label="Count"
            value={metric}
            onChange={(event) => setMetric(event.target.value)}
            options={options}
          />
          {onDays && trend.choices && (
            <Select
              label="Period"
              value={String(trend.days)}
              onChange={(event) => onDays(Number(event.target.value))}
              options={trend.choices.map((days) => ({
                value: String(days),
                label: `${days} days`,
              }))}
            />
          )}
        </>
      }
    >
      <Trend
        metric={trend.metrics[metric]}
        start={trend.start}
        label={options.find((item) => item.value === metric)?.label ?? metric}
      />
    </ChartCard>
  );
}
