"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, Card, Dialog, Select, Table, Tag, Textarea } from "@/components/ui";
import { deleteJson, getJson, patchJson, postJson, type ApiError } from "@/lib/api";

import { STAGES, stageLabel } from "./stages";

type Note = {
  id: string;
  text: string;
  author: string;
  mine: boolean;
  created_at: string;
  updated_at: string;
};
type Verdict = "met" | "partly_met" | "missing";
type Detail = {
  id: string;
  file_name: string;
  status: string;
  failure_reason: string;
  stage: string;
  added_at: string;
  contact: { name: string; email: string; phone: string; address: string };
  score: {
    score: string;
    grade: string;
    capped: boolean;
    outdated: boolean;
    must_score: string | null;
    nice_score: string | null;
    label: "strong_match" | "possible" | "not_recommended";
    borderline: boolean;
    strengths: string[];
    risks: string[];
    interview_questions: string[];
    guide_note: string;
  } | null;
  ats: { score: number; reasons: string[]; rules_version: number } | null;
  requirements: {
    requirement_id: string;
    text: string;
    kind: "must" | "nice";
    weight: number;
    verdict: Verdict | null;
    evidence: string;
    confidence: string | null;
    outdated: boolean;
  }[];
  factors: {
    outdated: boolean;
    values: Record<string, { value: number | null; explanation: string }>;
  } | null;
  history: { from_stage: string; to_stage: string; by: string; at: string }[];
  notes: Note[];
  models: {
    reading: { model: string; prompt_version: number };
    scoring: { model: string; prompt_version: number } | null;
  };
  cv: { file_type: string; can_preview: boolean };
};

const LABELS = {
  strong_match: "Strong match",
  possible: "Possible",
  not_recommended: "Not recommended",
};
const VERDICTS: Record<Verdict, string> = {
  met: "Met",
  partly_met: "Partly met",
  missing: "Missing",
};
const FACTORS: Record<string, string> = {
  experience_years: "Experience years match",
  education: "Education match",
  seniority: "Seniority fit",
  recency: "Recency of relevant work",
  gaps_and_changes: "Career gaps and job changes",
  readability: "CV readability",
  confidence: "Confidence level",
};
const STATUSES: Record<string, string> = {
  awaiting_confirmation: "Awaiting confirmation",
  waiting: "Waiting",
  reading: "Reading",
  scoring: "Scoring",
  done: "Done",
  failed: "Failed",
};
const DATE_LENGTH = 10;

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <Card aria-label={title}>
      <h2>{title}</h2>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </Card>
  );
}

/** Everything about one candidate. Parts that no longer match the project (a reworded
 * requirement, a score waiting to be recalculated) are marked Outdated. */
