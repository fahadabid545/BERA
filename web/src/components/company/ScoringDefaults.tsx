"use client";

import { useEffect, useState, type FormEvent } from "react";

import { FACTORS } from "@/components/company/ExtraFactors";
import { Button, Checkbox, Dialog, Input } from "@/components/ui";
import { getJson, putJson, type ApiError } from "@/lib/api";

type Setting = { enabled: boolean; weight: number | string };
type Defaults = {
  must_weight_percent: number;
  nice_weight_percent: number;
  recommendation_threshold: number;
  top_n: number;
  cap_on_missing_must_have: boolean;
  factors: Record<string, Setting>;
  top_n_cap: number;
};

const URL = "/api/company/scoring-defaults/";
const TOTAL = 100;
const toNumber = (text: string) => (text.trim() === "" ? Number.NaN : Number(text));

/** What the company's new projects start with: the scoring numbers and the extra factors. The
 * nice-to-have weight is always what is left of 100. Projects that exist are never changed. */
export function ScoringDefaults() {
  const [loaded, setLoaded] = useState<Defaults | null>(null);
  const [mustWeight, setMustWeight] = useState("");
  const [threshold, setThreshold] = useState("");
  const [topN, setTopN] = useState("");
  const [capOnMissing, setCapOnMissing] = useState(false);
  const [factors, setFactors] = useState<Record<string, Setting>>({});
  const [error, setError] = useState<ApiError | null>(null);
  const [saved, setSaved] = useState(false);

  function show(data: Defaults) {
    setLoaded(data);
    setMustWeight(String(data.must_weight_percent));
    setThreshold(String(data.recommendation_threshold));
    setTopN(String(data.top_n));
    setCapOnMissing(data.cap_on_missing_must_have);
    setFactors(data.factors);
  }
  useEffect(() => {
    void getJson<Defaults>(URL).then((result) => {
      if (result.ok) show(result.data);
      else setError(result.error);
    });
  }, []);

  const change = (name: string, changes: Partial<Setting>) =>
    setFactors((current) => ({ ...current, [name]: { ...current[name], ...changes } }));

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const must = toNumber(mustWeight);
    const result = await putJson<Defaults>(URL, {
      must_weight_percent: must,
      nice_weight_percent: TOTAL - must,
      recommendation_threshold: toNumber(threshold),
      top_n: toNumber(topN),
      cap_on_missing_must_have: capOnMissing,
      factors: Object.fromEntries(
        Object.entries(factors).map(([name, setting]) => [
          name,
          { enabled: setting.enabled, weight: toNumber(String(setting.weight)) },
        ]),
      ),
    });
    if (!result.ok) return setError(result.error);
    show(result.data);
    setSaved(true);
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
        type="number"
        value={threshold}
        onChange={(event) => setThreshold(event.target.value)}
        error={fields.recommendation_threshold}
      />
      <Input
        label={`Top list size (up to ${loaded.top_n_cap})`}
        type="number"
        value={topN}
        onChange={(event) => setTopN(event.target.value)}
        error={fields.top_n}
      />
      <Checkbox
        label="Cap the score when a must-have is missing"
        checked={capOnMissing}
        onChange={(event) => setCapOnMissing(event.target.checked)}
      />
      {FACTORS.map(({ name, label }) => (
        <div key={name} className="page-form">
          <Checkbox
            label={label}
            checked={factors[name]?.enabled ?? false}
            onChange={(event) => change(name, { enabled: event.target.checked })}
          />
          <Input
            label={`${label} weight (%)`}
            type="number"
            value={String(factors[name]?.weight ?? "")}
            onChange={(event) => change(name, { weight: event.target.value })}
            error={fields[`factors.${name}`]}
          />
        </div>
      ))}
      {generalError && (
        <p className="ui-error" role="alert">
          {generalError}
        </p>
      )}
      <div className="page-actions">
        <Button type="submit">Save</Button>
      </div>
      <Dialog open={saved} onOpenChange={setSaved} title="Scoring defaults saved" />
    </form>
  );
}
