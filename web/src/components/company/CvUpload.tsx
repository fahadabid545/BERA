"use client";

import { useEffect, useRef, useState, type DragEvent } from "react";

import { BillingPrompts, isPromptKind, type PromptKind } from "@/components/company/BillingPrompt";
import { CVS_HELD_EVENT } from "@/components/company/CvProcessing";
import { Button } from "@/components/ui";
import { getJson, uploadFiles } from "@/lib/api";

type Blocked = { code: string; message: string; prompt: PromptKind | null };
type Rules = {
  allowed_types: string[];
  max_file_size_mb: number;
  max_files_per_batch: number;
  max_files_in_progress: number;
  files_in_progress: number;
  parallel_uploads: number;
  blocked: Blocked | null;
};
type FileResult = {
  name: string;
  status: "accepted" | "rejected" | "failed" | "skipped";
  code: string;
  message: string;
  prompt: PromptKind | null;
  notice: string;
};
type Entry = {
  id: number;
  file: File;
  batch: string;
  state: "queued" | "uploading" | "added" | "skipped" | "refused" | "failed";
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
  const [prompt, setPrompt] = useState<PromptKind | null>(null);
  const [blocked, setBlocked] = useState<Blocked | null>(null);
  const [loadError, setLoadError] = useState("");
  const [refusal, setRefusal] = useState("");
  const chooser = useRef<HTMLInputElement>(null);
  const sending = useRef(0);
  const waiting = useRef<Entry[]>([]);
  const addedAny = useRef(false);

  useEffect(() => {
    void getJson<Rules>(base).then((result) => {
      if (result.ok) {
        setRules(result.data);
        setBlocked(result.data.blocked);
      } else setLoadError(result.error.message);
    });
  }, [base]);

  const update = (id: number, changes: Partial<Entry>) =>
    setEntries((current) =>
      current.map((entry) => (entry.id === id ? { ...entry, ...changes } : entry)),
    );

  async function sendOne(entry: Entry) {
    update(entry.id, { state: "uploading", progress: 0, message: "" });
    const result = await uploadFiles<{ results: FileResult[] }>(
      base,
      [entry.file],
      (fraction) => update(entry.id, { progress: Math.round(fraction * PERCENT) }),
      { fields: { batch: entry.batch } },
    );
    if (!result.ok) {
      return update(entry.id, { state: "failed", message: result.error.message });
    }
    const outcome = result.data.results[0];
    if (outcome.status === "accepted") {
      addedAny.current = true;
      return update(entry.id, { state: "added", progress: PERCENT, message: outcome.notice });
    }
    if (outcome.status === "skipped") {
      return update(entry.id, { state: "skipped", message: outcome.message });
    }
    if (outcome.status === "failed") {
      return update(entry.id, { state: "failed", message: outcome.message });
    }
    if (outcome.prompt) {
      setPrompt(outcome.prompt);
      setBlocked({ code: outcome.code, message: outcome.message, prompt: outcome.prompt });
    }
    update(entry.id, { state: "refused", message: outcome.message });
  }

  /** Sends the waiting files, at most `parallel_uploads` at the same time. */
  function drain() {
    const most = rules?.parallel_uploads ?? 1;
    while (sending.current < most && waiting.current.length > 0) {
      sending.current += 1;
      void sendOne(waiting.current.shift()!).finally(() => {
        sending.current -= 1;
        if (waiting.current.length > 0) return drain();
        if (sending.current === 0 && addedAny.current) {
          addedAny.current = false;
          window.dispatchEvent(new Event(CVS_HELD_EVENT)); // the held CVs wait for their estimate
        }
      });
    }
  }

  /** Why the whole drop is refused (nothing is added), or null. The server checks again. */
  function refusalFor(chosen: File[], current: Rules): string | null {
    if (chosen.length === 0) return "Choose at least one file.";
    if (chosen.length > current.max_files_per_batch) {
      return `Only ${current.max_files_per_batch} files can be uploaded at a time. Nothing was added: choose fewer files.`;
    }
    const sentSinceLoading = entries.filter((entry) =>
      ["queued", "uploading", "added"].includes(entry.state),
    ).length;
    const busy = current.files_in_progress + sentSinceLoading;
    if (busy + chosen.length > current.max_files_in_progress) {
      return `You already have ${busy} files waiting or being processed, and at most ${current.max_files_in_progress} are allowed at a time. Nothing was added: wait for some to finish, then upload again.`;
    }
    return null;
  }

  function add(chosen: File[]) {
    if (!rules) return;
    const reason = refusalFor(chosen, rules);
    setRefusal(reason ?? "");
    if (reason) return;
    const batch = crypto.randomUUID(); // everything dropped together is one batch to cancel
    const fresh = chosen.map((file): Entry => {
      const id = nextId++;
      const problem = problemWith(file, rules);
      return {
        id,
        file,
        batch,
        progress: 0,
        state: problem ? "refused" : "queued",
        message: problem ?? "",
      };
    });
    setEntries((current) => [...current, ...fresh]);
    waiting.current.push(...fresh.filter((entry) => entry.state === "queued"));
    drain();
  }

  function retry(entry: Entry) {
    update(entry.id, { state: "queued", message: "" });
    waiting.current.push({ ...entry, state: "queued" });
    drain();
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
    <div className="page-stack" id="upload">
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
      {refusal && (
        <p className="ui-error" role="alert">
          {refusal}
        </p>
      )}
      {blocked && (
        <p role="status">
          {blocked.message}{" "}
          {blocked.prompt && (
            <Button variant="secondary" onClick={() => setPrompt(blocked.prompt)}>
              Show options
            </Button>
          )}
        </p>
      )}
      {entries.length > 0 && (
        <ul className="cv-upload-list" aria-label="Uploads">
          {entries.map((entry) => (
            <li key={entry.id}>
              <span>{entry.file.name}</span>{" "}
              <span>
                {entry.state === "queued" && "Waiting to upload"}
                {entry.state === "uploading" && `Uploading ${entry.progress}%`}
                {entry.state === "added" && (entry.message ? `Added. ${entry.message}` : "Added")}
                {(entry.state === "refused" ||
                  entry.state === "failed" ||
                  entry.state === "skipped") &&
                  entry.message}
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
      <BillingPrompts kind={prompt} onClose={() => setPrompt(null)} />
    </div>
  );
}
