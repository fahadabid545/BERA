"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button, Dialog, Input, Table, Tag, TextLink } from "@/components/ui";
import { getJson, putJson, type ApiError } from "@/lib/api";

import { STATE_NAMES } from "./companyText";

const BASE = "/api/admin/cost-versus-revenue/";
const MONEY_DECIMALS = 2;
const RATE_NOT_SET = "rate_not_set";
const NO_PRICE = "no_price";

type Row = {
  id: string;
  name: string;
  country: string;
  subscription_state: string;
  currency: string;
  amount: string | null;
  status: string;
  paid_usd: string | null;
  ai_cost: string;
  margin_percent: number | null;
  flagged: boolean;
};
type Overall = {
  paid_usd: string;
  ai_cost: string;
  margin_percent: number | null;
  flagged: boolean;
  companies_counted: number;
  left_out: { rate_not_set: number; no_price: number };
};
type Report = {
  days: number;
  pkr_per_usd: string | null;
  overall: Overall;
  results: Row[];
  page: number;
  pages: number;
};

const dollars = (value: string) => `$${Number(value).toFixed(MONEY_DECIMALS)}`;
const marginText = (value: number | null) => (value === null ? "None" : `${value}%`);

function amountText(row: Row) {
  if (row.status === NO_PRICE) return "No price";
  if (row.amount === null) return "None";
  const number = Number(row.amount).toLocaleString("en-US", {
    minimumFractionDigits: MONEY_DECIMALS,
  });
  return `${row.currency} ${number}`;
}

function usdText(row: Row) {
  if (row.status === RATE_NOT_SET) return "Rate not set";
  return row.paid_usd === null ? "None" : dollars(row.paid_usd);
}

function Margin({ value, flagged }: { value: number | null; flagged: boolean }) {
  return flagged ? <Tag variant="warning">{marginText(value)}</Tag> : <>{marginText(value)}</>;
}

/** Per company and overall: AI cost, the estimated amount paid and the margin, with the PKR to
 * USD rate a super admin sets. A margin under the warning level carries a warning tag. */
export function CostVersusRevenue() {
  const [report, setReport] = useState<Report | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<ApiError | null>(null);
  const [open, setOpen] = useState(false);
  const [rate, setRate] = useState("");
  const [reason, setReason] = useState("");
  const latestRequest = useRef(0);

  const load = useCallback(async (wanted: number) => {
    const request = ++latestRequest.current;
    const result = await getJson<Report>(`${BASE}?page=${wanted}`);
    if (request !== latestRequest.current) return;
    if (result.ok) {
      setReport(result.data);
      setError(null);
    } else setError(result.error);
  }, []);
  useEffect(() => {
    void load(page);
  }, [load, page]);

  function show() {
    setRate(report?.pkr_per_usd ?? "");
    setReason("");
    setError(null);
    setOpen(true);
  }

  async function save() {
    setError(null);
    const value = rate.trim();
    const result = await putJson(`${BASE}rate/`, {
      pkr_per_usd: value === "" ? null : value,
      reason,
    });
    if (!result.ok) return setError(result.error);
    await load(page);
  }

  if (!report) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const { overall } = report;
  return (
    <div className="page-stack">
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      <Table label="Overall">
        <thead>
          <tr>
            <th scope="col">Period</th>
            <th scope="col">AI cost</th>
            <th scope="col">Amount paid (estimated)</th>
            <th scope="col">Margin</th>
            <th scope="col">Companies counted</th>
            <th scope="col">Left out</th>
            <th scope="col">PKR per USD</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{`Last ${report.days} days`}</td>
            <td>{dollars(overall.ai_cost)}</td>
            <td>{dollars(overall.paid_usd)}</td>
            <td>
              <Margin value={overall.margin_percent} flagged={overall.flagged} />
            </td>
            <td>{overall.companies_counted}</td>
            <td>{`${overall.left_out.rate_not_set} rate not set, ${overall.left_out.no_price} no price`}</td>
            <td>
              {report.pkr_per_usd ?? "Not set"}{" "}
              <Button variant="secondary" onClick={show}>
                Set rate
              </Button>
            </td>
          </tr>
        </tbody>
      </Table>
      {report.results.length === 0 ? (
        <p>No companies found.</p>
      ) : (
        <Table label="Companies">
          <thead>
            <tr>
              <th scope="col">Company</th>
              <th scope="col">Subscription</th>
              <th scope="col">Amount paid (estimated)</th>
              <th scope="col">In USD</th>
              <th scope="col">AI cost</th>
              <th scope="col">Margin</th>
            </tr>
          </thead>
          <tbody>
            {report.results.map((row) => (
              <tr key={row.id}>
                <td>
                  <TextLink href={`/admin/companies/${row.id}`}>{row.name}</TextLink>
                </td>
                <td>{STATE_NAMES[row.subscription_state] ?? row.subscription_state}</td>
                <td>{amountText(row)}</td>
                <td>{usdText(row)}</td>
                <td>{dollars(row.ai_cost)}</td>
                <td>
                  <Margin value={row.margin_percent} flagged={row.flagged} />
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {report.pages > 1 && (
        <div className="page-actions">
          <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </Button>
          <span>
            Page {report.page} of {report.pages}
          </span>
          <Button
            variant="secondary"
            disabled={page >= report.pages}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </div>
      )}
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="PKR per US dollar"
        confirmLabel="Save rate"
        onConfirm={() => void save()}
      >
        <Input label="Rate" value={rate} onChange={(event) => setRate(event.target.value)} />
        <Input label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
      </Dialog>
    </div>
  );
}
