"use client";

import { useEffect, useState, type FormEvent } from "react";

import {
  Button,
  Dialog,
  Input,
  Select,
  Table,
  Tag,
  Textarea,
  type TagVariant,
} from "@/components/ui";
import { getJson, postForm, putJson, type ApiError } from "@/lib/api";

type Budget = { month: string; limit: string; spent: string; remaining: string; used_up: boolean };
type Options = {
  models: string[];
  prompts: Record<"reading" | "scoring", { number: number; current: boolean }[]>;
  budget: Budget;
};
type Profile = {
  skills: string[];
  jobs: { title: string; start: string; end: string }[];
  years_of_experience: number;
  education: { degree: string; institution: string }[];
  certifications: string[];
  languages: string[];
  summary: string;
};
type RequirementResult = {
  kind: "must" | "nice";
  text: string;
  weight: number;
  verdict: "met" | "partly_met" | "missing";
  evidence: string;
  confidence: string;
};
type Score = {
  score: string;
  grade: string;
  must_score: string | null;
  nice_score: string | null;
  capped: boolean;
  label: string;
  borderline: boolean;
};
type StepUsage = { step: string; tokens_in: number; tokens_out: number; cost: string };
type RunResult = {
  profile: Profile;
  requirements: RequirementResult[];
  score: Score;
  usage: { steps: StepUsage[]; tokens_in: number; tokens_out: number; cost: string };
  budget: Budget;
  notice: string;
};

const BASE = "/api/admin/ai/playground/";
const MONEY_DECIMALS = 4;
const WARNING = "Do not use real candidate data.";
const VERDICT_WORDS: Record<RequirementResult["verdict"], { words: string; tag: TagVariant }> = {
  met: { words: "Met", tag: "success" },
  partly_met: { words: "Partly met", tag: "warning" },
  missing: { words: "Missing", tag: "danger" },
};
const KIND_WORDS = { must: "Must-have", nice: "Nice-to-have" };
const LABEL_WORDS: Record<string, string> = {
  strong_match: "Strong match",
  possible: "Possible match",
  not_recommended: "Not recommended",
};
const STEP_WORDS: Record<string, string> = {
  reading: "Reading the CV",
  requirement_extraction: "Finding the requirements",
  scoring: "Judging the requirements",
};

const dollars = (value: string) => `$${Number(value).toFixed(MONEY_DECIMALS)}`;
const versionLabel = (item: { number: number; current: boolean }) =>
  item.current ? `Version ${item.number} (current)` : `Version ${item.number}`;
const currentNumber = (items: { number: number; current: boolean }[]) =>
  String((items.find((item) => item.current) ?? items[0])?.number ?? "");
const listText = (items: string[]) => (items.length ? items.join(", ") : "None");

/** Tries the CV reading and scoring with chosen models and prompt versions. Nothing is saved to
 * any company; test runs are paid from their own monthly budget. */
