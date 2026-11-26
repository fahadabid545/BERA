"use client";

import { useEffect, useState } from "react";

import { ChartCard } from "@/components/charts/ChartCard";
import { AdminSettingsTable } from "@/components/admin/AdminSettingsTable";
import { Button, Dialog, Table, Tabs } from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";

import { DailyBars } from "./DailyBars";
import { GrantList } from "./GrantList";
import { InviteList } from "./InviteList";
import { BASE, type Overview } from "./types";

const BETA_INVITES = ["beta_code", "beta_email"] as const;
const BETA_KINDS = [...BETA_INVITES];

/** Beta users: how they are doing, who they are, the codes and emails that let them in, and the
 * limits they work under. Revoking here never touches paid or permitted access. */
export function BetaSection() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [version, setVersion] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    void getJson<Overview>(`${BASE}overview/`).then((result) => {
      if (result.ok) setOverview(result.data);
      else setError(result.error);
    });
  }, [version]);

  async function revokeAll() {
    setError(null);
    const result = await postJson(`${BASE}access/revoke-all-beta/`, {});
    if (result.ok) setVersion((value) => value + 1);
    else setError(result.error);
  }

  return (
    <Tabs
      label="Beta users"
      tabs={[
        {
          value: "overview",
          label: "Overview",
          content: (
            <div className="page-stack">
              {overview && (
                <>
                  <Table label="Beta overview">
                    <tbody>
                      <tr>
                        <th scope="row">Active</th>
                        <td>{overview.active}</td>
                      </tr>
                      <tr>
                        <th scope="row">Ended</th>
                        <td>{overview.ended}</td>
                      </tr>
                      <tr>
                        <th scope="row">Revoked</th>
                        <td>{overview.revoked}</td>
                      </tr>
                      <tr>
                        <th scope="row">Feedback sent</th>
                        <td>{overview.feedback}</td>
                      </tr>
                    </tbody>
                  </Table>
                  <ChartCard title="Beta CVs a day">
                    <DailyBars days={overview.daily_cvs} label="Beta CVs a day" />
                  </ChartCard>
                </>
              )}
              {error && (
                <p className="ui-error" role="alert">
                  {error.message}
                </p>
              )}
              <div className="page-actions">
                <Button variant="danger" onClick={() => setConfirming(true)}>
                  Revoke all beta users
                </Button>
              </div>
              <Dialog
                open={confirming}
                onOpenChange={setConfirming}
                title="Revoke all beta users"
                confirmLabel="Revoke all"
                destructive
                onConfirm={() => void revokeAll()}
              />
            </div>
          ),
        },
        {
          value: "users",
          label: "Users",
          content: <GrantList kind="beta" refreshKey={version} />,
        },
        {
          value: "invites",
          label: "Codes and emails",
          content: (
            <InviteList kinds={BETA_KINDS} onChange={() => setVersion((value) => value + 1)} />
          ),
        },
        { value: "settings", label: "Settings", content: <AdminSettingsTable page="beta" /> },
      ]}
    />
  );
}
