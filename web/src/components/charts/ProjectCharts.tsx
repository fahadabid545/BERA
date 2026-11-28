"use client";

import { useState } from "react";

import { ChartCard } from "./ChartCard";
import { DetailDialog, type Detail } from "./DetailDialog";
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
  const [detail, setDetail] = useState<Detail | null>(null);
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
    <div className="chart-grid chart-grid--overview">
      <DetailDialog detail={detail} onClose={() => setDetail(null)} />
      <ChartCard title="Funnel">
        <Funnel
          steps={data.funnel}
          onOpen={(step) =>
            setDetail({
              kind: "funnel",
              key: step,
              title: `Funnel: ${step.charAt(0).toUpperCase()}${step.slice(1)}`,
              project: projectId,
            })
          }
        />
      </ChartCard>
      <ChartCard title="Score distribution">
        <Histogram
          grades={data.distribution}
          onOpen={(grade) =>
            setDetail({
              kind: "grade",
              key: grade,
              title: `Score distribution: grade ${grade}`,
              project: projectId,
            })
          }
        />
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
            projectId={projectId}
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
