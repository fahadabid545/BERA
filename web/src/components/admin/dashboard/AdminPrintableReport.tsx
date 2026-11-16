"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { periodWords } from "@/components/company/dashboard/types";
import { Button, Table } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

import { usd } from "./types";

type Report = {
  days: number;
  generated_on: string;
  summary: {
    metric: string;
    current: number | null;
    previous: number | null;
    change: number | null;
  }[];
  companies: {
    company: string;
    plan: string | null;
    state: string;
    cvs_scored: number;
    cost?: number;
  }[];
  revenue?: {
    mrr: number;
    ai_cost: number;
    margin_percent: number | null;
    plans: { plan: string; subscribers: number; mrr: number }[];
  };
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

/** The platform's numbers as plain tables on a page made for printing or saving as a PDF. */
export function AdminPrintableReport() {
  const days = useSearchParams().get("days");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    let current = true;
    void getJson<Report>(`/api/admin/dashboard/report/${days ? `?days=${days}` : ""}`).then(
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
  const withCost = report.companies.some((row) => row.cost !== undefined);
  return (
    <div className="print-report page-stack">
      <div className="print-report__header">
        <h1>
          Platform report for {periodWords(report.days)}, {report.generated_on}
        </h1>
        <Button onClick={() => window.print()}>Print</Button>
      </div>
      <Grid
        title="Summary"
        columns={["Metric", "This period", "Previous period", "Change"]}
        rows={report.summary.map((row) => [
          row.metric,
          show(row.current),
          show(row.previous),
          show(row.change),
        ])}
      />
      {report.revenue && (
        <Grid
          title="Revenue"
          columns={["Plan", "Subscribers", "Monthly revenue"]}
          rows={[
            ...report.revenue.plans.map((row) => [row.plan, String(row.subscribers), usd(row.mrr)]),
            [
              "Total",
              String(report.revenue.plans.reduce((sum, row) => sum + row.subscribers, 0)),
              usd(report.revenue.mrr),
            ],
          ]}
        />
      )}
      <Grid
        title="Companies using the platform most"
        columns={[
          "Company",
          "Plan",
          "Subscription",
          "CVs scored",
          ...(withCost ? ["AI cost"] : []),
        ]}
        rows={report.companies.map((row) => [
          row.company,
          row.plan ?? "No plan",
          row.state,
          String(row.cvs_scored),
          ...(withCost ? [usd(row.cost ?? 0)] : []),
        ])}
      />
    </div>
  );
}
