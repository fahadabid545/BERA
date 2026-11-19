"use client";

import { useEffect, useState } from "react";

import { Button, Checkbox, Dialog } from "@/components/ui";
import { getJson, patchJson, type ApiError } from "@/lib/api";

type Choice = { kind: string; label: string; required: boolean; enabled: boolean };

const URL = "/api/company/notifications/";

/** Which emails the signed-in person gets. Billing and security emails are listed switched on
 * and cannot be changed. Saving asks to confirm. */
export function NotificationChoices() {
  const [choices, setChoices] = useState<Choice[] | null>(null);
  const [wanted, setWanted] = useState<Record<string, boolean>>({});
  const [confirming, setConfirming] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    void getJson<{ choices: Choice[] }>(URL).then((result) => {
      if (result.ok) setChoices(result.data.choices);
      else setError(result.error);
    });
  }, []);

  if (!choices) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }

  const shown = (choice: Choice) => wanted[choice.kind] ?? choice.enabled;
  const changed = choices.filter((choice) => !choice.required && shown(choice) !== choice.enabled);

  async function save() {
    let latest = choices;
    for (const choice of changed) {
      const result = await patchJson<{ choices: Choice[] }>(URL, {
        kind: choice.kind,
        enabled: shown(choice),
      });
      if (!result.ok) {
        setError(result.error);
        return;
      }
      latest = result.data.choices;
    }
    setError(null);
    setChoices(latest);
    setWanted({});
    setSaved(true);
  }

  return (
    <>
      <form className="page-form" onSubmit={(event) => event.preventDefault()}>
        {choices.map((choice) => (
          <Checkbox
            key={choice.kind}
            label={choice.label}
            checked={choice.required || shown(choice)}
            disabled={choice.required}
            onChange={(event) => setWanted({ ...wanted, [choice.kind]: event.target.checked })}
          />
        ))}
        {error && (
          <p className="ui-error" role="alert">
            {error.message}
          </p>
        )}
        <div className="page-actions">
          <Button type="button" disabled={changed.length === 0} onClick={() => setConfirming(true)}>
            Save
          </Button>
        </div>
      </form>
      <Dialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Save notifications"
        confirmLabel="Save"
        onConfirm={() => void save()}
      />
      <Dialog open={saved} onOpenChange={setSaved} title="Notifications saved" />
    </>
  );
}
