"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Checkbox, Dialog, Input, Select, Table, Tag } from "@/components/ui";
import { deleteJson, getJson, patchJson, postJson, type ApiError } from "@/lib/api";

import { BASE, day, type Invite, type Plan } from "./types";

type Kind = Invite["kind"];
type Open =
  | { name: "email" }
  | { name: "code" }
  | { name: "switch"; invite: Invite }
  | { name: "extend"; invite: Invite }
  | { name: "delete"; invite: Invite };
type Form = {
  label: string;
  email: string;
  days: string;
  uses: string;
  until: string;
  plan: string;
};

const EMPTY: Form = { label: "", email: "", days: "", uses: "", until: "", plan: "" };
const KIND_TEXT: Record<Kind, string> = {
  beta_email: "Email",
  beta_code: "Code",
  permitted_email: "Email",
};

/** The invites of some kinds: emails that get access once their owner has verified them, and codes
 * people type in. A code is shown once, when it is made. Switching an invite off never touches the
 * other invites; the choice to also take back the access it gave is made in the popup. */
export function InviteList({ kinds, onChange }: { kinds: Kind[]; onChange: () => void }) {
  const [invites, setInvites] = useState<Invite[] | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [open, setOpen] = useState<Open | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [alsoRevoke, setAlsoRevoke] = useState(false);
  const [created, setCreated] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const permitted = kinds.includes("permitted_email");

  const load = useCallback(async () => {
    const result = await getJson<{ invites: Invite[] }>(`${BASE}invites/`);
    if (result.ok) setInvites(result.data.invites.filter((invite) => kinds.includes(invite.kind)));
    else setError(result.error);
  }, [kinds]);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (!permitted) return;
    void getJson<Plan[]>("/api/admin/plans/").then((result) => {
      if (result.ok) setPlans(result.data.filter((plan) => plan.status === "active"));
    });
  }, [permitted]);

  function show(next: Open) {
    setError(null);
    setForm(EMPTY);
    setAlsoRevoke(false);
    setOpen(next);
  }
  const set = (patch: Partial<Form>) => setForm({ ...form, ...patch });

  async function send() {
    if (!open) return;
    setError(null);
    let result;
    if (open.name === "email") {
      result = await postJson<Invite>(`${BASE}invites/`, {
        kind: permitted ? "permitted_email" : "beta_email",
        email: form.email,
        label: form.label,
        ...(permitted
          ? { plan_id: Number(form.plan || plans[0]?.id) }
          : { access_days: Number(form.days) }),
      });
    } else if (open.name === "code") {
      result = await postJson<Invite & { code: string }>(`${BASE}invites/`, {
        kind: "beta_code",
        label: form.label,
        access_days: Number(form.days),
        max_uses: Number(form.uses),
        ...(form.until ? { redeem_until: `${form.until}T23:59:59Z` } : {}),
      });
      if (result.ok) setCreated(result.data.code);
    } else if (open.name === "switch") {
      result = await patchJson(`${BASE}invites/${open.invite.id}/`, {
        enabled: !open.invite.enabled,
        also_revoke_users: alsoRevoke,
      });
    } else if (open.name === "extend") {
      result = await postJson(`${BASE}invites/${open.invite.id}/extend/`, {
        days: Number(form.days),
      });
    } else {
      result = await deleteJson(`${BASE}invites/${open.invite.id}/`);
    }
    if (!result.ok) {
      setError(result.error);
      setOpen(open); // the popup closes when confirmed; a refusal brings it back
      return;
    }
    await load();
    onChange();
  }

  if (!invites) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const fields = error?.fields ?? {};
  const withCodes = kinds.includes("beta_code");
  return (
    <div className="page-stack">
      <div className="page-actions">
        {withCodes && <Button onClick={() => show({ name: "code" })}>New code</Button>}
        <Button
          variant={withCodes ? "secondary" : "primary"}
          onClick={() => show({ name: "email" })}
        >
          Add email
        </Button>
      </div>
      <Table label="Invites">
        <thead>
          <tr>
            <th>Label</th>
            <th>Type</th>
            <th>Email</th>
            {permitted ? <th>Plan</th> : <th>Days</th>}
            {withCodes && <th>Used</th>}
            {withCodes && <th>Use until</th>}
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {invites.map((invite) => {
            const name = invite.label || invite.email || `Invite ${invite.id}`;
            return (
              <tr key={invite.id}>
                <td>{invite.label}</td>
                <td>{KIND_TEXT[invite.kind]}</td>
                <td>{invite.email ?? ""}</td>
                {permitted ? <td>{invite.plan?.name ?? ""}</td> : <td>{invite.access_days}</td>}
                {withCodes && (
                  <td>{invite.max_uses ? `${invite.uses} of ${invite.max_uses}` : ""}</td>
                )}
                {withCodes && <td>{day(invite.redeem_until)}</td>}
                <td>
                  <Tag variant={invite.enabled ? "success" : "neutral"}>
                    {invite.enabled ? "On" : "Off"}
                  </Tag>
                </td>
                <td>
                  <div className="page-actions">
                    <Button
                      variant="secondary"
                      aria-label={`${invite.enabled ? "Switch off" : "Switch on"} ${name}`}
                      onClick={() => show({ name: "switch", invite })}
                    >
                      {invite.enabled ? "Switch off" : "Switch on"}
                    </Button>
                    {!permitted && (
                      <Button
                        variant="secondary"
                        aria-label={`Extend everyone of ${name}`}
                        onClick={() => show({ name: "extend", invite })}
                      >
                        Extend all
                      </Button>
                    )}
                    {invite.uses === 0 && (
                      <Button
                        variant="danger"
                        aria-label={`Delete ${name}`}
                        onClick={() => show({ name: "delete", invite })}
                      >
                        Delete
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </Table>
      {error && !open && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      <Dialog
        open={open !== null}
        onOpenChange={(next) => !next && setOpen(null)}
        title={
          open?.name === "code"
            ? "New code"
            : open?.name === "email"
              ? "Add email"
              : open?.name === "switch"
                ? open.invite.enabled
                  ? "Switch off"
                  : "Switch on"
                : open?.name === "extend"
                  ? "Extend everyone"
                  : "Delete invite"
        }
        confirmLabel={
          open?.name === "code"
            ? "Create code"
            : open?.name === "email"
              ? "Add email"
              : open?.name === "switch"
                ? open.invite.enabled
                  ? "Switch off"
                  : "Switch on"
                : open?.name === "extend"
                  ? "Extend"
                  : "Delete"
        }
        destructive={open?.name === "delete"}
        onConfirm={() => void send()}
      >
        {(open?.name === "code" || open?.name === "email") && (
          <Input
            label="Label"
            value={form.label}
            error={fields.label}
            onChange={(event) => set({ label: event.target.value })}
          />
        )}
        {open?.name === "email" && (
          <Input
            label="Email"
            type="email"
            value={form.email}
            error={fields.email}
            onChange={(event) => set({ email: event.target.value })}
          />
        )}
        {open?.name === "email" && permitted && (
          <Select
            label="Plan"
            value={form.plan || String(plans[0]?.id ?? "")}
            error={fields.plan_id}
            options={plans.map((plan) => ({ value: String(plan.id), label: plan.name }))}
            onChange={(event) => set({ plan: event.target.value })}
          />
        )}
        {((open?.name === "email" && !permitted) ||
          open?.name === "code" ||
          open?.name === "extend") && (
          <Input
            label={open?.name === "extend" ? "Days to add" : "Access days"}
            inputMode="numeric"
            value={form.days}
            error={fields.access_days ?? fields.days}
            onChange={(event) => set({ days: event.target.value })}
          />
        )}
        {open?.name === "code" && (
          <>
            <Input
              label="Most companies"
              inputMode="numeric"
              value={form.uses}
              error={fields.max_uses}
              onChange={(event) => set({ uses: event.target.value })}
            />
            <Input
              label="Use until"
              type="date"
              value={form.until}
              error={fields.redeem_until}
              onChange={(event) => set({ until: event.target.value })}
            />
          </>
        )}
        {open?.name === "switch" && open.invite.enabled && (
          <Checkbox
            label="Also revoke the people who joined with it"
            checked={alsoRevoke}
            onChange={(event) => setAlsoRevoke(event.target.checked)}
          />
        )}
        {open?.name === "delete" && <p>{open.invite.label || open.invite.email}</p>}
        {open && error && !Object.keys(fields).length && (
          <p className="ui-error" role="alert">
            {error.message}
          </p>
        )}
      </Dialog>
      <Dialog
        open={created !== null}
        onOpenChange={(next) => !next && setCreated(null)}
        title="Beta code"
      >
        {created && <p aria-label="New beta code">{created}</p>}
      </Dialog>
    </div>
  );
}