export function AiPlayground() {
  const [options, setOptions] = useState<Options | null>(null);
  const [budget, setBudget] = useState<Budget | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [jobDescription, setJobDescription] = useState("");
  const [choice, setChoice] = useState({
    reading_model: "",
    scoring_model: "",
    reading_prompt_version: "",
    scoring_prompt_version: "",
  });
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [budgetOpen, setBudgetOpen] = useState(false);
  const [newBudget, setNewBudget] = useState("");
  const [reason, setReason] = useState("");

  useEffect(() => {
    void getJson<Options>(BASE).then((loaded) => {
      if (!loaded.ok) return setError(loaded.error);
      setOptions(loaded.data);
      setBudget(loaded.data.budget);
      setChoice({
        reading_model: loaded.data.models[0] ?? "",
        scoring_model: loaded.data.models[0] ?? "",
        reading_prompt_version: currentNumber(loaded.data.prompts.reading),
        scoring_prompt_version: currentNumber(loaded.data.prompts.scoring),
      });
    });
  }, []);

  async function run(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setRunning(true);
    const form = new FormData();
    if (file) form.append("cv_file", file);
    form.append("job_description", jobDescription);
    for (const [name, value] of Object.entries(choice)) form.append(name, value);
    const reply = await postForm<RunResult>(`${BASE}run/`, form);
    setRunning(false);
    if (reply.ok) {
      setResult(reply.data);
      setBudget(reply.data.budget);
    } else {
      setError(reply.error);
      // A refusal for the budget or a busy run says where the budget stands now.
      const shown = reply.error.details as Budget | undefined;
      if (shown?.limit) setBudget(shown);
    }
  }

  function showBudget() {
    setNewBudget(budget ? String(Number(budget.limit)) : "");
    setReason("");
    setError(null);
    setBudgetOpen(true);
  }

  async function saveBudget() {
    setError(null);
    const reply = await putJson<Budget>(BASE, { monthly_budget: newBudget.trim(), reason });
    if (reply.ok) setBudget(reply.data);
    else setError(reply.error);
  }

  if (!options || !budget) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const fields = error?.fields ?? {};
  const asOptions = (items: { number: number; current: boolean }[]) =>
    items.map((item) => ({ value: String(item.number), label: versionLabel(item) }));
  const modelOptions = options.models.map((name) => ({ value: name, label: name }));
  const choose = (name: keyof typeof choice) => (event: { target: { value: string } }) =>
    setChoice({ ...choice, [name]: event.target.value });

  return (
    <div className="page-stack">
      <p role="note">
        <Tag variant="warning">Warning</Tag> {WARNING}
      </p>
      <Table label="Test budget">
        <thead>
          <tr>
            <th scope="col">Month</th>
            <th scope="col">Budget</th>
            <th scope="col">Spent</th>
            <th scope="col">Remaining</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{budget.month}</td>
            <td>{dollars(budget.limit)}</td>
            <td>{dollars(budget.spent)}</td>
            <td>{dollars(budget.remaining)}</td>
          </tr>
        </tbody>
      </Table>
      <div className="page-actions">
        <Button variant="secondary" onClick={showBudget}>
          Set test budget
        </Button>
      </div>
      <Dialog
        open={budgetOpen}
        onOpenChange={setBudgetOpen}
        title="Monthly test budget"
        confirmLabel="Save budget"
        onConfirm={() => void saveBudget()}
      >
        <Input
          label="Monthly budget (USD)"
          value={newBudget}
          onChange={(event) => setNewBudget(event.target.value)}
        />
        <Input label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
      </Dialog>
      <form className="page-form" onSubmit={(event) => void run(event)}>
        <Input
          label="CV file"
          type="file"
          accept=".pdf,.docx"
          error={fields.cv_file}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <Textarea
          label="Job description"
          rows={12}
          value={jobDescription}
          error={fields.job_description}
          onChange={(event) => setJobDescription(event.target.value)}
        />
        <Select
          label="Reading model"
          options={modelOptions}
          value={choice.reading_model}
          error={fields.reading_model}
          onChange={choose("reading_model")}
        />
        <Select
          label="Reading prompt version"
          options={asOptions(options.prompts.reading)}
          value={choice.reading_prompt_version}
          error={fields.reading_prompt_version}
          onChange={choose("reading_prompt_version")}
        />
        <Select
          label="Scoring model"
          options={modelOptions}
          value={choice.scoring_model}
          error={fields.scoring_model}
          onChange={choose("scoring_model")}
        />
        <Select
          label="Scoring prompt version"
          options={asOptions(options.prompts.scoring)}
          value={choice.scoring_prompt_version}
          error={fields.scoring_prompt_version}
          onChange={choose("scoring_prompt_version")}
        />
        {error && (
          <p className="ui-error" role="alert">
            {error.message}
          </p>
        )}
        <div className="page-actions">
          <Button type="submit" disabled={running || budget.used_up}>
            {running ? "Running" : "Run test"}
          </Button>
        </div>
      </form>
      {result && <Results result={result} />}
    </div>
  );
}

