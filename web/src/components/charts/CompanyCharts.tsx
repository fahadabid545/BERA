"use client";

import { useState } from "react";

import { ChartCard } from "./ChartCard";
import { Funnel, type FunnelStep } from "./Funnel";
import { Histogram, type GradeCount } from "./Histogram";
import { TrendCard, type TrendData } from "./TrendCard";
import { useLiveCharts } from "./useLiveCharts";

type CompanyChartData = {
  refresh_seconds: number;
  funnel: FunnelStep[];
  distribution: GradeCount[];
  trend: TrendData;
};

/** The company's charts: the same questions, all the company's projects together. */
export function CompanyCharts() {
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
      <ChartCard title="Funnel">
        <Funnel steps={data.funnel} />
      </ChartCard>
      <ChartCard title="Score distribution">
        <Histogram grades={data.distribution} />
      </ChartCard>
      <div className="chart-grid__wide">
        <TrendCard trend={data.trend} onDays={setDays} />
      </div>
    </div>
  );
}
