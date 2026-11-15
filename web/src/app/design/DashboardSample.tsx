"use client";

import { Donut } from "@/components/company/dashboard/Donut";
import { Gauge } from "@/components/company/dashboard/Gauge";
import { InsightCard } from "@/components/company/dashboard/InsightCard";
import { KpiCard } from "@/components/company/dashboard/KpiCard";
import { PendingActions } from "@/components/company/dashboard/PendingActions";
import { QuickActions } from "@/components/company/dashboard/QuickActions";
import { TopCandidates } from "@/components/company/dashboard/TopCandidates";
import { ActivityFeed } from "@/components/company/dashboard/ActivityFeed";
import { SegmentedControl } from "@/components/ui";

const nothing = () => undefined;
const NOW = "2026-11-15T10:00:00Z";

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
      <div className="dashboard__insights">
        <InsightCard
          title="Hiring pace"
          headline="+67%"
          tag={{ text: "More CVs than before", variant: "success" }}
          now={12}
          before={7}
          unit=""
          tipLines={["12 CVs in the last 7 days", "7 in the period before"]}
          onOpen={nothing}
        />
      </div>
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
      <TopCandidates
        onProject={nothing}
        top={{
          projects: [{ id: "p", title: "Senior Python Developer" }],
          project_id: "p",
          compare_limits: { min: 2, max: 4 },
          candidates: [
            {
              id: "a",
              project_id: "p",
              project_title: "Senior Python Developer",
              name: "A. H.",
              file_name: "a.pdf",
              score: "94.5",
              grade: "A",
              stage: "interview",
              rank: 1,
              strengths: ["Strong Django", "Led a team"],
              ats_score: 92,
            },
            {
              id: "b",
              project_id: "p",
              project_title: "Senior Python Developer",
              name: "D. O.",
              file_name: "b.pdf",
              score: "91.0",
              grade: "A",
              stage: "shortlisted",
              rank: 2,
              strengths: ["PostgreSQL expert"],
              ats_score: 88,
            },
          ],
        }}
      />
      <div className="dashboard__row dashboard__row--two">
        <QuickActions projectId="p" days={30} />
        <PendingActions
          pending={{ awaiting_confirmation: 12, failed: 3, links_expiring: 2 }}
          onOpen={nothing}
        />
      </div>
      <ActivityFeed
        events={[
          {
            kind: "scored",
            id: "a",
            project_id: "p",
            project_title: "Senior Python Developer",
            name: "A. H.",
            file_name: "a.pdf",
            score: "94.5",
            at: NOW,
          },
          {
            kind: "moved",
            id: "b",
            project_id: "p",
            project_title: "Senior Python Developer",
            name: "D. O.",
            file_name: "b.pdf",
            score: "91.0",
            to_stage: "shortlisted",
            at: NOW,
          },
        ]}
      />
    </div>
  );
}
