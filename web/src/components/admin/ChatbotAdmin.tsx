"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Checkbox, Dialog, Input, Select, Table, Tag } from "@/components/ui";
import {
  deleteJson,
  getJson,
  patchJson,
  postForm,
  putForm,
  putJson,
  type ApiError,
  type ApiResult,
} from "@/lib/api";

type Settings = {
  enabled: boolean;
  model: string;
  prompt_version: number;
  visitor_questions_per_hour: number;
  max_question_length: number;
  max_answer_length: number;
  daily_token_cap: number;
  models: string[];
  prompt_versions: number[];
};
type KnowledgeDocument = {
  id: number;
  name: string;
  file_type: string;
  size_bytes: number;
  characters: number;
  enabled: boolean;
  updated_at: string;
};
type State = { settings: Settings; documents: KnowledgeDocument[] };
type Open =
  | { kind: "save" }
  | { kind: "add" }
  | { kind: "replace"; document: KnowledgeDocument }
  | { kind: "delete"; document: KnowledgeDocument };
type Form = Record<NumberField, string> & { enabled: boolean; model: string; version: string };
type NumberField =
  "visitor_questions_per_hour" | "max_question_length" | "max_answer_length" | "daily_token_cap";

const BASE = "/api/admin/chatbot/";
const NUMBER_FIELDS: { name: NumberField; label: string }[] = [
  { name: "visitor_questions_per_hour", label: "Questions per visitor per hour" },
  { name: "max_question_length", label: "Longest question (characters)" },
  { name: "max_answer_length", label: "Longest answer (characters)" },
  { name: "daily_token_cap", label: "Daily token cap" },
];
const BYTES_PER_KILOBYTE = 1024;

function formOf(settings: Settings): Form {
  return {
    enabled: settings.enabled,
    model: settings.model,
    version: String(settings.prompt_version),
    visitor_questions_per_hour: String(settings.visitor_questions_per_hour),
    max_question_length: String(settings.max_question_length),
    max_answer_length: String(settings.max_answer_length),
    daily_token_cap: String(settings.daily_token_cap),
  };
}

/** The website chatbot's admin page: the on/off switch, model, prompt version and limits, and the
 * public product documents it may use. Only the extracted text of a document is kept. */
export function ChatbotAdmin() {
  const [state, setState] = useState<State | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [open, setOpen] = useState<Open | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const take = useCallback((result: ApiResult<State>): boolean => {
    if (!result.ok) {
      setError(result.error);
      return false;
    }
    setError(null);
    setState(result.data);
    setForm(formOf(result.data.settings));
    return true;
  }, []);
  useEffect(() => {
    void getJson<State>(BASE).then(take);
  }, [take]);

  if (!state || !form) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const fields = error?.fields ?? {};
  const change = (patch: Partial<Form>) => setForm({ ...form, ...patch });
  // The confirm button also closes the popup, so a refusal is shown on the page, below the list.
  const close = () => {
    setOpen(null);
    setFile(null);
  };
  const show = (next: Open) => {
    setError(null);
    setOpen(next);
  };

  async function confirm() {
    if (!open) return;
    let result: ApiResult<State> | null = null;
    if (open.kind === "save") {
      result = await putJson<State>(BASE, {
        enabled: form!.enabled,
        model: form!.model,
        prompt_version: Number(form!.version),
        ...Object.fromEntries(NUMBER_FIELDS.map(({ name }) => [name, Number(form![name])])),
      });
    } else if (open.kind === "delete") {
      result = await deleteJson<State>(`${BASE}documents/${open.document.id}/`);
    } else {
      if (!file)
        return setError({
          code: "file_missing",
          message: "Choose a file.",
          fields: { file: "Choose a file." },
        });
      const body = new FormData();
      body.append("file", file);
      result =
        open.kind === "add"
          ? await postForm<State>(`${BASE}documents/`, body)
          : await putForm<State>(`${BASE}documents/${open.document.id}/`, body);
    }
    take(result);
  }

  async function switchDocument(document: KnowledgeDocument) {
    take(
      await patchJson<State>(`${BASE}documents/${document.id}/`, { enabled: !document.enabled }),
    );
  }

  const titles = {
    save: "Save chatbot settings",
    add: "Add document",
    replace: "Replace document",
    delete: "Delete document",
  };
  const labels = { save: "Save", add: "Add", replace: "Replace", delete: "Delete" };
  const { settings } = state;
  return (
    <div className="page-stack">
      <div className="page-form">
        <Checkbox
          label="Chatbot on"
          checked={form.enabled}
          onChange={(event) => change({ enabled: event.target.checked })}
        />
        <Select
          label="Model"
          options={[
            { value: "", label: "No model" },
            ...settings.models.map((name) => ({ value: name, label: name })),
          ]}
          value={form.model}
          error={fields.model}
          onChange={(event) => change({ model: event.target.value })}
        />
        <Select
          label="Prompt version"
          options={settings.prompt_versions.map((number) => ({
            value: String(number),
            label: String(number),
          }))}
          value={form.version}
          onChange={(event) => change({ version: event.target.value })}
        />
        {NUMBER_FIELDS.map(({ name, label }) => (
          <Input
            key={name}
            label={label}
            inputMode="numeric"
            value={form[name]}
            error={fields[name]}
            onChange={(event) => change({ [name]: event.target.value })}
          />
        ))}
        {fields.enabled && (
          <p className="ui-error" role="alert">
            {fields.enabled}
          </p>
        )}
        <div className="page-actions">
          <Button onClick={() => show({ kind: "save" })}>Save settings</Button>
        </div>
      </div>
      <div className="page-actions">
        <Button variant="secondary" onClick={() => show({ kind: "add" })}>
          Add document
        </Button>
      </div>
      <Table label="Documents">
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Size</th>
            <th>Characters</th>
            <th>Status</th>
            <th>Updated</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {state.documents.map((document) => (
            <tr key={document.id}>
              <td>{document.name}</td>
              <td>{document.file_type.toUpperCase()}</td>
              <td>{Math.max(1, Math.round(document.size_bytes / BYTES_PER_KILOBYTE))} KB</td>
              <td>{document.characters}</td>
              <td>
                <Tag variant={document.enabled ? "success" : "neutral"}>
                  {document.enabled ? "On" : "Off"}
                </Tag>
              </td>
              <td>{new Date(document.updated_at).toLocaleDateString()}</td>
              <td>
                <Button
                  variant="secondary"
                  aria-label={`${document.enabled ? "Switch off" : "Switch on"} ${document.name}`}
                  onClick={() => void switchDocument(document)}
                >
                  {document.enabled ? "Switch off" : "Switch on"}
                </Button>{" "}
                <Button
                  variant="secondary"
                  aria-label={`Replace ${document.name}`}
                  onClick={() => show({ kind: "replace", document })}
                >
                  Replace
                </Button>{" "}
                <Button
                  variant="secondary"
                  aria-label={`Delete ${document.name}`}
                  onClick={() => show({ kind: "delete", document })}
                >
                  Delete
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      <Dialog
        open={open !== null}
        onOpenChange={(next) => !next && close()}
        title={open ? titles[open.kind] : ""}
        confirmLabel={open ? labels[open.kind] : undefined}
        onConfirm={() => void confirm()}
        destructive={open?.kind === "delete"}
      >
        {open?.kind === "delete" && <p>{open.document.name}</p>}
        {(open?.kind === "add" || open?.kind === "replace") && (
          <Input
            label="File"
            type="file"
            accept=".pdf,.docx,.txt,.md"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        )}
      </Dialog>
    </div>
  );
}
