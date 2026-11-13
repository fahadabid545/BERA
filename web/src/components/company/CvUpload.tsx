"use client";

import { useEffect, useRef, useState, type DragEvent } from "react";

import { RenewalPrompt, UpgradePrompt } from "@/components/company/BillingPrompt";
import { Button } from "@/components/ui";
import { getJson, uploadFiles } from "@/lib/api";

type Rules = { allowed_types: string[]; max_file_size_mb: number; max_files_per_batch: number };
type FileResult = {
  name: string;
  status: "accepted" | "rejected" | "failed";
  code: string;
  message: string;
  prompt: "upgrade" | "renewal" | null;
  notice: string;
};
type Entry = {
  id: number;
  file: File;
  state: "queued" | "uploading" | "added" | "refused" | "failed";
  progress: number;
  message: string;
};

const BYTES_PER_MEGABYTE = 1024 * 1024;
const PERCENT = 100;
let nextId = 0;

/** The same checks the server makes, so an obviously wrong file is explained at once. The
 * server checks again and has the final say. */
function problemWith(file: File, rules: Rules): string | null {
  const ending = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
  if (!rules.allowed_types.includes(ending)) {
    return `Only ${rules.allowed_types.map((type) => type.toUpperCase()).join(" or ")} files can be uploaded.`;
  }
  if (file.size === 0) return "This file is empty.";
  if (file.size > rules.max_file_size_mb * BYTES_PER_MEGABYTE) {
    return `This file is larger than ${rules.max_file_size_mb} MB.`;
  }
  return null;
}

/** Drag and drop or choose CVs. Each file is sent on its own, so it shows its own progress and
 * result, a good file is never held back by a bad one, and after a dropped connection only the
 * files that failed are sent again. */
export function CvUpload({ projectId }: { projectId: string }) {
  const base = `/api/company/projects/${projectId}/cvs/`;
  const [rules, setRules] = useState<Rules | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [dragging, setDragging] = useState(false);
  const [prompt, setPrompt] = useState<"upgrade" | "renewal" | null>(null);
  const [loadError, setLoadError] = useState("");
  const chooser = useRef<HTMLInputElement>(null);
  const busy = useRef(false);
  const waiting = useRef<Entry[]>([]);

  useEffect(() => {
    void getJson<Rules>(base).then((result) => {
      if (result.ok) setRules(result.data);
      else setLoadError(result.error.message);
    });
  }, [base]);

  const update = (id: number, changes: Partial<Entry>) =>
    setEntries((current) =>
      current.map((entry) => (entry.id === id ? { ...entry, ...changes } : entry)),
    );

  async function sendOne(entry: Entry) {
    update(entry.id, { state: "uploading", progress: 0, message: "" });
    const result = await uploadFiles<{ results: FileResult[] }>(base, [entry.file], (fraction) =>
      update(entry.id, { progress: Math.round(fraction * PERCENT) }),
    );
    if (!result.ok) {
      return update(entry.id, { state: "failed", message: result.error.message });
    }
    const outcome = result.data.results[0];
    if (outcome.status === "accepted") {
      return update(entry.id, { state: "added", progress: PERCENT, message: outcome.notice });
    }
    if (outcome.status === "failed") {
      return update(entry.id, { state: "failed", message: outcome.message });
    }
    if (outcome.prompt) setPrompt(outcome.prompt);
    update(entry.id, { state: "refused", message: outcome.message });
  }

  async function drain() {
    if (busy.current) return;
    busy.current = true;
    while (waiting.current.length > 0) await sendOne(waiting.current.shift()!);
    busy.current = false;
  }

  function add(chosen: File[]) {
    if (!rules) return;
    const fresh = chosen.map((file, position): Entry => {
      const id = nextId++;
      const tooMany = position >= rules.max_files_per_batch;
      const problem = tooMany
        ? `Only ${rules.max_files_per_batch} files can be added at a time.`
        : problemWith(file, rules);
      return {
        id,
        file,
        progress: 0,
        state: problem ? "refused" : "queued",
        message: problem ?? "",
      };
    });
    setEntries((current) => [...current, ...fresh]);
    waiting.current.push(...fresh.filter((entry) => entry.state === "queued"));
    void drain();
  }

  function retry(entry: Entry) {
    update(entry.id, { state: "queued", message: "" });
    waiting.current.push({ ...entry, state: "queued" });
    void drain();
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    add(Array.from(event.dataTransfer.files));
  }

  if (loadError) {
    return (
      <p className="ui-error" role="alert">
        {loadError}
      </p>
    );
  }
  return (
    <div className="page-stack">
      <div
        className={dragging ? "cv-dropzone cv-dropzone--active" : "cv-dropzone"}
        data-testid="cv-dropzone"
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
      >
        <Button onClick={() => chooser.current?.click()} disabled={!rules}>
          Upload CVs
        </Button>
        <input
          ref={chooser}
          type="file"
          multiple
          className="visually-hidden"
          aria-label="Choose CV files"
          accept={rules?.allowed_types.map((type) => `.${type}`).join(",")}
          onChange={(event) => {
            add(Array.from(event.target.files ?? []));
            event.target.value = "";
          }}
        />
      </div>
      {entries.length > 0 && (
        <ul className="cv-upload-list" aria-label="Uploads">
          {entries.map((entry) => (
            <li key={entry.id}>
              <span>{entry.file.name}</span>{" "}
              <span>
                {entry.state === "queued" && "Waiting to upload"}
                {entry.state === "uploading" && `Uploading ${entry.progress}%`}
                {entry.state === "added" && (entry.message ? `Added. ${entry.message}` : "Added")}
                {(entry.state === "refused" || entry.state === "failed") && entry.message}
              </span>
              {entry.state === "failed" && (
                <Button
                  variant="secondary"
                  aria-label={`Try ${entry.file.name} again`}
                  onClick={() => retry(entry)}
                >
                  Try again
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <UpgradePrompt
        open={prompt === "upgrade"}
        onOpenChange={(open) => !open && setPrompt(null)}
      />
      <RenewalPrompt
        open={prompt === "renewal"}
        onOpenChange={(open) => !open && setPrompt(null)}
      />
    </div>
  );
}
