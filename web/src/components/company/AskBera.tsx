"use client";

import { Fragment, useState, type FormEvent } from "react";

import { Button, Card, Input, TextLink } from "@/components/ui";
import { postJson, type ApiError } from "@/lib/api";

type Mentioned = { reference: string; candidate_id: string; initials: string };
type Answer = { answer: string; refused: boolean; candidates: Mentioned[] };

const REFERENCE = /\[(C\d+)\]/g;

/** The answer as text, with each candidate it names shown by initials and linked to the
 * candidate's page. The answer is kept only on this screen: nothing is stored or reloaded. */
function AnswerText({ projectId, result }: { projectId: string; result: Answer }) {
  const byReference = new Map(result.candidates.map((item) => [item.reference, item]));
  const parts = result.answer.split(REFERENCE);
  return (
    <p>
      {parts.map((part, index) => {
        const mentioned = index % 2 === 1 ? byReference.get(part) : undefined;
        return (
          <Fragment key={index}>
            {mentioned ? (
              <TextLink
                href={`/company/projects/${projectId}/candidates/${mentioned.candidate_id}`}
              >
                {mentioned.initials}
              </TextLink>
            ) : index % 2 === 1 ? null : (
              part
            )}
          </Fragment>
        );
      })}
    </p>
  );
}

/** The prompt bar of the Candidates tab: one question about this project's candidates. */
export function AskBera({ projectId }: { projectId: string }) {
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [result, setResult] = useState<Answer | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || asking) return;
    setAsking(true);
    setError(null);
    const reply = await postJson<Answer>(`/api/company/projects/${projectId}/ask/`, { question });
    setAsking(false);
    if (reply.ok) setResult(reply.data);
    else {
      setResult(null);
      setError(reply.error);
    }
  }

  return (
    <div className="page-stack">
      <form className="ask-bar" onSubmit={(event) => void submit(event)}>
        <Input
          label="Question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          error={error?.fields?.question}
        />
        <Button type="submit" disabled={asking || !question.trim()}>
          {asking ? "Asking" : "Ask"}
        </Button>
      </form>
      {error && !error.fields?.question && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      {result && (
        <Card aria-live="polite">
          <AnswerText projectId={projectId} result={result} />
        </Card>
      )}
    </div>
  );
}
