"use client";

import { useEffect, useState } from "react";

import { Button, Dialog, Input, Select, Textarea } from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";

import { useAdminRole } from "./role";

type Plan = { id: number; name: string; status: string };

/** A super admin gives one company its free trial: a plan, days, a CV limit and a written reason.
 * Shown only while the company has no plan and has had no trial; the server decides in the end. */
export function StartTrial({
  companyId,
  state,
  onStarted,
}: {
  companyId: string;
  state: string;
  onStarted: () => void;
}) {
  const role = useAdminRole();
  const [open, setOpen] = useState(false);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [plan, setPlan] = useState("");
  const [days, setDays] = useState("");
  const [cvs, setCvs] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    if (role !== "super") return;
    void getJson<Plan[]>("/api/admin/plans/").then((result) => {
      if (result.ok) setPlans(result.data.filter((item) => item.status === "active"));
    });
  }, [role]);

  if (role !== "super" || !["no_plan", "expired"].includes(state)) return null;

  async function start() {
    setError(null);
    const result = await postJson(`/api/admin/companies/${companyId}/subscription/trial/`, {
      plan_id: Number(plan || plans[0]?.id),
      days: Number(days),
      cv_limit: Number(cvs),
      reason,
    });
    if (!result.ok) return setError(result.error);
    setDays("");
    setCvs("");
    setReason("");
    onStarted();
  }

  const fields = error?.fields ?? {};
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Start free trial
      </Button>
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Start free trial"
        confirmLabel="Start trial"
        onConfirm={() => void start()}
      >
        <Select
          label="Plan"
          options={plans.map((item) => ({ value: String(item.id), label: item.name }))}
          value={plan || String(plans[0]?.id ?? "")}
          onChange={(event) => setPlan(event.target.value)}
        />
        <Input
          label="Days"
          inputMode="numeric"
          value={days}
          error={fields.days}
          onChange={(e) => setDays(e.target.value)}
        />
        <Input
          label="CVs"
          inputMode="numeric"
          value={cvs}
          error={fields.cv_limit}
          onChange={(e) => setCvs(e.target.value)}
        />
        <Textarea
          label="Reason"
          value={reason}
          error={fields.reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </Dialog>
    </>
  );
}
