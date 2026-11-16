"use client";

import { useState } from "react";

import { UsageCard } from "./UsageCard";

import { CompanyCharts } from "@/components/charts/CompanyCharts";
import { DetailDialog, type Detail } from "@/components/charts/DetailDialog";
import { useLiveCharts } from "@/components/charts/useLiveCharts";
import { Button, Card, SegmentedControl, Tabs } from "@/components/ui";

import { ActivityFeed } from "./ActivityFeed";
import { Donut } from "./Donut";
import { ExportDialog } from "./ExportDialog";
import { Gauge } from "./Gauge";
import { InsightCard } from "./InsightCard";
import { KpiCard } from "./KpiCard";
import { PendingActions } from "./PendingActions";
import { QuickActions } from "./QuickActions";
import { TopCandidates } from "./TopCandidates";
import { periodWords, type DashboardData } from "./types";

const PERIOD_NAMES: Record<number, string> = { 1: "Today", 7: "This week", 30: "This month" };
const HOURS_PER_DAY = 24;

const RECOMMENDATIONS = [
  { key: "strong_match", label: "Strong match", colour: "green" },
  { key: "possible", label: "Possible", colour: "blue" },
  { key: "not_recommended", label: "Not recommended", colour: "coral" },
];
const PROJECT_GROUPS = [
  { key: "in_progress", label: "In progress", colour: "amber" },
  { key: "ready", label: "Ready", colour: "blue" },
  { key: "not_started", label: "Not started", colour: "grey" },
] as const;

const hoursWords = (hours: number) =>
  hours < HOURS_PER_DAY ? `${hours} h` : `${Math.round((hours / HOURS_PER_DAY) * 10) / 10} days`;
const signed = (value: number) => `${value > 0 ? "+" : ""}${value}`;
const direction = (value: number | null, goodWhenUp = true) =>
  value === null || value === 0 ? "neutral" : value > 0 === goodWhenUp ? "success" : "danger";

function Insights({
  data,
  open,
}: {
  data: DashboardData;
  open: (kind: string, key: string, title: string) => void;
}) {
  const { hiring_pace: pace, match_quality: quality, time_to_shortlist: wait } = data.insights;
  const period = periodWords(data.days);
  const waitChange =
    wait.hours !== null && wait.previous_hours !== null
      ? Math.round((wait.hours - wait.previous_hours) * 10) / 10
      : null;
  return (
    <div className="dashboard__insights">
      <InsightCard
        title="Hiring pace"
        headline={pace.change === null ? String(pace.current) : `${signed(pace.change)}%`}
        tag={{
          text:
            pace.change === null
              ? "No earlier period"
              : pace.change === 0
                ? "Same as before"
                : pace.change > 0
                  ? "More than before"
                  : "Fewer than before",
          variant: direction(pace.change),
        }}
        now={pace.current}
        before={pace.previous}
        unit=""
        tipLines={[`${pace.current} CVs in ${period}`, `${pace.previous} in the period before`]}
        onOpen={() => open("insight", "hiring_pace", `Hiring pace: CVs uploaded ${period}`)}
      />
      <InsightCard
        title="Match quality"
        headline={quality.share === null ? "No data" : `${quality.share}%`}
        tag={{
          text: quality.change === null ? "No earlier period" : `${signed(quality.change)} pts`,
          variant: direction(quality.change),
        }}
        now={quality.share}
        before={quality.previous_share}
        unit="%"
        tipLines={["Share of scored CVs that are a strong match", `Period: ${period}`]}
        onOpen={() => open("insight", "match_quality", `Strong matches scored ${period}`)}
      />
      <InsightCard
        title="Time to shortlist"
        headline={wait.hours === null ? "No data" : hoursWords(wait.hours)}
        tag={{
          text:
            waitChange === null
              ? "No earlier period"
              : waitChange === 0
                ? "Same as before"
                : `${waitChange < 0 ? "Faster" : "Slower"} by ${hoursWords(Math.abs(waitChange))}`,
          variant: direction(waitChange, false),
        }}
        now={wait.hours}
        before={wait.previous_hours}
        unit=" h"
        tipLines={["Median time from added to shortlisted", `Period: ${period}`]}
        onOpen={() => open("insight", "time_to_shortlist", `Shortlisted ${period}`)}
      />
    </div>
  );
}

type Open = (kind: string, key: string, title: string) => void;

function OverviewSection({ data, open }: { data: DashboardData; open: Open }) {
  const { cards, top, pending } = data;
  const period = periodWords(data.days);
  return (
    <div className="dashboard__section">
      <div className="dashboard__kpis">
        <KpiCard
          label="CVs uploaded"
          card={cards.uploaded}
          colour="blue"
          period={period}
          onOpen={() => open("metric", "uploaded", `CVs uploaded ${period}`)}
        />
        <KpiCard
          label="CVs scored"
          card={cards.scored}
          colour="violet"
          period={period}
          onOpen={() => open("metric", "scored", `CVs scored ${period}`)}
        />
        <KpiCard
          label="Shortlisted"
          card={cards.shortlisted}
          colour="teal"
          period={period}
          onOpen={() => open("metric", "shortlisted", `Shortlisted ${period}`)}
        />
        <KpiCard
          label="Average AI score"
          card={cards.average_score}
          colour="amber"
          unit=" pts"
          period={period}
          onOpen={() => open("metric", "average_score", `CVs scored ${period}`)}
        />
      </div>
      <Insights data={data} open={open} />
      <div className="dashboard__row dashboard__row--two">
        <QuickActions projectId={top.project_id} days={data.days} />
        <PendingActions pending={pending} onOpen={(key, label) => open("pending", key, label)} />
      </div>
    </div>
  );
}

