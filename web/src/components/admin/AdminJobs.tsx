"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Dialog, Select, Table, Tag, type TagVariant } from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";
import { timeAgo } from "@/lib/timeAgo";

type State = "waiting" | "running" | "failed" | "stuck";
type Job = {
  id: string;
  company_id: string;
  company: string;
  project: string;
  state: State;
  tries: number;
  reason: string;
  since: string;
  can_retry: boolean;
  can_cancel: boolean;
};
type CompanyCounts = { id: string; name: string } & Record<State, number>;
type Listing = {
  totals: Record<State, number>;
  companies: CompanyCounts[];
  total: number;
  items: Job[];
};

const BASE = "/api/admin/jobs/";
const ALL = "";
const STATE_WORDS: Record<State, string> = {
  waiting: "Waiting",
  running: "Running",
  failed: "Failed",
  stuck: "Stuck",
};
const STATE_TAGS: Record<State, TagVariant> = {
  waiting: "neutral",
  running: "live",
  failed: "danger",
  stuck: "warning",
};
const STATES = Object.keys(STATE_WORDS) as State[];

/** Waiting, running, failed and stuck background work, by company, with a way to retry or cancel
 * a job. A job never shows a file name: that is candidate data. */
export function AdminJobs() {
  const [listing, setListing] = useState<Listing | null>(null);
  const [state, setState] = useState(ALL);
  const [company, setCompany] = useState(ALL);
  const [cancelling, setCancelling] = useState<Job | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    const query = new URLSearchParams();
    if (state) query.set("state", state);
    if (company) query.set("company", company);
    const result = await getJson<Listing>(`${BASE}?${query}`);
    if (result.ok) setListing(result.data);
    else setError(result.error);
  }, [state, company]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(job: Job, action: "retry" | "cancel") {
    setError(null);
    const result = await postJson(`${BASE}${job.id}/${action}/`, {});
    if (!result.ok) setError(result.error);
    await load();
  }

  if (!listing) {
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
      <Table label="Jobs by company">
        <thead>
          <tr>
            <th scope="col">Company</th>
            {STATES.map((each) => (
              <th key={each} scope="col">
                {STATE_WORDS[each]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {listing.companies.map((entry) => (
            <tr key={entry.id}>
              <th scope="row">{entry.name}</th>
              {STATES.map((each) => (
                <td key={each}>{entry[each]}</td>
              ))}
            </tr>
          ))}
          <tr>
            <th scope="row">Total</th>
            {STATES.map((each) => (
              <td key={each}>{listing.totals[each]}</td>
            ))}
          </tr>
        </tbody>
      </Table>
      <div className="page-actions">
        <Select
          label="State"
          value={state}
          onChange={(event) => setState(event.target.value)}
          options={[
            { value: ALL, label: "All states" },
            ...STATES.map((each) => ({ value: each, label: STATE_WORDS[each] })),
          ]}
        />
        <Select
          label="Company"
          value={company}
          onChange={(event) => setCompany(event.target.value)}
          options={[
            { value: ALL, label: "All companies" },
            ...listing.companies.map((entry) => ({ value: entry.id, label: entry.name })),
          ]}
        />
      </div>
      {listing.items.length === 0 ? (
        <p role="status">No jobs.</p>
      ) : (
        <>
          <Table label="Jobs">
            <thead>
              <tr>
                <th scope="col">Company</th>
                <th scope="col">Project</th>
                <th scope="col">State</th>
                <th scope="col">Tries</th>
                <th scope="col">Reason</th>
                <th scope="col">Since</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {listing.items.map((job) => (
                <tr key={job.id}>
                  <th scope="row">{job.company}</th>
                  <td>{job.project}</td>
                  <td>
                    <Tag variant={STATE_TAGS[job.state]}>{STATE_WORDS[job.state]}</Tag>
                  </td>
                  <td>{job.tries}</td>
                  <td>{job.reason}</td>
                  <td>{timeAgo(job.since)}</td>
                  <td>
                    <div className="page-actions">
                      {job.can_retry && (
                        <Button variant="secondary" onClick={() => void act(job, "retry")}>
                          Retry
                        </Button>
                      )}
                      {job.can_cancel && (
                        <Button variant="secondary" onClick={() => setCancelling(job)}>
                          Cancel job
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
          <p role="status">
            Showing {listing.items.length} of {listing.total}
          </p>
        </>
      )}
      <Dialog
        open={cancelling !== null}
        onOpenChange={(open) => {
          if (!open) setCancelling(null);
        }}
        title="Cancel this job?"
        confirmLabel="Cancel job"
        destructive
        onConfirm={() => cancelling && void act(cancelling, "cancel")}
      />
    </div>
  );
}
