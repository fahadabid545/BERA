"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Dialog, Input, Select } from "@/components/ui";
import { getJson, putJson, type ApiError } from "@/lib/api";

import { RequirementSuggestions, type SuggestedRequirement } from "./RequirementSuggestions";

type Row = { id?: string; key: string; kind: "must" | "nice"; text: string; weight: number };
type Saved = {
  requirements: { id: string; kind: "must" | "nice"; text: string; weight: number }[];
  warnings: { code: string; message: string }[];
};
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

  const load = useCallback(async () => {
    const result = await getJson<Saved>(base);
    if (result.ok) {
      setRows(toRows(result.data.requirements));
      setWarnings(result.data.warnings);
    } else setError(result.error);
  }, [base]);
  useEffect(() => {
    void load();
  }, [load]);

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
      setRows(toRows(result.data.requirements));
      setWarnings(result.data.warnings);
      return setSaved(true);
    }
    if (result.error.code === "rescoring_needed") {
      return setRescoring(result.error.details as unknown as Rescoring);
    }
    setError(result.error);
  }

  const fieldError = error?.fields ? Object.values(error.fields)[0] : null;
  return (
    <div className="page-stack">
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
