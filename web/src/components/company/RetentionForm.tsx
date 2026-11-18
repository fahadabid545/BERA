"use client";

import { useState } from "react";

import { Button, Dialog, Select } from "@/components/ui";

import { useCompanySettings, type RetentionPreview } from "./companySettings";

const DEFAULT = "default";

const count = (value: number, one: string, many: string) => `${value} ${value === 1 ? one : many}`;

/** What saving would delete, in words, for the confirmation. */
function deletionText(days: number, due: RetentionPreview | null) {
  if (!due || (due.cvs === 0 && due.shared_links === 0)) {
    return `CVs, scores, notes and files older than ${days} days are deleted automatically.`;
  }
  const parts = [`${count(due.cvs, "CV", "CVs")} in ${count(due.projects, "project", "projects")}`];
  if (due.shared_links > 0) parts.push(count(due.shared_links, "shared link", "shared links"));
  return `Saving deletes ${parts.join(" and ")}, with their scores, notes and files. CVs older than ${days} days are deleted automatically.`;
}

/** How long candidate data and the activity log are kept: one of the platform's choices, or the
 * platform default. A shorter time shows what it deletes first, and saving asks to confirm. */
export function RetentionForm() {
  const { settings, error, saved, setSaved, save, preview } = useCompanySettings();
  const [choice, setChoice] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [due, setDue] = useState<RetentionPreview | null>(null);

  if (!settings) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const { retention } = settings;
  const current = retention.chosen === null ? DEFAULT : String(retention.chosen);
  const shown = choice ?? current;
  const days = shown === DEFAULT ? retention.default_days : Number(shown);
  const shortening = days < retention.days;

  async function review() {
    setDue(shortening ? await preview(days) : null);
    setConfirming(true);
  }

  return (
    <>
      <form className="page-form" onSubmit={(event) => event.preventDefault()}>
        <Select
          label="Retention"
          value={shown}
          error={error?.fields?.retention_days}
          onChange={(event) => setChoice(event.target.value)}
          options={[
            { value: DEFAULT, label: `Platform default (${retention.default_days} days)` },
            ...retention.choices.map((value) => ({ value: String(value), label: `${value} days` })),
          ]}
        />
        {error && !error.fields?.retention_days && (
          <p className="ui-error" role="alert">
            {error.message}
          </p>
        )}
        <div className="page-actions">
          <Button type="button" disabled={shown === current} onClick={() => void review()}>
            Save
          </Button>
        </div>
      </form>
      <Dialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Save retention"
        description={deletionText(days, due)}
        confirmLabel="Save"
        onConfirm={() =>
          void save({
            retention_days: shown === DEFAULT ? null : Number(shown),
            ...(due && (due.cvs > 0 || due.shared_links > 0) ? { acknowledge_deletion: true } : {}),
          }).then(() => setChoice(null))
        }
      />
      <Dialog open={saved} onOpenChange={setSaved} title="Retention saved" />
    </>
  );
}
