"use client";

import { useState } from "react";

import { Button, Dialog, Select } from "@/components/ui";

import { useCompanySettings } from "./companySettings";

const DEFAULT = "default";

/** How long the company's activity log is kept: one of the platform's choices, or the platform
 * default. A shorter time hides older entries at once, so saving asks first. */
export function RetentionForm() {
  const { settings, error, saved, setSaved, save } = useCompanySettings();
  const [choice, setChoice] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

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
          <Dialog
            open={confirming}
            onOpenChange={setConfirming}
            trigger={
              <Button type="button" disabled={shown === current}>
                Save
              </Button>
            }
            title="Save retention"
            description={`Activity older than ${days} days will no longer be shown or kept.`}
            confirmLabel="Save"
            onConfirm={() =>
              void save({ retention_days: shown === DEFAULT ? null : Number(shown) }).then(() =>
                setChoice(null),
              )
            }
          />
        </div>
      </form>
      <Dialog open={saved} onOpenChange={setSaved} title="Retention saved" />
    </>
  );
}
