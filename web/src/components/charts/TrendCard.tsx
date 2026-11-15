"use client";

import { useState } from "react";

import { Select } from "@/components/ui";

import { ChartCard } from "./ChartCard";
import { Trend, type TrendMetric } from "./Trend";

export type TrendData = {
  days: number;
  choices: number[];
  start: string;
  metrics: { uploaded: TrendMetric; scored: TrendMetric };
};

const METRICS = [
  { value: "uploaded", label: "CVs uploaded" },
  { value: "scored", label: "CVs scored" },
];

/** The trend chart with its two choices: what to count and over how many days. The days go to
 * the server (it picks the periods), so the parent reads them. */
export function TrendCard({ trend, onDays }: { trend: TrendData; onDays: (days: number) => void }) {
  const [metric, setMetric] = useState<"uploaded" | "scored">("uploaded");
  return (
    <ChartCard
      title="Trend"
      controls={
        <>
          <Select
            label="Count"
            value={metric}
            onChange={(event) => setMetric(event.target.value as "uploaded" | "scored")}
            options={METRICS}
          />
          <Select
            label="Period"
            value={String(trend.days)}
            onChange={(event) => onDays(Number(event.target.value))}
            options={trend.choices.map((days) => ({ value: String(days), label: `${days} days` }))}
          />
        </>
      }
    >
      <Trend
        metric={trend.metrics[metric]}
        start={trend.start}
        label={METRICS.find((item) => item.value === metric)?.label ?? metric}
      />
    </ChartCard>
  );
}
