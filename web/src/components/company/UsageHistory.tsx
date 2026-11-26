"use client";

import { useEffect, useState } from "react";

import { UploadHeatmap } from "@/components/charts/UploadHeatmap";
import { Card, Select, Table } from "@/components/ui";
import { getJson } from "@/lib/api";

type Figures = {
  cvs: number;
  estimated_cost: string;
};
type Period = Figures & { id: string; start: string; end: string };
type ProjectRow = Figures & { project_id: string | null; title: string | null };
type History = {
  periods: Period[];
  selected: string | null;
  projects: ProjectRow[];
  uploads: number[][];
};

const COST_DECIMALS = 2;
const number = (value: number) => value.toLocaleString("en-US");
const cost = (value: string) => `$${Number(value).toFixed(COST_DECIMALS)}`;
const date = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
const periodText = (period: Period) => `${date(period.start)} to ${date(period.end)}`;

function FigureHeads() {
  return (
    <>
      <th scope="col">CVs</th>
      <th scope="col">Estimated cost</th>
    </>
  );
}

function FigureCells({ figures }: { figures: Figures }) {
  return (
    <>
      <td>{number(figures.cvs)}</td>
      <td>{cost(figures.estimated_cost)}</td>
    </>
  );
}

/** What the company used in each billing period, in each project of the chosen period, and when
 * in the week its CVs were uploaded. Owner only: for anyone else the server refuses and the
 * section stays out. */
export function UsageHistory() {
  const [period, setPeriod] = useState<string | null>(null);
  const [history, setHistory] = useState<History | null>(null);

  useEffect(() => {
    let current = true;
    void getJson<History>(`/api/company/usage/history/${period ? `?period=${period}` : ""}`).then(
      (result) => {
        if (current && result.ok) setHistory(result.data);
      },
    );
    return () => {
      current = false;
    };
  }, [period]);

  if (!history || history.periods.length === 0) return null;
  return (
    <>
      <Card className="ui-card">
        <h2>Usage by period</h2>
        <Table label="Usage by period">
          <thead>
            <tr>
              <th scope="col">Period</th>
              <FigureHeads />
            </tr>
          </thead>
          <tbody>
            {history.periods.map((item) => (
              <tr key={item.id}>
                <th scope="row">{periodText(item)}</th>
                <FigureCells figures={item} />
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
      <Card className="ui-card">
        <div className="chart-card__header">
          <h2>Usage by project</h2>
          <Select
            label="Period"
            value={history.selected ?? ""}
            onChange={(event) => setPeriod(event.target.value)}
            options={history.periods.map((item) => ({ value: item.id, label: periodText(item) }))}
          />
        </div>
        <Table label="Usage by project">
          <thead>
            <tr>
              <th scope="col">Project</th>
              <FigureHeads />
            </tr>
          </thead>
          <tbody>
            {history.projects.map((row) => (
              <tr key={row.project_id ?? "none"}>
                <th scope="row">
                  {row.title ?? (row.project_id ? "Deleted project" : "No project")}
                </th>
                <FigureCells figures={row} />
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
      <Card className="ui-card">
        <h2>When CVs are uploaded</h2>
        <UploadHeatmap grid={history.uploads} />
      </Card>
    </>
  );
}
