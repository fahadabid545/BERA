"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Dialog, Table, Tag, type TagVariant } from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";

type Status = "waiting" | "reading" | "scoring" | "done" | "failed" | "cancelled";
type Item = { id: string; name: string; status: Status; reason: string; can_retry: boolean };
type Processing = { refresh_seconds: number; counts: Record<Status, number>; items: Item[] };

const STATUSES: { status: Status; label: string; variant: TagVariant }[] = [
  { status: "waiting", label: "Waiting", variant: "neutral" },
  { status: "reading", label: "Reading", variant: "live" },
  { status: "scoring", label: "Scoring", variant: "live" },
  { status: "done", label: "Done", variant: "success" },
  { status: "failed", label: "Failed", variant: "danger" },
  { status: "cancelled", label: "Cancelled", variant: "neutral" },
];
const MILLISECONDS = 1000;

/** The project's CVs and where each one is. It looks again every few seconds, so people can
 * leave the page and come back. A failed CV shows why and has a Retry button; CVs that have not
 * started can be cancelled. */
export function CvProcessing({ projectId }: { projectId: string }) {
  const base = `/api/company/projects/${projectId}/`;
  const [processing, setProcessing] = useState<Processing | null>(null);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [actionError, setActionError] = useState<ApiError | null>(null);

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
