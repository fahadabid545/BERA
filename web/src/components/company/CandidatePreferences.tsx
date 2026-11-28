"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Checkbox, Dialog } from "@/components/ui";
import { getJson, putJson, type ApiError } from "@/lib/api";

type Preferences = { hide_contact_by_default: boolean };

/** How the project's candidates are handled. One Save for the whole section. */
export function CandidatePreferences({
  projectId,
  readOnly,
}: {
  projectId: string;
  readOnly: boolean;
}) {
  const url = `/api/company/projects/${projectId}/preferences/`;
  const [saved, setSaved] = useState<Preferences | null>(null);
  const [draft, setDraft] = useState<Preferences | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [done, setDone] = useState(false);

  const load = useCallback(async () => {
    const result = await getJson<Preferences>(url);
    if (result.ok) {
      setSaved(result.data);
      setDraft(result.data);
    } else setError(result.error);
  }, [url]);
  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    if (!draft) return;
    setError(null);
    const result = await putJson<Preferences>(url, draft);
    if (result.ok) {
      setSaved(result.data);
      setDraft(result.data);
      setDone(true);
    } else setError(result.error);
  }

  if (!draft || !saved) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const changed = draft.hide_contact_by_default !== saved.hide_contact_by_default;
  return (
    <section className="page-form" aria-labelledby="candidate-preferences">
      <h2 id="candidate-preferences">Candidates</h2>
      <Checkbox
        label="Hide contact details in new shared reports"
        checked={draft.hide_contact_by_default}
        disabled={readOnly}
        onChange={(event) => setDraft({ ...draft, hide_contact_by_default: event.target.checked })}
      />
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      {!readOnly && (
        <div className="page-actions">
          <Button disabled={!changed} onClick={() => void save()}>
            Save candidate settings
          </Button>
        </div>
      )}
      <Dialog open={done} onOpenChange={setDone} title="Candidate settings saved" />
    </section>
  );
}
