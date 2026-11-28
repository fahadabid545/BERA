"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Dialog, Input, Select } from "@/components/ui";
import { getJson, postJson, putJson, type ApiError } from "@/lib/api";
import { startLive } from "@/lib/live";

import { RequirementSuggestions, type SuggestedRequirement } from "./RequirementSuggestions";

type Row = { id?: string; key: string; kind: "must" | "nice"; text: string; weight: number };
type Saved = {
  requirements: { id: string; kind: "must" | "nice"; text: string; weight: number }[];
  warnings: { code: string; message: string }[];
  status?: ListStatus;
  notice?: string;
  refresh_seconds: number;
};
type ListStatus = "drafting" | "draft" | "confirmed";
type Rescoring = { cvs: number; estimated_cost: string };

const KINDS = [
  { value: "must", label: "Must have" },
  { value: "nice", label: "Nice to have" },
];
const WEIGHTS = [1, 2, 3, 4, 5].map((weight) => ({ value: String(weight), label: String(weight) }));
const DEFAULT_WEIGHT = 3;

let nextKey = 0;
const newKey = () => `row-${nextKey++}`;
const toRows = (saved: Saved["requirements"]): Row[] =>
  saved.map((requirement) => ({ ...requirement, key: newKey() }));

/** Add, edit, remove and reorder a project's requirements, saved as one list. */
export function RequirementEditor({ projectId }: { projectId: string }) {
  const base = `/api/company/projects/${projectId}/requirements/`;
  const [rows, setRows] = useState<Row[]>([]);
  const [warnings, setWarnings] = useState<Saved["warnings"]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [saved, setSaved] = useState(false);
  const [rescoring, setRescoring] = useState<Rescoring | null>(null);
  const [listStatus, setListStatus] = useState<ListStatus>("confirmed");
  const [notice, setNotice] = useState("");
  const [rereading, setRereading] = useState(false);

  const show = useCallback((data: Saved) => {
    setRows(toRows(data.requirements));
    setWarnings(data.warnings);
    setListStatus(data.status ?? "confirmed");
    setNotice(data.notice ?? "");
  }, []);
  const load = useCallback(async () => {
    const result = await getJson<Saved>(base);
    if (result.ok) show(result.data);
    else setError(result.error);
  }, [base, show]);
  useEffect(() => {
    void load();
  }, [load]);
  // While the AI reads the job description, ask again until its draft arrives. The person's own
  // edits are left alone until then.
  useEffect(() => {
    if (listStatus !== "drafting") return;
    return startLive(
      () => getJson<Saved>(base),
      (result) => {
        if (result.ok && result.data.status !== "drafting") show(result.data);
      },
    );
  }, [listStatus, base, show]);

  const change = (key: string, changes: Partial<Row>) =>
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...changes } : row)));
  const move = (index: number, step: number) =>
    setRows((current) => {
      const target = index + step;
      if (target < 0 || target >= current.length) return current;
      const copy = [...current];
      [copy[index], copy[target]] = [copy[target], copy[index]];
      return copy;
    });
  const add = (items: SuggestedRequirement[] = [{ kind: "must", text: "" }]) =>
    setRows((current) => [
      ...current,
      ...items.map((item) => ({ ...item, weight: DEFAULT_WEIGHT, key: newKey() })),
    ]);

  async function save(acknowledgeRescoring: boolean) {
    setError(null);
    const result = await putJson<Saved>(base, {
      requirements: rows.map(({ id, kind, text, weight }) => ({ id, kind, text, weight })),
      acknowledge_rescoring: acknowledgeRescoring,
    });
    if (result.ok) {
      show(result.data);
      return setSaved(true);
    }
    if (result.error.code === "rescoring_needed") {
      return setRescoring(result.error.details as unknown as Rescoring);
    }
    setError(result.error);
  }

  async function confirm() {
    setError(null);
    const result = await postJson<Saved>(`${base}confirm/`, {});
    if (result.ok) show(result.data);
    else setError(result.error);
  }

  async function readAgain() {
    setRereading(false);
    setError(null);
    const result = await postJson<Saved>(`${base}reread/`, {});
    if (result.ok) show(result.data);
    else setError(result.error);
  }

  const fieldError = error?.fields ? Object.values(error.fields)[0] : null;
  return (
    <div className="page-stack">
      {listStatus === "drafting" && <p role="status">Reading the job description</p>}
      {listStatus === "draft" && (
        <div className="page-actions">
          <p role="status">Draft, not confirmed yet</p>
          <Button onClick={() => void confirm()} disabled={rows.length === 0}>
            Confirm requirements
          </Button>
          <Button variant="secondary" onClick={() => setRereading(true)}>
            Read job description again
          </Button>
        </div>
      )}
      {listStatus === "draft" && notice && <p role="status">{notice}</p>}
      {rows.map((row, index) => (
        <div className="page-actions" key={row.key}>
          <Select
            label={`Type ${index + 1}`}
            options={KINDS}
            value={row.kind}
            onChange={(event) => change(row.key, { kind: event.target.value as Row["kind"] })}
          />
          <Input
            label={`Requirement ${index + 1}`}
            value={row.text}
            onChange={(event) => change(row.key, { text: event.target.value })}
          />
          <Select
            label={`Weight ${index + 1}`}
            options={WEIGHTS}
            value={String(row.weight)}
            onChange={(event) => change(row.key, { weight: Number(event.target.value) })}
          />
          <Button
            variant="secondary"
            aria-label={`Move requirement ${index + 1} up`}
            disabled={index === 0}
            onClick={() => move(index, -1)}
          >
            Up
          </Button>
          <Button
            variant="secondary"
            aria-label={`Move requirement ${index + 1} down`}
            disabled={index === rows.length - 1}
            onClick={() => move(index, 1)}
          >
            Down
          </Button>
          <Button
            variant="secondary"
            aria-label={`Remove requirement ${index + 1}`}
            onClick={() => setRows((current) => current.filter((r) => r.key !== row.key))}
          >
            Remove
          </Button>
        </div>
      ))}
      {warnings.map((warning, index) => (
        <p key={`${warning.code}-${index}`} role="status">
          {warning.message}
        </p>
      ))}
      {(fieldError || (error && !error.fields)) && (
        <p className="ui-error" role="alert">
          {fieldError ?? error?.message}
        </p>
      )}
      <div className="page-actions">
        <Button variant="secondary" onClick={() => add()}>
          Add requirement
        </Button>
        <Button onClick={() => save(false)}>Save</Button>
      </div>
      <RequirementSuggestions projectId={projectId} onUse={add} />
      <Dialog
        open={rereading}
        onOpenChange={setRereading}
        title="Read job description again"
        description="The draft below will be replaced."
        confirmLabel="Read again"
        onConfirm={() => void readAgain()}
      />
      <Dialog open={saved} onOpenChange={setSaved} title="Requirements saved" />
      <Dialog
        open={rescoring !== null}
        onOpenChange={(open) => !open && setRescoring(null)}
        title="Re-scoring needed"
        description={
          rescoring
            ? `${rescoring.cvs} CVs will be scored again. Estimated cost: ${rescoring.estimated_cost}.`
            : undefined
        }
        confirmLabel="Save changes"
        onConfirm={() => {
          setRescoring(null);
          void save(true);
        }}
      />
    </div>
  );
}
