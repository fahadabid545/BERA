"use client";

import { Button, Checkbox, Dialog } from "@/components/ui";

import type { Requirement } from "./types";

/** Chooses which requirement columns the matrix shows. At least one stays on. */
export function ColumnPicker({
  requirements,
  hidden,
  onChange,
}: {
  requirements: Requirement[];
  hidden: string[];
  onChange: (hidden: string[]) => void;
}) {
  const shownCount = requirements.filter((requirement) => !hidden.includes(requirement.id)).length;
  const toggle = (id: string, show: boolean) =>
    onChange(show ? hidden.filter((other) => other !== id) : [...hidden, id]);
  return (
    <Dialog
      trigger={<Button variant="secondary">Columns</Button>}
      title="Columns"
      description={`${shownCount} of ${requirements.length} shown. At least one stays on.`}
    >
      <div className="column-picker__actions">
        <Button variant="secondary" onClick={() => onChange([])}>
          Select all
        </Button>
        <Button
          variant="secondary"
          onClick={() =>
            onChange(
              requirements
                .filter((requirement) => requirement.kind !== "must")
                .map((requirement) => requirement.id),
            )
          }
        >
          Must-haves only
        </Button>
      </div>
      <div className="column-picker__list">
        {requirements.map((requirement) => {
          const shown = !hidden.includes(requirement.id);
          return (
            <Checkbox
              key={requirement.id}
              label={requirement.text}
              checked={shown}
              disabled={shown && shownCount === 1}
              onChange={(event) => toggle(requirement.id, event.target.checked)}
            />
          );
        })}
      </div>
    </Dialog>
  );
}
