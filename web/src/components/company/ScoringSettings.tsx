"use client";

import { useEffect, useState, type FormEvent } from "react";

import { RenewalPrompt, UpgradePrompt } from "@/components/company/BillingPrompt";
import { Button, Checkbox, Dialog, Input } from "@/components/ui";
import { getJson, putJson, type ApiError } from "@/lib/api";

type Scoring = {
  must_weight_percent: number;
  nice_weight_percent: number;
  recommendation_threshold: number;
  top_n: number;
  cap_on_missing_must_have: boolean;
  top_n_cap: number;
};

const TOTAL = 100;
const toNumber = (text: string) => (text.trim() === "" ? Number.NaN : Number(text));

/** How scores are calculated for one project. The nice-to-have weight is always what is left
 * of 100, so the two can never disagree on screen. */
export function ScoringSettings({ projectId }: { projectId: string }) {
  const base = `/api/company/projects/${projectId}/scoring/`;
  const [loaded, setLoaded] = useState<Scoring | null>(null);
  const [mustWeight, setMustWeight] = useState("");
  const [capOnMissing, setCapOnMissing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [saved, setSaved] = useState(false);
  const [prompt, setPrompt] = useState<"upgrade" | "renewal" | null>(null);

  useEffect(() => {
    void getJson<Scoring>(base).then((result) => {
      if (!result.ok) return setError(result.error);
      setLoaded(result.data);
      setMustWeight(String(result.data.must_weight_percent));
      setCapOnMissing(result.data.cap_on_missing_must_have);
    });
  }, [base]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const must = toNumber(mustWeight);
    setError(null);
    const result = await putJson<Scoring>(base, {
      must_weight_percent: must,
      nice_weight_percent: TOTAL - must,
      recommendation_threshold: toNumber(String(form.get("recommendation_threshold") ?? "")),
      top_n: toNumber(String(form.get("top_n") ?? "")),
      cap_on_missing_must_have: capOnMissing,
    });
    if (result.ok) {
      setLoaded(result.data);
      return setSaved(true);
    }
    const promptKind = result.error.details?.prompt;
    if (promptKind === "upgrade" || promptKind === "renewal") return setPrompt(promptKind);
    setError(result.error);
  }

  if (!loaded) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const fields = error?.fields ?? {};
  const generalError = error && Object.keys(fields).length === 0 ? error.message : null;
  const nice = Number.isNaN(toNumber(mustWeight)) ? "" : String(TOTAL - toNumber(mustWeight));
  return (
    <form className="page-form" onSubmit={save} noValidate>
      <Input
        label="Must-have weight (%)"
        type="number"
        value={mustWeight}
        onChange={(event) => setMustWeight(event.target.value)}
        error={fields.must_weight_percent}
      />
      <Input
        label="Nice-to-have weight (%)"
        type="number"
        value={nice}
        readOnly
        error={fields.nice_weight_percent}
      />
      <Input
        label="Recommendation threshold (%)"
        name="recommendation_threshold"
        type="number"
        defaultValue={loaded.recommendation_threshold}
        error={fields.recommendation_threshold}
      />
      <Input
        label={`Top list size (up to ${loaded.top_n_cap})`}
        name="top_n"
        type="number"
        defaultValue={loaded.top_n}
        error={fields.top_n}
      />
      <Checkbox
        label="Cap the score when a must-have is missing"
        checked={capOnMissing}
        onChange={(event) => setCapOnMissing(event.target.checked)}
      />
      {generalError && (
        <p className="ui-error" role="alert">
          {generalError}
        </p>
      )}
      <div className="page-actions">
        <Button type="submit">Save scoring settings</Button>
      </div>
      <Dialog open={saved} onOpenChange={setSaved} title="Scoring settings saved" />
      <UpgradePrompt
        open={prompt === "upgrade"}
        onOpenChange={(open) => !open && setPrompt(null)}
      />
      <RenewalPrompt
        open={prompt === "renewal"}
        onOpenChange={(open) => !open && setPrompt(null)}
      />
    </form>
  );
}
