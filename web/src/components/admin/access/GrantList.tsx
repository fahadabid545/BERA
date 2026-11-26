"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Dialog, Input, Select, Table, Tag } from "@/components/ui";
import { deleteJson, getJson, patchJson, postJson, type ApiError } from "@/lib/api";

import { GrantView } from "./GrantView";
import { Pager } from "./Pager";
import {
  BASE,
  day,
  KIND_TEXT,
  STATUS_TEXT,
  type Grant,
  type Kind,
  type Page,
  type Plan,
  type Status,
} from "./types";

type Action =
  | { name: "revoke"; grant: Grant }
  | { name: "extend"; grant: Grant }
  | { name: "plan"; grant: Grant };

const ALL = "";

/** The accesses of one kind (beta or permitted), a page at a time, with their details, extending,
 * changing a plan and revoking. Each change is its own request and touches that access only. */
export function GrantList({ kind, refreshKey = 0 }: { kind: Kind; refreshKey?: number }) {
  const [listing, setListing] = useState<Page<Grant> | null>(null);
  const [status, setStatus] = useState<string>(ALL);
  const [page, setPage] = useState(1);
  const [action, setAction] = useState<Action | null>(null);
  const [days, setDays] = useState("");
  const [planId, setPlanId] = useState("");
  const [plans, setPlans] = useState<Plan[]>([]);
  const [shown, setShown] = useState<Grant | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    const query = new URLSearchParams({ kind, page: String(page) });
    if (status) query.set("status", status);
    const result = await getJson<Page<Grant>>(`${BASE}access/?${query}`);
    if (result.ok) setListing(result.data);
    else setError(result.error);
  }, [kind, page, status]);
  useEffect(() => {
    void load();
  }, [load, refreshKey]);
  useEffect(() => {
    if (kind !== "permitted") return;
    void getJson<Plan[]>("/api/admin/plans/").then((result) => {
      if (result.ok) setPlans(result.data.filter((plan) => plan.status === "active"));
    });
  }, [kind]);

  function open(next: Action) {
    setError(null);
    setDays("");
    setPlanId(next.grant.plan ? String(next.grant.plan.id) : "");
    setAction(next);
  }

  async function confirm() {
    if (!action) return;
    setError(null);
    const url = `${BASE}access/${action.grant.id}/`;
    const result =
      action.name === "revoke"
        ? await deleteJson(url)
        : action.name === "extend"
          ? await postJson(`${url}extend/`, { days: Number(days) })
          : await patchJson(url, { plan_id: Number(planId || plans[0]?.id) });
    if (result.ok) await load();
    else setError(result.error);
  }

  if (shown) {
    return (
      <GrantView
        grant={shown}
        onBack={() => {
          setShown(null);
          void load();
        }}
      />
    );
  }
  if (!listing) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const titles = { revoke: "Revoke access", extend: "Extend access", plan: "Change plan" };
  return (
    <div className="page-stack">
      <div className="page-actions">
        <Select
          label="Status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setPage(1);
          }}
          options={[
            { value: ALL, label: "All" },
            ...(Object.keys(STATUS_TEXT) as Status[]).map((value) => ({
              value,
              label: STATUS_TEXT[value],
            })),
          ]}
        />
      </div>
      <Table label={`${KIND_TEXT[kind]} accesses`}>
        <thead>
          <tr>
            <th>Company</th>
            <th>Owner</th>
            {kind === "permitted" && <th>Plan</th>}
            <th>Invite</th>
            <th>Started</th>
            {kind === "beta" && <th>Ends</th>}
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {listing.items.map((grant) => (
            <tr key={grant.id}>
              <td>{grant.company?.name ?? ""}</td>
              <td>{grant.owner?.email ?? ""}</td>
              {kind === "permitted" && <td>{grant.plan?.name ?? ""}</td>}
              <td>{grant.invite.label}</td>
              <td>{day(grant.started_at)}</td>
              {kind === "beta" && <td>{day(grant.ends_at)}</td>}
              <td>
                <Tag variant={grant.status === "active" ? "success" : "neutral"}>
                  {STATUS_TEXT[grant.status]}
                </Tag>
              </td>
              <td>
                <div className="page-actions">
                  <Button
                    variant="secondary"
                    aria-label={`Details of ${grant.company?.name ?? "access"}`}
                    onClick={() => setShown(grant)}
                  >
                    Details
                  </Button>
                  {kind === "beta" && grant.status !== "revoked" && (
                    <Button
                      variant="secondary"
                      aria-label={`Extend ${grant.company?.name ?? "access"}`}
                      onClick={() => open({ name: "extend", grant })}
                    >
                      Extend
                    </Button>
                  )}
                  {kind === "permitted" && grant.status === "active" && (
                    <Button
                      variant="secondary"
                      aria-label={`Change plan of ${grant.company?.name ?? "access"}`}
                      onClick={() => open({ name: "plan", grant })}
                    >
                      Change plan
                    </Button>
                  )}
                  {grant.status !== "revoked" && (
                    <Button
                      variant="danger"
                      aria-label={`Revoke ${grant.company?.name ?? "access"}`}
                      onClick={() => open({ name: "revoke", grant })}
                    >
                      Revoke
                    </Button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Pager listing={listing} onPage={setPage} />
      {error && !action && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      <Dialog
        open={action !== null}
        onOpenChange={(next) => !next && setAction(null)}
        title={action ? titles[action.name] : ""}
        confirmLabel={action ? titles[action.name] : undefined}
        destructive={action?.name === "revoke"}
        onConfirm={() => void confirm()}
      >
        {action?.name === "revoke" && <p>{action.grant.company?.name}</p>}
        {action?.name === "extend" && (
          <Input
            label="Days to add"
            inputMode="numeric"
            value={days}
            error={error?.fields?.days}
            onChange={(event) => setDays(event.target.value)}
          />
        )}
        {action?.name === "plan" && (
          <Select
            label="Plan"
            value={planId || String(plans[0]?.id ?? "")}
            error={error?.fields?.plan_id}
            options={plans.map((plan) => ({ value: String(plan.id), label: plan.name }))}
            onChange={(event) => setPlanId(event.target.value)}
          />
        )}
      </Dialog>
    </div>
  );
}
