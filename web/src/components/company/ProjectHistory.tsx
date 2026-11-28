"use client";

import { useEffect, useState } from "react";

import { sentence, when, type Entry } from "@/components/company/ActivityLog";
import { Table } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

/** Who changed what on one project and when, newest first. */
export function ProjectHistory({ projectId }: { projectId: string }) {
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    void getJson<{ entries: Entry[] }>(`/api/company/projects/${projectId}/history/`).then(
      (result) => {
        if (result.ok) setEntries(result.data.entries);
        else setError(result.error);
      },
    );
  }, [projectId]);

  if (error)
    return (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    );
  if (!entries?.length) return null;
  return (
    <Table label="Project history">
      <thead>
        <tr>
          <th scope="col">When</th>
          <th scope="col">Who</th>
          <th scope="col">What</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((entry) => (
          <tr key={entry.id}>
            <td>{when(entry.created_at)}</td>
            <td>{entry.actor_name}</td>
            <td>{sentence(entry)}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