export function CandidateDetail({
  projectId,
  candidateId,
}: {
  projectId: string;
  candidateId: string;
}) {
  const base = `/api/company/projects/${projectId}/candidates/${candidateId}/`;
  const router = useRouter();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [version, setVersion] = useState(0);
  const [stage, setStage] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [problem, setProblem] = useState<ApiError | null>(null);
  const reload = () => setVersion((current) => current + 1);

  async function deleteCandidate() {
    const result = await deleteJson(base);
    if (result.ok) router.push(`/company/projects/${projectId}`);
    else setProblem(result.error);
  }

  useEffect(() => {
    let stopped = false;
    void getJson<Detail>(base).then((result) => {
      if (stopped) return;
      if (result.ok) {
        setDetail(result.data);
        setStage((current) => current || result.data.stage);
      } else setError(result.error);
    });
    return () => {
      stopped = true;
    };
  }, [base, version]);

  if (error) {
    return (
      <p className="ui-error" role="alert">
        {error.code === "not_found" ? "This candidate no longer exists." : error.message}
      </p>
    );
  }
  if (!detail) return null;

  async function run(request: Promise<{ ok: boolean; error?: ApiError }>, done?: () => void) {
    const result = await request;
    if (result.ok) {
      setProblem(null);
      done?.();
      reload();
    } else setProblem(result.error ?? null);
  }
  const changeStage = () =>
    run(
      postJson(`/api/company/projects/${projectId}/candidates/stage/`, {
        candidate_ids: [candidateId],
        stage,
      }),
    );
  const addNote = () => run(postJson(`${base}notes/`, { text: draft }), () => setDraft(""));
  const saveNote = () =>
    editing &&
    run(patchJson(`${base}notes/${editing.id}/`, { text: editing.text }), () => setEditing(null));

  const { score, ats, contact } = detail;
  const contactLines = [contact.name, contact.email, contact.phone, contact.address].filter(
    Boolean,
  );
  return (
    <div className="page-stack">
      <Card aria-label="Candidate">
        <h1>{detail.file_name}</h1>
        {contactLines.map((line) => (
          <div key={line}>{line}</div>
        ))}
        <div>
          Stage: {stageLabel(detail.stage)}. Added {detail.added_at.slice(0, DATE_LENGTH)}.
        </div>
        <Select
          label="Stage"
          value={stage}
          onChange={(event) => setStage(event.target.value)}
          options={STAGES}
        />
        <Dialog
          open={confirming}
          onOpenChange={setConfirming}
          trigger={
            <Button variant="secondary" disabled={stage === detail.stage}>
              Change stage
            </Button>
          }
          title="Change stage"
          description={`Move this candidate to ${stageLabel(stage)}?`}
          confirmLabel="Change stage"
          onConfirm={() => void changeStage()}
        />
        <Dialog
          trigger={<Button variant="danger">Delete candidate</Button>}
          title="Delete candidate"
          description="Delete this candidate with their CV, scores and notes? This cannot be undone."
          confirmLabel="Delete candidate"
          destructive
          onConfirm={() => void deleteCandidate()}
        />
        {detail.status !== "done" && (
          <div>
            <Tag variant={detail.status === "failed" ? "danger" : "live"}>
              {STATUSES[detail.status] ?? detail.status}
            </Tag>{" "}
            {detail.failure_reason}
          </div>
        )}
      </Card>

      {score ? (
        <Card aria-label="Score">
          <h2>Score</h2>
          <div>
            {score.score} ({score.grade}) {LABELS[score.label]}{" "}
            {score.borderline && <Tag variant="neutral">Borderline</Tag>}{" "}
            {score.capped && <Tag variant="neutral">Capped</Tag>}{" "}
            {score.outdated && <Tag variant="warning">Outdated</Tag>}
          </div>
          {score.must_score && <div>Must-haves: {score.must_score}</div>}
          {score.nice_score && <div>Nice-to-haves: {score.nice_score}</div>}
          {score.guide_note && <div>{score.guide_note}</div>}
        </Card>
      ) : (
        <Card aria-label="Score">
          <h2>Score</h2>
          <div>Not scored yet.</div>
        </Card>
      )}

      <Card aria-label="ATS score">
        <h2>ATS score</h2>
        <div>{ats ? ats.score : "Not available."}</div>
        {ats && ats.reasons.length > 0 && (
          <ul>
            {ats.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
      </Card>

      {detail.requirements.length > 0 && (
        <Table label="Requirements">
          <thead>
            <tr>
              {["Requirement", "Type", "Weight", "Result", "Evidence", "Confidence"].map((name) => (
                <th key={name} scope="col">
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {detail.requirements.map((item) => (
              <tr key={item.requirement_id}>
                <td>{item.text}</td>
                <td>{item.kind === "must" ? "Must-have" : "Nice-to-have"}</td>
                <td>{item.weight}</td>
                <td>
                  {item.verdict ? VERDICTS[item.verdict] : <Tag variant="warning">Not judged</Tag>}{" "}
                  {item.verdict && item.outdated && <Tag variant="warning">Outdated</Tag>}
                </td>
                <td>{item.evidence}</td>
                <td>{item.confidence}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      {score && (
        <>
          <List title="Strengths" items={score.strengths} />
          <List title="Risks" items={score.risks} />
          <List title="Interview questions" items={score.interview_questions} />
        </>
      )}

      {detail.factors && (
        <Table label="Extra factors">
          <thead>
            <tr>
              <th scope="col">Factor</th>
              <th scope="col">Value</th>
              <th scope="col">Explanation</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(detail.factors.values).map(([name, factor]) => (
              <tr key={name}>
                <td>{FACTORS[name] ?? name}</td>
                <td>
                  {factor.value ?? "Not found"}{" "}
                  {detail.factors?.outdated && <Tag variant="warning">Outdated</Tag>}
                </td>
                <td>{factor.explanation}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      {problem && (
        <p className="ui-error" role="alert">
          {problem.fields ? Object.values(problem.fields).join(" ") : problem.message}
        </p>
      )}

      <Card aria-label="Stage history">
        <h2>Stage history</h2>
        {detail.history.length === 0 ? (
          <div>No changes.</div>
        ) : (
          <ul>
            {detail.history.map((change) => (
              <li key={change.at + change.to_stage}>
                {stageLabel(change.from_stage)} to {stageLabel(change.to_stage)} by {change.by},{" "}
                {change.at.slice(0, DATE_LENGTH)}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card aria-label="Notes">
        <h2>Notes</h2>
        <Textarea
          label="New note"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <Button disabled={!draft.trim()} onClick={() => void addNote()}>
          Add note
        </Button>
        {detail.notes.length === 0 ? (
          <div>No notes.</div>
        ) : (
          <ul>
            {detail.notes.map((note) => (
              <li key={note.id}>
                {editing?.id === note.id ? (
                  <>
                    <Textarea
                      label="Edit note"
                      value={editing.text}
                      onChange={(event) => setEditing({ id: note.id, text: event.target.value })}
                    />
                    <Button onClick={() => void saveNote()}>Save note</Button>
                    <Button variant="secondary" onClick={() => setEditing(null)}>
                      Cancel
                    </Button>
                  </>
                ) : (
                  <>
                    <div>{note.text}</div>
                    <div>
                      {note.author}, {note.created_at.slice(0, DATE_LENGTH)}
                    </div>
                    {note.mine && (
                      <div className="page-actions">
                        <Button
                          variant="secondary"
                          onClick={() => setEditing({ id: note.id, text: note.text })}
                        >
                          Edit note
                        </Button>
                        <Dialog
                          trigger={<Button variant="secondary">Delete note</Button>}
                          title="Delete note"
                          description="Delete this note?"
                          confirmLabel="Delete note"
                          destructive
                          onConfirm={() => void run(deleteJson(`${base}notes/${note.id}/`))}
                        />
                      </div>
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card aria-label="Models">
        <h2>Models</h2>
        <div>
          Reading: {detail.models.reading.model}, prompt version{" "}
          {detail.models.reading.prompt_version}
        </div>
        {detail.models.scoring && (
          <div>
            Scoring: {detail.models.scoring.model}, prompt version{" "}
            {detail.models.scoring.prompt_version}
          </div>
        )}
      </Card>

      <Card aria-label="Original CV">
        <h2>Original CV</h2>
        <div className="page-actions">
          <a className="ui-button ui-button--secondary" href={`${base}cv/?download=1`}>
            Download CV
          </a>
        </div>
        {detail.cv.can_preview && (
          <iframe className="cv-preview" title="CV preview" src={`${base}cv/`} />
        )}
      </Card>
    </div>
  );
}