function Results({ result }: { result: RunResult }) {
  const { score, profile, usage } = result;
  return (
    <div className="page-stack">
      {result.notice && <p role="note">{result.notice}</p>}
      <h2>Score</h2>
      <Table label="Score">
        <thead>
          <tr>
            <th scope="col">Score</th>
            <th scope="col">Grade</th>
            <th scope="col">Must-have</th>
            <th scope="col">Nice-to-have</th>
            <th scope="col">Recommendation</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{score.score}</td>
            <td>{score.grade}</td>
            <td>{score.must_score ?? "None"}</td>
            <td>{score.nice_score ?? "None"}</td>
            <td>
              {LABEL_WORDS[score.label] ?? score.label}
              {score.borderline ? ", borderline" : ""}
              {score.capped ? ", capped by a missing must-have" : ""}
            </td>
          </tr>
        </tbody>
      </Table>
      <h2>Requirement results</h2>
      <Table label="Requirement results">
        <thead>
          <tr>
            <th scope="col">Requirement</th>
            <th scope="col">Type</th>
            <th scope="col">Weight</th>
            <th scope="col">Result</th>
            <th scope="col">Evidence</th>
            <th scope="col">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {result.requirements.map((item) => (
            <tr key={item.text}>
              <td>{item.text}</td>
              <td>{KIND_WORDS[item.kind]}</td>
              <td>{item.weight}</td>
              <td>
                <Tag variant={VERDICT_WORDS[item.verdict].tag}>
                  {VERDICT_WORDS[item.verdict].words}
                </Tag>
              </td>
              <td>{item.evidence || "None"}</td>
              <td>{item.confidence}</td>
            </tr>
          ))}
        </tbody>
      </Table>
      <h2>Profile</h2>
      <Table label="Profile">
        <tbody>
          <tr>
            <th scope="row">Skills</th>
            <td>{listText(profile.skills)}</td>
          </tr>
          <tr>
            <th scope="row">Jobs</th>
            <td>
              {profile.jobs.length
                ? profile.jobs.map((job) => `${job.title} (${job.start} to ${job.end})`).join(", ")
                : "None"}
            </td>
          </tr>
          <tr>
            <th scope="row">Years of experience</th>
            <td>{profile.years_of_experience}</td>
          </tr>
          <tr>
            <th scope="row">Education</th>
            <td>
              {profile.education.length
                ? profile.education.map((item) => `${item.degree}, ${item.institution}`).join("; ")
                : "None"}
            </td>
          </tr>
          <tr>
            <th scope="row">Certifications</th>
            <td>{listText(profile.certifications)}</td>
          </tr>
          <tr>
            <th scope="row">Languages</th>
            <td>{listText(profile.languages)}</td>
          </tr>
          <tr>
            <th scope="row">Summary</th>
            <td>{profile.summary}</td>
          </tr>
        </tbody>
      </Table>
      <h2>Tokens and cost</h2>
      <Table label="Tokens and cost">
        <thead>
          <tr>
            <th scope="col">Step</th>
            <th scope="col">Tokens in</th>
            <th scope="col">Tokens out</th>
            <th scope="col">Cost</th>
          </tr>
        </thead>
        <tbody>
          {usage.steps.map((step) => (
            <tr key={step.step}>
              <td>{STEP_WORDS[step.step] ?? step.step}</td>
              <td>{step.tokens_in}</td>
              <td>{step.tokens_out}</td>
              <td>{dollars(step.cost)}</td>
            </tr>
          ))}
          <tr>
            <th scope="row">Total</th>
            <td>{usage.tokens_in}</td>
            <td>{usage.tokens_out}</td>
            <td>{dollars(usage.cost)}</td>
          </tr>
        </tbody>
      </Table>
    </div>
  );
}
