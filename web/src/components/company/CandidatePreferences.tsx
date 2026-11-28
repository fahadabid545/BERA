"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Checkbox, Dialog, Input } from "@/components/ui";
import { getJson, putJson, type ApiError } from "@/lib/api";

type Preferences = {
  hide_contact_by_default: boolean;
  auto_shortlist: boolean;
  auto_reject_below: number | null;
};
type Answer = Preferences & { labels: string[] };

// Labels have their own section, so this one never sends them.
function candidateFields({ labels: _labels, ...fields }: Answer): Preferences {
  return fields;
}

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
    const result = await getJson<Answer>(url);
    if (result.ok) {
      setSaved(candidateFields(result.data));
      setDraft(candidateFields(result.data));
    } else setError(result.error);
  }, [url]);
  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    if (!draft) return;
    setError(null);
    const result = await putJson<Answer>(url, draft);
    if (result.ok) {
      setSaved(candidateFields(result.data));
      setDraft(candidateFields(result.data));
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
  const changed = JSON.stringify(draft) !== JSON.stringify(saved);
  return (
    <section className="page-form" aria-labelledby="candidate-preferences">
      <h2 id="candidate-preferences">Candidates</h2>
      <Checkbox
        label="Hide contact details in new shared reports"
        checked={draft.hide_contact_by_default}
        disabled={readOnly}
        onChange={(event) => setDraft({ ...draft, hide_contact_by_default: event.target.checked })}
      />
      <Checkbox
        label="Shortlist strong matches automatically"
        checked={draft.auto_shortlist}
        disabled={readOnly}
        onChange={(event) => setDraft({ ...draft, auto_shortlist: event.target.checked })}
      />
      <Input
        label="Reject new candidates scoring below"
        type="number"
        inputMode="numeric"
        min={0}
        max={100}
        value={draft.auto_reject_below ?? ""}
        readOnly={readOnly}
        error={error?.fields?.auto_reject_below}
        onChange={(event) =>
          setDraft({
            ...draft,
            auto_reject_below: event.target.value === "" ? null : Number(event.target.value),
          })
        }
      />
      {error && !error.fields && (
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