function ProjectsSection({ data, open }: { data: DashboardData; open: Open }) {
  const { projects, screening } = data;
  const projectCount = projects.in_progress + projects.ready + projects.not_started;
  return (
    <div className="dashboard__row">
      <Card className="ui-card">
        <div className="chart-card__header">
          <h2>Projects overview</h2>
        </div>
        <Donut
          total={projectCount}
          centreLabel="projects"
          noun="projects"
          parts={PROJECT_GROUPS.map((item) => ({ ...item, count: projects[item.key] }))}
          onOpen={(key) =>
            open(
              "project_status",
              key,
              `Projects: ${PROJECT_GROUPS.find((item) => item.key === key)?.label ?? key}`,
            )
          }
        />
      </Card>
      <Card className="ui-card">
        <div className="chart-card__header">
          <h2>Screening progress</h2>
        </div>
        <Gauge
          percent={screening.percent}
          scored={screening.scored}
          uploaded={screening.uploaded}
          onOpen={() => open("screening", "all", "Screening progress by project")}
        />
      </Card>
    </div>
  );
}

function CandidatesSection({
  data,
  open,
  onProject,
  onDetail,
}: {
  data: DashboardData;
  open: Open;
  onProject: (id: string) => void;
  onDetail: (detail: Detail) => void;
}) {
  const { recommendations, top } = data;
  return (
    <div className="dashboard__section">
      <TopCandidates top={top} onProject={onProject} />
      <div className="dashboard__row">
        <Card className="ui-card">
          <div className="chart-card__header">
            <h2>CVs by recommendation</h2>
          </div>
          <Donut
            total={recommendations.total}
            centreLabel="scored"
            noun="candidates"
            parts={RECOMMENDATIONS.map((item) => ({
              ...item,
              count: recommendations.parts.find((part) => part.label === item.key)?.count ?? 0,
            }))}
            onOpen={(key) =>
              open(
                "recommendation",
                key,
                RECOMMENDATIONS.find((item) => item.key === key)?.label ?? key,
              )
            }
          />
        </Card>
      </div>
      <CompanyCharts show={["funnel", "distribution"]} onOpen={onDetail} />
    </div>
  );
}

const SECTIONS = ["overview", "projects", "candidates", "usage", "activity"] as const;
export type DashboardSection = (typeof SECTIONS)[number];

/** The company dashboard, one tab for each question: how the period went, how the projects
 * stand, who the best candidates are, how much is used, what just happened. The period, the
 * export and the popups behind every card are shared by all the tabs. Everything refreshes by
 * itself and every card and mark can be hovered for details or clicked for the list behind it. */
export function CompanyDashboard({
  tab,
  onTab,
}: {
  tab: DashboardSection;
  onTab: (tab: string) => void;
}) {
  const [days, setDays] = useState<number | null>(null);
  const [project, setProject] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const query = new URLSearchParams();
  if (days !== null) query.set("days", String(days));
  if (project) query.set("project", project);
  const { data, error } = useLiveCharts<DashboardData>(
    `/api/company/dashboard/${query.size ? `?${query}` : ""}`,
  );
  const open: Open = (kind, key, title) => setDetail({ kind, key, title });
  // The tabs are always there; a tab whose numbers cannot be read says why.
  const unavailable = error ? (
    <p className="ui-error" role="alert">
      {error.message}
    </p>
  ) : null;
  return (
    <div className="dashboard">
      <DetailDialog detail={detail} days={data?.days} onClose={() => setDetail(null)} />
      {data && (
        <div className="dashboard__header">
          <SegmentedControl
            label="Period"
            value={String(data.days)}
            options={data.choices.map((choice) => ({
              value: String(choice),
              label: PERIOD_NAMES[choice] ?? `${choice} days`,
            }))}
            onChange={(value) => setDays(Number(value))}
          />
          <ExportDialog
            days={data.days}
            trigger={<Button variant="secondary">Export report</Button>}
          />
        </div>
      )}
      <Tabs
        label="Dashboard"
        value={tab}
        onValueChange={onTab}
        tabs={[
          {
            value: "overview",
            label: "Overview",
            content: data ? <OverviewSection data={data} open={open} /> : unavailable,
          },
          {
            value: "projects",
            label: "Projects",
            content: data ? <ProjectsSection data={data} open={open} /> : unavailable,
          },
          {
            value: "candidates",
            label: "Candidates",
            content: data ? (
              <CandidatesSection
                data={data}
                open={open}
                onProject={setProject}
                onDetail={setDetail}
              />
            ) : (
              unavailable
            ),
          },
          {
            value: "usage",
            label: "Usage",
            content: (
              <div className="dashboard__section">
                <UsageCard />
                <CompanyCharts show={["trend"]} />
              </div>
            ),
          },
          {
            value: "activity",
            label: "Activity",
            content: data ? <ActivityFeed events={data.activity} /> : unavailable,
          },
        ]}
      />
    </div>
  );
}
