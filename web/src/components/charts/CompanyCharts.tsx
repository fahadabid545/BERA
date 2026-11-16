"use client";

import { useState } from "react";

import { ChartCard } from "./ChartCard";
import type { Detail } from "./DetailDialog";
import { Funnel, type FunnelStep } from "./Funnel";
import { Histogram, type GradeCount } from "./Histogram";
import { TrendCard, type TrendData } from "./TrendCard";
import { useLiveCharts } from "./useLiveCharts";

const stepName = (step: string) => step.charAt(0).toUpperCase() + step.slice(1);

type CompanyChartData = {
  refresh_seconds: number;
  funnel: FunnelStep[];
  distribution: GradeCount[];
  trend: TrendData;
};

type Part = "funnel" | "distribution" | "trend";

/** The company's charts: the same questions, all the company's projects together. */
export function CompanyCharts({
  show = ["funnel", "distribution", "trend"],
  onOpen,
}: {
  /** Which charts to draw; each tab of the dashboard takes the ones that belong to it. */
  show?: Part[];
  onOpen?: (detail: Detail) => void;
}) {
  const [days, setDays] = useState<number | null>(null);
  const { data, error } = useLiveCharts<CompanyChartData>(
    `/api/company/charts/${days === null ? "" : `?days=${days}`}`,
  );
  if (!data) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  return (
    <div className="chart-grid">
      {show.includes("funnel") && (
        <ChartCard title="Funnel">
          <Funnel
            steps={data.funnel}
            onOpen={
              onOpen &&
              ((step) => onOpen({ kind: "funnel", key: step, title: `Funnel: ${stepName(step)}` }))
            }
          />
        </ChartCard>
      )}
      {show.includes("distribution") && (
        <ChartCard title="Score distribution">
          <Histogram
            grades={data.distribution}
            onOpen={
              onOpen &&
              ((grade) =>
                onOpen({ kind: "grade", key: grade, title: `Score distribution: grade ${grade}` }))
            }
          />
        </ChartCard>
      )}
      {show.includes("trend") && (
        <div className="chart-grid__wide">
          <TrendCard trend={data.trend} onDays={setDays} />
        </div>
      )}
    </div>
  );
}
