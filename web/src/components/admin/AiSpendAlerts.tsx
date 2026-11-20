"use client";

import { useEffect, useState } from "react";

import { Button, Dialog, Input, Table } from "@/components/ui";
import { getJson, putJson, type ApiError } from "@/lib/api";

type Limits = {
  daily_limit: string | null;
  monthly_limit: string | null;
  spent_today: string;
  spent_this_month: string;
};

const BASE = "/api/admin/ai/controls/spend-alerts/";
const MONEY_DECIMALS = 2;

const dollars = (value: string) => `$${Number(value).toFixed(MONEY_DECIMALS)}`;
const limitText = (value: string | null) => (value === null ? "Not set" : dollars(value));

/** The daily and monthly AI spend limits. An email goes to the super admins once when spending
 * crosses one. Leaving a limit empty turns that alert off. */
export function AiSpendAlerts() {
  const [limits, setLimits] = useState<Limits | null>(null);
  const [open, setOpen] = useState(false);
  const [daily, setDaily] = useState("");
  const [monthly, setMonthly] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    void getJson<Limits>(BASE).then((result) => {
      if (result.ok) setLimits(result.data);
      else setError(result.error);
    });
  }, []);

  function show() {
    setDaily(limits?.daily_limit ?? "");
    setMonthly(limits?.monthly_limit ?? "");
    setReason("");
    setError(null);
    setOpen(true);
  }

  async function save() {
    setError(null);
    const result = await putJson<Limits>(BASE, {
      daily_limit: daily.trim() === "" ? null : daily.trim(),
      monthly_limit: monthly.trim() === "" ? null : monthly.trim(),
      reason,
    });
    if (result.ok) setLimits(result.data);
    else setError(result.error);
  }

  if (!limits) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  return (
    <div className="page-stack">
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      <Table label="Spend alerts">
        <thead>
          <tr>
            <th scope="col">Period</th>
            <th scope="col">Spent</th>
            <th scope="col">Alert limit</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Today</td>
            <td>{dollars(limits.spent_today)}</td>
            <td>{limitText(limits.daily_limit)}</td>
          </tr>
          <tr>
            <td>This month</td>
            <td>{dollars(limits.spent_this_month)}</td>
            <td>{limitText(limits.monthly_limit)}</td>
          </tr>
        </tbody>
      </Table>
      <div className="page-actions">
        <Button variant="secondary" onClick={show}>
          Set alert limits
        </Button>
      </div>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="AI spend alert limits"
        confirmLabel="Save limits"
        onConfirm={() => void save()}
      >
        <Input
          label="Daily limit (USD)"
          value={daily}
          onChange={(event) => setDaily(event.target.value)}
        />
        <Input
          label="Monthly limit (USD)"
          value={monthly}
          onChange={(event) => setMonthly(event.target.value)}
        />
        <Input label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
      </Dialog>
    </div>
  );
}
