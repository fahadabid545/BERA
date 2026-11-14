"use client";

import { useState } from "react";

import { Button, Checkbox, Dialog, Input } from "@/components/ui";

import { STAGES } from "./stages";

/** The filters, as the values of the address. A list value holds its choices separated by commas. */
export type Filters = Record<string, string>;
export type RequirementChoice = { id: string; text: string; kind: "must" | "nice" };

export const FILTER_KEYS = [
  "score_min",
  "score_max",
  "ats_min",
  "ats_max",
  "years_min",
  "years_max",
  "grade",
  "label",
  "stage",
  "missing",
  "has",
  "added_from",
  "added_to",
  "duplicate",
  "q",
] as const;

const GRADES = ["A", "B", "C", "D", "E"].map((value) => ({ value, label: value }));
const LABELS = [
  { value: "strong_match", label: "Strong match" },
  { value: "possible", label: "Possible" },
  { value: "not_recommended", label: "Not recommended" },
];
const RANGES = [
  { name: "score", label: "AI score" },
  { name: "ats", label: "ATS score" },
  { name: "years", label: "Years of experience" },
] as const;

const chosen = (value: string | undefined) => (value ? value.split(",") : []);

function Choices({
  legend,
  options,
  value,
  onChange,
}: {
  legend: string;
  options: { value: string; label: string }[];
  value: string | undefined;
  onChange: (next: string) => void;
}) {
  const selected = chosen(value);
  return (
    <fieldset className="ui-fieldset">
      <legend className="ui-label">{legend}</legend>
      {options.map((option) => (
        <Checkbox
          key={option.value}
          label={option.label}
          checked={selected.includes(option.value)}
          onChange={(event) =>
            onChange(
              (event.target.checked
                ? [...selected, option.value]
                : selected.filter((item) => item !== option.value)
              ).join(","),
            )
          }
        />
      ))}
    </fieldset>
  );
}

/** The Filters button and its popup. Applying hands the whole set to the page, which keeps it in
 * the address; the popup only edits a copy until then. */
export function CandidateFilters({
  filters,
  requirements,
  onApply,
  onClearAll,
}: {
  filters: Filters;
  requirements: RequirementChoice[];
  onApply: (next: Filters) => void;
  onClearAll: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Filters>(filters);
  const active = Object.keys(filters).length;
  const set = (name: string, value: string) =>
    setDraft((current) => ({ ...current, [name]: value }));
  const requirementOptions = (kind?: "must") =>
    requirements
      .filter((item) => !kind || item.kind === kind)
      .map((item) => ({ value: item.id, label: item.text }));

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (next) setDraft(filters);
        setOpen(next);
      }}
      trigger={<Button variant="secondary">{active ? `Filters (${active})` : "Filters"}</Button>}
      title="Filters"
      confirmLabel="Apply filters"
      onConfirm={() => onApply(Object.fromEntries(Object.entries(draft).filter(([, v]) => v)))}
      actions={
        <Button
          variant="secondary"
          onClick={() => {
            setOpen(false);
            onClearAll();
          }}
        >
          Clear all
        </Button>
      }
    >
      <Input
        label="Search file name and summary"
        value={draft.q ?? ""}
        onChange={(event) => set("q", event.target.value)}
      />
      {RANGES.map(({ name, label }) => (
        <div key={name} className="ui-filter-range">
          <Input
            label={`${label}, from`}
            type="number"
            min={0}
            value={draft[`${name}_min`] ?? ""}
            onChange={(event) => set(`${name}_min`, event.target.value)}
          />
          <Input
            label={`${label}, to`}
            type="number"
            min={0}
            value={draft[`${name}_max`] ?? ""}
            onChange={(event) => set(`${name}_max`, event.target.value)}
          />
        </div>
      ))}
      <div className="ui-filter-range">
        <Input
          label="Added from"
          type="date"
          value={draft.added_from ?? ""}
          onChange={(event) => set("added_from", event.target.value)}
        />
        <Input
          label="Added to"
          type="date"
          value={draft.added_to ?? ""}
          onChange={(event) => set("added_to", event.target.value)}
        />
      </div>
      <Choices
        legend="Grade"
        options={GRADES}
        value={draft.grade}
        onChange={(v) => set("grade", v)}
      />
      <Choices
        legend="Recommendation"
        options={LABELS}
        value={draft.label}
        onChange={(v) => set("label", v)}
      />
      <Choices
        legend="Stage"
        options={STAGES}
        value={draft.stage}
        onChange={(v) => set("stage", v)}
      />
      {requirements.length > 0 && (
        <>
          <Choices
            legend="Missing the must-have"
            options={requirementOptions("must")}
            value={draft.missing}
            onChange={(v) => set("missing", v)}
          />
          <Choices
            legend="Meets the requirement"
            options={requirementOptions()}
            value={draft.has}
            onChange={(v) => set("has", v)}
          />
        </>
      )}
      <Checkbox
        label="Likely duplicates only"
        checked={draft.duplicate === "true"}
        onChange={(event) => set("duplicate", event.target.checked ? "true" : "")}
      />
    </Dialog>
  );
}
