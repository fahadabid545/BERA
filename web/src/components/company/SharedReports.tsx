"use client";

import { useEffect, useState } from "react";

import { Button, Checkbox, Dialog, Input, Select, Table } from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";

type Report = {
  id: string;
  created_at: string;
  expires_at: string;
  hide_contact: boolean;
  candidates: number;
  views: number;
  status: "active" | "expired" | "revoked";
};
type Listing = { days: { choices: number[]; default: number }; reports: Report[] };

const STATUSES = { active: "Active", expired: "Expired", revoked: "Revoked" };
const DATE_LENGTH = 10;

/** Share the project's top candidates through a read-only link, and see or revoke the links made
 * so far. The link itself is shown once, right after it is made. */
export function SharedReports({ projectId }: { projectId: string }) {
  const base = `/api/company/projects/${projectId}/reports/`;
  const [listing, setListing] = useState<Listing | null>(null);
  const [listOpen, setListOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [days, setDays] = useState("");
  const [hideContact, setHideContact] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<Report | null>(null);

  async function load() {
    const result = await getJson<Listing>(base);
    if (result.ok) setListing(result.data);
    else setError(result.error);
  }
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base]);

  async function create() {
    const result = await postJson<Report & { token: string }>(base, {
      days: Number(days || listing?.days.default),
      hide_contact: hideContact,
    });
    if (result.ok) {
      setError(null);
      setLink(`${window.location.origin}/r/${result.data.token}`);
      void load();
    } else setError(result.error);
  }

  async function revoke(report: Report) {
    const result = await postJson(`${base}${report.id}/revoke/`, {});
    if (result.ok) setError(null);
    else setError(result.error);
    void load();
  }

  const choices = (listing?.days.choices ?? []).map((value) => ({
    value: String(value),
    label: value === 1 ? "1 day" : `${value} days`,
  }));
  return (
    <>
      <Dialog
        open={creating}
        onOpenChange={setCreating}
        trigger={<Button variant="secondary">Share report</Button>}
        title="Share report"
        confirmLabel="Create link"
        onConfirm={() => void create()}
      >
        <Select
          label="Link expires after"
          value={days || String(listing?.days.default ?? "")}
          onChange={(event) => setDays(event.target.value)}
          options={choices}
        />
        <Checkbox
          label="Hide contact details"
          checked={hideContact}
          onChange={(event) => setHideContact(event.target.checked)}
        />
      </Dialog>
      <Dialog
        open={link !== null}
        onOpenChange={(open) => !open && setLink(null)}
        title="Report link"
      >
        <Input
          label="Link"
          readOnly
          value={link ?? ""}
          onFocus={(event) => event.target.select()}
        />
      </Dialog>
      <Dialog
        open={listOpen}
        onOpenChange={setListOpen}
        trigger={<Button variant="secondary">Shared links</Button>}
        title="Shared links"
      >
        {listing && listing.reports.length > 0 && (
          <Table label="Shared links">
            <thead>
              <tr>
                <th scope="col">Created</th>
                <th scope="col">Expires</th>
                <th scope="col">Status</th>
                <th scope="col">Views</th>
                <th scope="col">Contact details</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {listing.reports.map((report) => (
                <tr key={report.id}>
                  <td>{report.created_at.slice(0, DATE_LENGTH)}</td>
                  <td>{report.expires_at.slice(0, DATE_LENGTH)}</td>
                  <td>{STATUSES[report.status]}</td>
                  <td>{report.views}</td>
                  <td>{report.hide_contact ? "Hidden" : "Shown"}</td>
                  <td>
                    {report.status === "active" && (
                      <Button variant="danger" onClick={() => setRevoking(report)}>
                        Revoke
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Dialog>
      <Dialog
        open={revoking !== null}
        onOpenChange={(open) => !open && setRevoking(null)}
        title="Revoke link"
        description="The link stops working at once."
        confirmLabel="Revoke"
        destructive
        onConfirm={() => revoking && void revoke(revoking)}
      />
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
    </>
  );
}
