"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Checkbox, Dialog, Input, Select, Table, Tag } from "@/components/ui";
import { getJson, patchJson, postJson, type ApiError, type ApiResult } from "@/lib/api";

type Plan = { id: number; name: string; status: string };
type Code = {
  id: number;
  code: string;
  plan_id: number | null;
  enabled: boolean;
  known: boolean;
  percent_off?: number | null;
  amount_off?: string | null;
  duration?: "once" | "months" | "forever";
  months?: number | null;
  expires_at?: string | null;
  max_redemptions?: number | null;
  times_redeemed?: number;
  first_time_only?: boolean;
};
type Form = {
  code: string;
  kind: "percent" | "amount";
  value: string;
  duration: "once" | "months" | "forever";
  months: string;
  expires: string;
  max: string;
  firstTime: boolean;
  plan: string;
};
type Open = { kind: "new" } | { kind: "plan"; code: Code };

const BASE = "/api/admin/discounts/";
const ALL_PLANS = "";
const EMPTY: Form = {
  code: "",
  kind: "percent",
  value: "",
  duration: "once",
  months: "",
  expires: "",
  max: "",
  firstTime: false,
  plan: ALL_PLANS,
};
const day = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", { dateStyle: "medium", timeZone: "UTC" });

function discountText(code: Code) {
  if (!code.known) return "";
  return code.percent_off ? `${code.percent_off}% off` : `USD ${code.amount_off} off`;
}
function durationText(code: Code) {
  if (!code.known) return "";
  if (code.duration === "months") return `First ${code.months} months`;
  return code.duration === "forever" ? "Every payment" : "First payment";
}

/** Discount codes, made and kept at the payment provider. The page lists them with their use
 * counts; a code can be switched off, or limited to one plan. */
