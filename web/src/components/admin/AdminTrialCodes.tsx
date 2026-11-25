"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Dialog, Input, Select, Table, Tag } from "@/components/ui";
import { getJson, patchJson, postJson, type ApiError, type ApiResult } from "@/lib/api";

type Plan = { id: number; name: string; status: string };
type TrialCode = {
  id: number;
  name: string;
  plan: { id: number; name: string };
  days: number;
  cv_limit: number;
  expires_at: string;
  enabled: boolean;
  status: "unused" | "redeemed" | "expired" | "off";
  redeemed_company: { id: number; name: string } | null;
};
type Created = TrialCode & { code: string };
type Form = { name: string; plan: string; days: string; cvs: string; expires: string };

const CODES = "/api/admin/trials/codes/";
const EMPTY: Form = { name: "", plan: "", days: "", cvs: "", expires: "" };
const STATUS_TEXT = { unused: "Unused", redeemed: "Used", expired: "Expired", off: "Off" };
const day = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", { dateStyle: "medium", timeZone: "UTC" });

/** Trial codes: a code gives one company one free trial of a plan, for some days and up to some
 * CVs. The code is shown once when it is made and never again. */
export function AdminTrialCodes() {
  const [codes, setCodes] = useState<TrialCode[] | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [form, setForm] = useState<Form>(EMPTY);
  const [making, setMaking] = useState(false);
  const [created, setCreated] = useState<Created | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    const [list, planList] = await Promise.all([
      getJson<{ codes: TrialCode[] }>(CODES),
      getJson<Plan[]>("/api/admin/plans/"),
    ]);
    if (!list.ok) return setError(list.error);
    setCodes(list.data.codes);
    if (planList.ok) setPlans(planList.data.filter((plan) => plan.status === "active"));
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const fail = (result: ApiResult<unknown>) => {
    if (!result.ok) setError(result.error);
    return result.ok;
  };

  async function create() {
    setError(null);
    const result = await postJson<Created>(CODES, {
      name: form.name,
      plan_id: Number(form.plan || plans[0]?.id),
      days: Number(form.days),
      cv_limit: Number(form.cvs),
      expires_at: `${form.expires}T23:59:59Z`,
    });
    if (!fail(result) || !result.ok) return;
    setCreated(result.data);
    setForm(EMPTY);
    await load();
  }

  async function switchCode(code: TrialCode) {
    setError(null);
    if (fail(await patchJson(`${CODES}${code.id}/`, { enabled: !code.enabled }))) await load();
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
  return (
    <div className="page-stack">
      <div className="page-actions">
        <Button onClick={() => setMaking(true)}>New trial code</Button>
      </div>
      <Table label="Trial codes">
        <thead>
          <tr>
            <th>Name</th>
            <th>Plan</th>
            <th>Days</th>
            <th>CVs</th>
            <th>Expires</th>
            <th>Status</th>
            <th>Used by</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {codes.map((code) => (
            <tr key={code.id}>
              <td>{code.name}</td>
              <td>{code.plan.name}</td>
              <td>{code.days}</td>
              <td>{code.cv_limit}</td>
              <td>{day(code.expires_at)}</td>
              <td>
                <Tag variant={code.status === "unused" ? "success" : "neutral"}>
                  {STATUS_TEXT[code.status]}
                </Tag>
              </td>
              <td>{code.redeemed_company?.name ?? ""}</td>
              <td>
                {code.status !== "redeemed" && (
                  <Button
                    variant="secondary"
                    aria-label={`${code.enabled ? "Switch off" : "Switch on"} ${code.name}`}
                    onClick={() => void switchCode(code)}
                  >
                    {code.enabled ? "Switch off" : "Switch on"}
                  </Button>
                )}
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
        open={making}
        onOpenChange={setMaking}
        title="New trial code"
        confirmLabel="Create code"
        onConfirm={() => void create()}
      >
        <Input
          label="Name"
          value={form.name}
          error={fields.name}
          onChange={(e) => set({ name: e.target.value })}
        />
        <Select
          label="Plan"
          options={plans.map((plan) => ({ value: String(plan.id), label: plan.name }))}
          value={form.plan || String(plans[0]?.id ?? "")}
          error={fields.plan_id}
          onChange={(event) => set({ plan: event.target.value })}
        />
        <Input
          label="Days"
          inputMode="numeric"
          value={form.days}
          error={fields.days}
          onChange={(e) => set({ days: e.target.value })}
        />
        <Input
          label="CVs"
          inputMode="numeric"
          value={form.cvs}
          error={fields.cv_limit}
          onChange={(e) => set({ cvs: e.target.value })}
        />
        <Input
          label="Code expires on"
          type="date"
          value={form.expires}
          error={fields.expires_at}
          onChange={(e) => set({ expires: e.target.value })}
        />
      </Dialog>
      <Dialog
        open={created !== null}
        onOpenChange={(open) => !open && setCreated(null)}
        title="Trial code"
      >
        {created && <p aria-label="New trial code">{created.code}</p>}
      </Dialog>
    </div>
  );
}
