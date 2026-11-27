"use client";

import { useState } from "react";

import { UsageHistory } from "../UsageHistory";
import { UsageCard } from "./UsageCard";

import { CompanyCharts } from "@/components/charts/CompanyCharts";
import { DetailDialog, type Detail } from "@/components/charts/DetailDialog";
import { useLiveCharts } from "@/components/charts/useLiveCharts";
import { Button, ButtonLink, Card, SegmentedControl, Tabs } from "@/components/ui";

import { Donut } from "./Donut";
import { ExportDialog } from "./ExportDialog";
import { Gauge } from "./Gauge";
import { stageLabel } from "../stages";
import { CandidateListDialog, type CandidateList } from "./CandidateListDialog";
import { CountCards } from "./CountCards";
import {
  AverageScores,
  MissedRequirements,
  NeedsAttention,
  ProjectTable,
  UploadsPerDay,
} from "./ProjectSections";
import { TopCandidatesTable } from "./TopCandidatesTable";
import type { DashboardData } from "./types";

const PERIOD_NAMES: Record<number, string> = {
  1: "Today",
  7: "This week",
  30: "This month",
  90: "3 months",
  180: "6 months",
};
const FLAG_COLOURS: Record<string, string> = {
  new: "grey",
  shortlisted: "blue",
  interviewed: "violet",
  on_hold: "amber",
  selected: "green",
  rejected: "coral",
};
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

type Open = (kind: string, key: string, title: string) => void;

function ProjectsSection({ data, open }: { data: DashboardData; open: Open }) {
  const { projects, screening } = data;
  const projectCount = projects.in_progress + projects.ready + projects.not_started;
  return (
    <div className="dashboard__section">
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
      <NeedsAttention items={data.attention} />
      <ProjectTable rows={data.project_rows} />
      <UploadsPerDay uploads={data.uploads_per_day} />
      <AverageScores rows={data.project_rows} />
    </div>
  );
}

function CandidatesSection({
  data,
  open,
  onDetail,
}: {
  data: DashboardData;
  open: Open;
  onDetail: (detail: Detail) => void;
}) {
  const { recommendations } = data;
  return (
    <div className="dashboard__section">
      <Card className="ui-card">
        <div className="chart-card__header">
          <h2>Top candidates</h2>
          <ButtonLink variant="secondary" href="/company/candidates">
            View all
          </ButtonLink>
        </div>
        <TopCandidatesTable candidates={data.top} />
      </Card>
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
      <div className="dashboard__row">
        <Card className="ui-card">
          <div className="chart-card__header">
            <h2>Candidates by flag</h2>
          </div>
          <Donut
            total={data.flag_split.reduce((sum, item) => sum + item.count, 0)}
            centreLabel="candidates"
            noun="candidates"
            parts={data.flag_split.map((item) => ({
              key: item.flag,
              label: stageLabel(item.flag),
              count: item.count,
              colour: FLAG_COLOURS[item.flag] ?? "grey",
            }))}
            onOpen={(key) => open("flag", key, stageLabel(key))}
          />
        </Card>
      </div>
      <MissedRequirements items={data.missed_requirements} />
      <CompanyCharts show={["funnel", "distribution"]} onOpen={onDetail} />
    </div>
  );
}

const SECTIONS = ["overview", "projects", "candidates", "usage"] as const;
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
  const [list, setList] = useState<CandidateList | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const query = new URLSearchParams();
  if (days !== null) query.set("days", String(days));
  const { data, error, reload } = useLiveCharts<DashboardData>(
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
      <CandidateListDialog
        list={list}
        days={data?.days ?? 1}
        onClose={() => setList(null)}
        onChanged={reload}
      />
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
            content: data ? (
              <CountCards
                counts={data.counts}
                onOpen={(key, title) =>
                  setList({ kind: key === "scored" ? "metric" : "stage", key, title })
                }
              />
            ) : (
              unavailable
            ),
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
              <CandidatesSection data={data} open={open} onDetail={setDetail} />
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
                <UsageHistory />
                <CompanyCharts show={["trend"]} />
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}