export function AdminDiscountCodes() {
  const [codes, setCodes] = useState<Code[] | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [form, setForm] = useState<Form>(EMPTY);
  const [open, setOpen] = useState<Open | null>(null);
  const [planChoice, setPlanChoice] = useState(ALL_PLANS);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    const [list, planList] = await Promise.all([
      getJson<{ codes: Code[] }>(BASE),
      getJson<Plan[]>("/api/admin/plans/"),
    ]);
    if (!list.ok) return setError(list.error);
    setCodes(list.data.codes);
    if (planList.ok) setPlans(planList.data.filter((plan) => plan.status === "active"));
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function run(request: Promise<ApiResult<{ codes: Code[] }>>) {
    setError(null);
    const result = await request;
    if (!result.ok) return setError(result.error);
    setCodes(result.data.codes);
    setForm(EMPTY);
  }

  function create() {
    const body: Record<string, unknown> = {
      code: form.code,
      kind: form.kind,
      value: form.value,
      duration: form.duration,
      first_time_only: form.firstTime,
    };
    if (form.duration === "months") body.months = Number(form.months);
    if (form.expires) body.expires_at = `${form.expires}T23:59:59Z`;
    if (form.max) body.max_redemptions = Number(form.max);
    if (form.plan) body.plan_id = Number(form.plan);
    return run(postJson(BASE, body));
  }

  if (!codes) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const fields = error?.fields ?? {};
  const set = (patch: Partial<Form>) => setForm({ ...form, ...patch });
  const planOptions = [
    { value: ALL_PLANS, label: "All plans" },
    ...plans.map((plan) => ({ value: String(plan.id), label: plan.name })),
  ];
  const planName = (id: number | null) =>
    id === null ? "All plans" : (plans.find((plan) => plan.id === id)?.name ?? String(id));

  return (
    <div className="page-stack">
      <div className="page-actions">
        <Button onClick={() => setOpen({ kind: "new" })}>New discount code</Button>
      </div>
      <Table label="Discount codes">
        <thead>
          <tr>
            <th>Code</th>
            <th>Discount</th>
            <th>Applies for</th>
            <th>Plan</th>
            <th>Expires</th>
            <th>Used</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {codes.map((code) => (
            <tr key={code.id}>
              <td>{code.code}</td>
              <td>{discountText(code)}</td>
              <td>{durationText(code)}</td>
              <td>{planName(code.plan_id)}</td>
              <td>{code.expires_at ? day(code.expires_at) : ""}</td>
              <td>
                {code.known
                  ? code.max_redemptions
                    ? `${code.times_redeemed} of ${code.max_redemptions}`
                    : String(code.times_redeemed)
                  : ""}
              </td>
              <td>
                <Tag variant={code.enabled ? "success" : "neutral"}>
                  {code.enabled ? "On" : "Off"}
                </Tag>
              </td>
              <td>
                <Button
                  variant="secondary"
                  aria-label={`${code.enabled ? "Switch off" : "Switch on"} ${code.code}`}
                  onClick={() =>
                    void run(patchJson(`${BASE}${code.id}/`, { enabled: !code.enabled }))
                  }
                >
                  {code.enabled ? "Switch off" : "Switch on"}
                </Button>{" "}
                <Button
                  variant="secondary"
                  aria-label={`Choose the plan of ${code.code}`}
                  onClick={() => {
                    setPlanChoice(code.plan_id === null ? ALL_PLANS : String(code.plan_id));
                    setOpen({ kind: "plan", code });
                  }}
                >
                  Plan
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      <Dialog
        open={open?.kind === "new"}
        onOpenChange={(next) => !next && setOpen(null)}
        title="New discount code"
        confirmLabel="Create code"
        onConfirm={() => void create()}
      >
        <Input
          label="Code"
          value={form.code}
          error={fields.code}
          onChange={(e) => set({ code: e.target.value })}
        />
        <Select
          label="Type"
          options={[
            { value: "percent", label: "Percent off" },
            { value: "amount", label: "US dollars off" },
          ]}
          value={form.kind}
          onChange={(event) => set({ kind: event.target.value as Form["kind"] })}
        />
        <Input
          label="Value"
          inputMode="decimal"
          value={form.value}
          error={fields.value}
          onChange={(e) => set({ value: e.target.value })}
        />
        <Select
          label="Applies for"
          options={[
            { value: "once", label: "First payment" },
            { value: "months", label: "A number of months" },
            { value: "forever", label: "Every payment" },
          ]}
          value={form.duration}
          onChange={(event) => set({ duration: event.target.value as Form["duration"] })}
        />
        {form.duration === "months" && (
          <Input
            label="Months"
            inputMode="numeric"
            value={form.months}
            error={fields.months}
            onChange={(e) => set({ months: e.target.value })}
          />
        )}
        <Input
          label="Code expires on"
          type="date"
          value={form.expires}
          error={fields.expires_at}
          onChange={(e) => set({ expires: e.target.value })}
        />
        <Input
          label="Most uses"
          inputMode="numeric"
          value={form.max}
          error={fields.max_redemptions}
          onChange={(e) => set({ max: e.target.value })}
        />
        <Checkbox
          label="First-time customers only"
          checked={form.firstTime}
          onChange={(e) => set({ firstTime: e.target.checked })}
        />
        <Select
          label="Plan"
          options={planOptions}
          value={form.plan}
          error={fields.plan_id}
          onChange={(e) => set({ plan: e.target.value })}
        />
      </Dialog>
      <Dialog
        open={open?.kind === "plan"}
        onOpenChange={(next) => !next && setOpen(null)}
        title="Plan of the code"
        confirmLabel="Save"
        onConfirm={() =>
          open?.kind === "plan" &&
          void run(
            patchJson(`${BASE}${open.code.id}/`, {
              plan_id: planChoice ? Number(planChoice) : null,
            }),
          )
        }
      >
        <Select
          label="Plan"
          options={planOptions}
          value={planChoice}
          onChange={(e) => setPlanChoice(e.target.value)}
        />
      </Dialog>
    </div>
  );
}
