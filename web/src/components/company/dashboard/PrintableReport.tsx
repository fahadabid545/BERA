"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, Table } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

import { periodWords } from "./types";

type Report = {
  days: number;
  generated_on: string;
  summary: { metric: string; count: number }[];
  recommendations: { label: string; count: number }[];
  projects: {
    project: string;
    cvs: number;
    scored: number;
    strong_matches: number;
    average_score: number | null;
  }[];
};

const RECOMMENDATION_WORDS: Record<string, string> = {
  strong_match: "Strong match",
  possible: "Possible",
  not_recommended: "Not recommended",
};
const show = (value: number | null) => (value === null ? "No data" : String(value));

function Grid({ title, columns, rows }: { title: string; columns: string[]; rows: string[][] }) {
  return (
    <section className="print-report__section">
      <h2>{title}</h2>
      <Table label={title}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.join("|")}>
              {row.map((cell, index) => (
                <td key={`${columns[index]}-${cell}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </Table>
    </section>
  );
}

/** The dashboard's numbers as plain tables on a page made for printing or saving as a PDF. */
export function PrintableReport() {
  const days = useSearchParams().get("days");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    let current = true;
    void getJson<Report>(`/api/company/dashboard/report/${days ? `?days=${days}` : ""}`).then(
      (result) => {
        if (!current) return;
        if (result.ok) setReport(result.data);
        else setError(result.error);
      },
    );
    return () => {
      current = false;
    };
  }, [days]);
  if (!report) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  return (
    <div className="print-report page-stack">
      <div className="print-report__header">
        <h1>
          Report for {periodWords(report.days)}, {report.generated_on}
        </h1>
        <Button onClick={() => window.print()}>Print</Button>
      </div>
      <Grid
        title="Summary"
        columns={["Metric", "Count"]}
        rows={report.summary.map((row) => [row.metric, show(row.count)])}
      />
      <Grid
        title="Recommendations"
        columns={["Recommendation", "Candidates"]}
        rows={report.recommendations.map((part) => [
          RECOMMENDATION_WORDS[part.label] ?? part.label,
          String(part.count),
        ])}
      />
      <Grid
        title="Projects"
        columns={["Project", "CVs", "Scored", "Strong matches", "Average AI score"]}
        rows={report.projects.map((row) => [
          row.project,
          String(row.cvs),
          String(row.scored),
          String(row.strong_matches),
          show(row.average_score),
        ])}
      />
    </div>
  );
}
