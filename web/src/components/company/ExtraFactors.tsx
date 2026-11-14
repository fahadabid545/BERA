"use client";

import { useEffect, useState, type FormEvent } from "react";

import { Button, Checkbox, Dialog, Input, Select } from "@/components/ui";
import { getJson, putJson, type ApiError } from "@/lib/api";

type Setting = { enabled: boolean; weight: number | string };
type Factors = {
  required_years: number | null;
  required_education: string | null;
  seniority: string | null;
  factors: Record<string, Setting>;
  max_required_years: number;
};

const FACTORS: { name: string; label: string }[] = [
  { name: "experience_years", label: "Experience years match" },
  { name: "education", label: "Education match" },
  { name: "seniority", label: "Seniority fit" },
  { name: "recency", label: "Recency of relevant work" },
  { name: "gaps_and_changes", label: "Career gaps and job changes" },
  { name: "readability", label: "CV readability" },
  { name: "confidence", label: "Confidence level" },
];
const EDUCATION = [
  { value: "", label: "Not set" },
  { value: "bachelor", label: "Bachelor" },
  { value: "master", label: "Master" },
  { value: "doctorate", label: "Doctorate" },
];
const SENIORITY = [
  { value: "", label: "Not set" },
  { value: "junior", label: "Junior" },
  { value: "mid", label: "Mid" },
  { value: "senior", label: "Senior" },
  { value: "lead", label: "Lead" },
];
const toNumber = (text: string) => (text.trim() === "" ? Number.NaN : Number(text));

/** The optional scoring factors of one project: each can be switched on or off and weighted
 * from 0 to 100%, with what the job expects for the experience, education and seniority factors. */
export function ExtraFactors({ projectId }: { projectId: string }) {
  const base = `/api/company/projects/${projectId}/factors/`;
  const [loaded, setLoaded] = useState<Factors | null>(null);
  const [settings, setSettings] = useState<Record<string, Setting>>({});
  const [years, setYears] = useState("");
  const [education, setEducation] = useState("");
  const [seniority, setSeniority] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [saved, setSaved] = useState(false);

  function show(data: Factors) {
    setLoaded(data);
    setSettings(data.factors);
    setYears(data.required_years === null ? "" : String(data.required_years));
    setEducation(data.required_education ?? "");
    setSeniority(data.seniority ?? "");
  }
  useEffect(() => {
    void getJson<Factors>(base).then((result) => {
      if (result.ok) show(result.data);
      else setError(result.error);
    });
  }, [base]);

  const change = (name: string, changes: Partial<Setting>) =>
    setSettings((current) => ({ ...current, [name]: { ...current[name], ...changes } }));

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const result = await putJson<Factors>(base, {
      required_years: years.trim() === "" ? null : toNumber(years),
      required_education: education === "" ? null : education,
      seniority: seniority === "" ? null : seniority,
      factors: Object.fromEntries(
        Object.entries(settings).map(([name, setting]) => [
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
  return (
    <form className="page-form" onSubmit={save} noValidate>
      <Input
        label="Years of experience needed"
        type="number"
        value={years}
        onChange={(event) => setYears(event.target.value)}
        error={fields.required_years}
      />
      <Select
        label="Education needed"
        options={EDUCATION}
        value={education}
        onChange={(event) => setEducation(event.target.value)}
        error={fields.required_education}
      />
      <Select
        label="Seniority needed"
        options={SENIORITY}
        value={seniority}
        onChange={(event) => setSeniority(event.target.value)}
        error={fields.seniority}
      />
      {FACTORS.map(({ name, label }) => (
        <div key={name} className="page-form">
          <Checkbox
            label={label}
            checked={settings[name]?.enabled ?? false}
            onChange={(event) => change(name, { enabled: event.target.checked })}
          />
          <Input
            label={`${label} weight (%)`}
            type="number"
            value={String(settings[name]?.weight ?? "")}
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
        <Button type="submit">Save scoring factors</Button>
      </div>
      <Dialog open={saved} onOpenChange={setSaved} title="Scoring factors saved" />
    </form>
  );
}
