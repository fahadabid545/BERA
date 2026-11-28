"use client";

import { useEffect, useState } from "react";

import { Button, Dialog, Input } from "@/components/ui";
import { getJson, putJson, type ApiError } from "@/lib/api";

const toList = (text: string) =>
  text
    .split(",")
    .map((label) => label.trim())
    .filter(Boolean);

/** The project's labels, typed as a comma-separated list. */
export function ProjectLabels({ projectId, readOnly }: { projectId: string; readOnly: boolean }) {
  const url = `/api/company/projects/${projectId}/preferences/`;
  const [saved, setSaved] = useState<string[] | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    void getJson<{ labels: string[] }>(url).then((result) => {
      if (!result.ok) return setError(result.error);
      setSaved(result.data.labels);
      setText(result.data.labels.join(", "));
    });
  }, [url]);

  async function save() {
    setError(null);
    const result = await putJson<{ labels: string[] }>(url, { labels: toList(text) });
    if (!result.ok) return setError(result.error);
    setSaved(result.data.labels);
    setText(result.data.labels.join(", "));
    setDone(true);
  }

  if (!saved) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const changed = JSON.stringify(toList(text)) !== JSON.stringify(saved);
  return (
    <section className="page-form" aria-labelledby="project-labels">
      <h2 id="project-labels">Labels</h2>
      <Input
        label="Labels, separated by commas"
        value={text}
        readOnly={readOnly}
        error={error?.fields?.labels}
        onChange={(event) => setText(event.target.value)}
      />
      {error && !error.fields && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      {!readOnly && (
        <div className="page-actions">
          <Button disabled={!changed} onClick={() => void save()}>
            Save labels
          </Button>
        </div>
      )}
      <Dialog open={done} onOpenChange={setDone} title="Labels saved" />
    </section>
  );
}
