"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Dialog, Select, Table, TextLink } from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";

import { STAGES } from "../stages";

export type CandidateList = { kind: "stage" | "metric"; key: string; title: string };

type Row = {
  id: string;
  project_id: string;
  project_title: string;
  name: string;
  file_name: string;
  score: string | null;
  grade: string | null;
  stage: string;
};
type Body = { total: number; items: Row[] };

/** The popup behind a number: one row for each candidate, the flag changeable in the row, and
 * the whole row opens the candidate. It asks the server when it opens and again after a flag
 * changes, so a candidate that no longer fits the number leaves the list. */
export function CandidateListDialog({
  list,
  days,
  onClose,
  onChanged,
}: {
  list: CandidateList | null;
  days: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const router = useRouter();
  const [body, setBody] = useState<Body | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    if (!list) return;
    const query = new URLSearchParams({ kind: list.kind, key: list.key, days: String(days) });
    const result = await getJson<Body>(`/api/company/dashboard/detail/?${query}`);
    if (result.ok) {
      setBody(result.data);
      setError(null);
    } else setError(result.error);
  }, [list, days]);

  useEffect(() => {
    setBody(null);
    setError(null);
    void load();
  }, [load]);

  async function changeFlag(row: Row, stage: string) {
    const result = await postJson(`/api/company/projects/${row.project_id}/candidates/stage/`, {
      candidate_ids: [row.id],
      stage,
    });
    if (!result.ok) {
      setError(result.error);
      return;
    }
    onChanged();
    await load();
  }

  const open = (row: Row) =>
    router.push(`/company/projects/${row.project_id}/candidates/${row.id}`);

  return (
    <Dialog
      open={list !== null}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={list?.title ?? ""}
    >
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      {body && body.items.length === 0 && <p role="status">Nothing here yet.</p>}
      {body && body.items.length > 0 && (
        <>
          <Table label="Candidates">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Project</th>
                <th scope="col">AI score</th>
                <th scope="col">Flag</th>
              </tr>
            </thead>
            <tbody>
              {body.items.map((row) => (
                <tr key={row.id} className="ui-table__row--link" onClick={() => open(row)}>
                  <td>
                    <TextLink
                      href={`/company/projects/${row.project_id}/candidates/${row.id}`}
                      onClick={(event) => event.stopPropagation()}
                    >
                      {row.name || row.file_name}
                    </TextLink>
                  </td>
                  <td>{row.project_title}</td>
                  <td className="score-cell">{row.score ?? "None"}</td>
                  <td onClick={(event) => event.stopPropagation()}>
                    <Select
                      label={`Flag for ${row.name || row.file_name}`}
                      value={row.stage}
                      onChange={(event) => void changeFlag(row, event.target.value)}
                      options={STAGES}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
          <p role="status">
            Showing {body.items.length} of {body.total}
          </p>
        </>
      )}
    </Dialog>
  );
}
