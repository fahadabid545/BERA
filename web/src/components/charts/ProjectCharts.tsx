"use client";

import { useState } from "react";

import { ChartCard } from "./ChartCard";
import { Coverage, type RequirementCoverage } from "./Coverage";
import { Funnel, type FunnelStep } from "./Funnel";
import { Histogram, type GradeCount } from "./Histogram";
import { Ranking, type RankedCandidate } from "./Ranking";
import { TrendCard, type TrendData } from "./TrendCard";
import { useLiveCharts } from "./useLiveCharts";

type ProjectChartData = {
  refresh_seconds: number;
  funnel: FunnelStep[];
  distribution: GradeCount[];
  ranking: RankedCandidate[];
  coverage: { candidates: number; requirements: RequirementCoverage[] };
  trend: TrendData;
};

/** The project's charts, each answering one question and all read from live data. */
export function ProjectCharts({ projectId }: { projectId: string }) {
  const [days, setDays] = useState<number | null>(null);
  const query = days === null ? "" : `?days=${days}`;
  const { data, error } = useLiveCharts<ProjectChartData>(
    `/api/company/projects/${projectId}/charts/${query}`,
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
      <ChartCard title="Ranking">
        {data.ranking.length > 0 ? (
          <Ranking projectId={projectId} candidates={data.ranking} />
        ) : (
          <p role="status">No scored candidates yet.</p>
        )}
      </ChartCard>
      <ChartCard title="Requirement coverage">
        {data.coverage.requirements.length > 0 ? (
          <Coverage
            candidates={data.coverage.candidates}
            requirements={data.coverage.requirements}
          />
        ) : (
          <p role="status">No requirements yet.</p>
        )}
      </ChartCard>
      <div className="chart-grid__wide">
        <TrendCard trend={data.trend} onDays={setDays} />
      </div>
    </div>
  );
}
