"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Dialog, Table, Tag, type TagVariant } from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";

type Status =
  "awaiting_confirmation" | "waiting" | "reading" | "scoring" | "done" | "failed" | "cancelled";
type Item = { id: string; name: string; status: Status; reason: string; can_retry: boolean };
type Used = { used: number; limit: number };
type Estimate = {
  cvs: number;
  tokens_total: number;
  estimated_cost: string;
  limits: { cvs_this_month: Used; cvs_in_project: Used; tokens: Used & { after_estimate: number } };
  blocked: boolean;
  message: string;
};
type Processing = { refresh_seconds: number; counts: Record<Status, number>; items: Item[] };

const STATUSES: { status: Status; label: string; variant: TagVariant }[] = [
  { status: "awaiting_confirmation", label: "Awaiting confirmation", variant: "neutral" },
  { status: "waiting", label: "Waiting", variant: "neutral" },
  { status: "reading", label: "Reading", variant: "live" },
  { status: "scoring", label: "Scoring", variant: "live" },
  { status: "done", label: "Done", variant: "success" },
  { status: "failed", label: "Failed", variant: "danger" },
  { status: "cancelled", label: "Cancelled", variant: "neutral" },
];
const MILLISECONDS = 1000;
/** Sent by the upload area when files were added, so the estimate opens at once. */
export const CVS_HELD_EVENT = "cvs-held";

/** The project's CVs and where each one is. It looks again every few seconds, so people can
 * leave the page and come back. A failed CV shows why and has a Retry button; CVs that have not
 * started can be cancelled. */
export function CvProcessing({ projectId }: { projectId: string }) {
  const base = `/api/company/projects/${projectId}/`;
  const [processing, setProcessing] = useState<Processing | null>(null);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [actionError, setActionError] = useState<ApiError | null>(null);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [estimateOpen, setEstimateOpen] = useState(false);

  const load = useCallback(async () => {
    const result = await getJson<Processing>(`${base}processing/`);
    if (result.ok) {
      setProcessing(result.data);
      setLoadError(null);
    } else setLoadError(result.error);
    return result.ok ? result.data.refresh_seconds : null;
  }, [base]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;
    const poll = async () => {
      const seconds = await load();
      if (!stopped && seconds) timer = setTimeout(poll, seconds * MILLISECONDS);
    };
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [load]);

  const reviewEstimate = useCallback(async () => {
    const result = await getJson<Estimate>(`${base}cvs/estimate/`);
    if (!result.ok) return setActionError(result.error);
    setEstimate(result.data);
    setEstimateOpen(true);
  }, [base]);

  useEffect(() => {
    const opened = () => void load().then(reviewEstimate);
    window.addEventListener(CVS_HELD_EVENT, opened);
    return () => window.removeEventListener(CVS_HELD_EVENT, opened);
  }, [load, reviewEstimate]);

  async function act(path: string) {
    setActionError(null);
    const result = await postJson(`${base}${path}`, {});
    if (!result.ok) setActionError(result.error);
    await load();
  }

  if (!processing) {
    return loadError ? (
      <p className="ui-error" role="alert">
        {loadError.message}
      </p>
    ) : null;
  }
  const total = Object.values(processing.counts).reduce((sum, count) => sum + count, 0);
  if (total === 0) return null;
  return (
    <div className="page-stack">
      <ul className="cv-upload-list" aria-label="CV status counts">
        {STATUSES.filter(({ status }) => processing.counts[status] > 0).map(({ status, label }) => (
          <li key={status}>
            {label} {processing.counts[status]}
          </li>
        ))}
      </ul>
      {processing.counts.awaiting_confirmation > 0 && (
        <div className="page-actions">
          <Button variant="secondary" onClick={reviewEstimate}>
            Review cost estimate
          </Button>
        </div>
      )}
      {estimate && (
        <Dialog
          open={estimateOpen}
          onOpenChange={setEstimateOpen}
          title="Approximate cost"
          confirmLabel={estimate.blocked ? undefined : "Process CVs"}
          onConfirm={() => act("cvs/estimate/")}
          actions={
            <Button
              variant="secondary"
              onClick={() => {
                setEstimateOpen(false);
                void act("cvs/cancel/");
              }}
            >
              Discard CVs
            </Button>
          }
        >
          <ul aria-label="Cost estimate">
            <li>CVs: {estimate.cvs}</li>
            <li>Approximate tokens: {estimate.tokens_total}</li>
            <li>Approximate cost: ${estimate.estimated_cost}</li>
            <li>
              CVs this month: {estimate.limits.cvs_this_month.used} of{" "}
              {estimate.limits.cvs_this_month.limit}
            </li>
            <li>
              CVs in this project: {estimate.limits.cvs_in_project.used} of{" "}
              {estimate.limits.cvs_in_project.limit}
            </li>
            <li>
              AI tokens this period: {estimate.limits.tokens.used} of {estimate.limits.tokens.limit}
            </li>
          </ul>
          {estimate.blocked && (
            <p className="ui-error" role="alert">
              {estimate.message}
            </p>
          )}
        </Dialog>
      )}
      {processing.counts.waiting > 0 && (
        <div className="page-actions">
          <Dialog
            trigger={<Button variant="secondary">Cancel waiting CVs</Button>}
            title="Cancel waiting CVs"
            confirmLabel="Cancel waiting CVs"
            onConfirm={() => act("cvs/cancel/")}
          />
        </div>
      )}
      {(actionError ?? loadError) && (
        <p className="ui-error" role="alert">
          {(actionError ?? loadError)?.message}
        </p>
      )}
      <Table label="CV processing">
        <thead>
          <tr>
            <th scope="col">File</th>
            <th scope="col">Status</th>
            <th scope="col">Reason</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {processing.items.map((item) => {
            const shown = STATUSES.find(({ status }) => status === item.status)!;
            return (
              <tr key={item.id}>
                <td>{item.name}</td>
                <td>
                  <Tag variant={shown.variant}>{shown.label}</Tag>
                </td>
                <td>{item.reason}</td>
                <td>
                  {item.can_retry && (
                    <Button
                      variant="secondary"
                      aria-label={`Retry ${item.name}`}
                      onClick={() => act(`cvs/${item.id}/retry/`)}
                    >
                      Retry
                    </Button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </Table>
    </div>
  );
}
