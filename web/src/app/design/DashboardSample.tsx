"use client";

import { CountCards } from "@/components/company/dashboard/CountCards";
import { Donut } from "@/components/company/dashboard/Donut";
import { Gauge } from "@/components/company/dashboard/Gauge";
import { KpiCard } from "@/components/company/dashboard/KpiCard";
import { TopCandidatesTable } from "@/components/company/dashboard/TopCandidatesTable";
import {
  AverageScores,
  MissedRequirements,
  NeedsAttention,
  ProjectTable,
  UploadsPerDay,
} from "@/components/company/dashboard/ProjectSections";
import type { ProjectRow } from "@/components/company/dashboard/types";
import { SegmentedControl } from "@/components/ui";

const nothing = () => undefined;
const PROJECT_ROWS: ProjectRow[] = [
  {
    id: "p",
    title: "Senior Python Developer",
    cvs: 48,
    failed: 2,
    capacity: 50,
    scored: 40,
    best_score: 94.5,
    average_score: 72.4,
    ats_average: 66,
    shortlisted: 6,
    interviewed: 3,
    selected: 1,
    updated_at: "2026-11-15T10:00:00Z",
  },
];

/** Every dashboard building block with sample figures; the handlers do nothing here. */
export function DashboardSample() {
  return (
    <div className="dashboard">
      <SegmentedControl
        label="Period"
        value="30"
        options={[
          { value: "1", label: "Today" },
          { value: "7", label: "This week" },
          { value: "30", label: "This month" },
          { value: "90", label: "3 months" },
          { value: "180", label: "6 months" },
        ]}
        onChange={nothing}
      />
      <div className="dashboard__kpis">
        <KpiCard
          label="CVs uploaded"
          colour="blue"
          period="the last 30 days"
          onOpen={nothing}
          card={{ value: 212, previous: 180, change: 17.8, series: [3, 5, 2, 8, 6, 9, 12] }}
        />
        <KpiCard
          label="Average AI score"
          colour="amber"
          unit=" pts"
          period="the last 30 days"
          onOpen={nothing}
          card={{ value: 72.4, previous: 73.6, change: -1.2, series: [75, 74, 76, 73, 72, 73, 72] }}
        />
      </div>
      <CountCards
        onOpen={nothing}
        counts={{
          projects: 8,
          scored: 198,
          shortlisted: 64,
          interviewed: 12,
          on_hold: 3,
          selected: 4,
          rejected: 20,
        }}
      />
      <div className="dashboard__row">
        <Donut
          total={198}
          centreLabel="scored"
          noun="candidates"
          parts={[
            { key: "strong_match", label: "Strong match", count: 31, colour: "green" },
            { key: "possible", label: "Possible", count: 98, colour: "blue" },
            { key: "not_recommended", label: "Not recommended", count: 69, colour: "coral" },
          ]}
          onOpen={nothing}
        />
        <Gauge percent={92} scored={198} uploaded={215} onOpen={nothing} />
      </div>
      <TopCandidatesTable
        candidates={[
          {
            id: "a",
            project_id: "p",
            project_title: "Senior Python Developer",
            name: "A. H.",
            file_name: "a.pdf",
            score: "94.5",
            grade: "A",
            stage: "interviewed",
            rank: 1,
            ats_score: 92,
          },
          {
            id: "b",
            project_id: "p",
            project_title: "Data Analyst",
            name: "D. O.",
            file_name: "b.pdf",
            score: "91.0",
            grade: "A",
            stage: "shortlisted",
            rank: 2,
            ats_score: null,
          },
        ]}
      />
      <NeedsAttention
        items={[
          { id: "p", title: "Senior Python Developer", capacity: 50, reason: "failed", count: 2 },
        ]}
      />
      <ProjectTable rows={PROJECT_ROWS} />
      <UploadsPerDay uploads={{ start: "2026-11-01", values: [2, 0, 5, 3] }} />
      <AverageScores rows={PROJECT_ROWS} />
      <MissedRequirements
        items={[
          {
            requirement: "5+ years of Python",
            kind: "must",
            project_id: "p",
            project_title: "Senior Python Developer",
            missing: 7,
            judged: 10,
          },
        ]}
      />
    </div>
  );
}
