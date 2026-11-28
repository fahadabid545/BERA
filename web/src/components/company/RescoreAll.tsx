"use client";

import { useState } from "react";

import { BillingPrompts, isPromptKind, type PromptKind } from "@/components/company/BillingPrompt";
import { Button, Dialog } from "@/components/ui";
import { postJson, type ApiError } from "@/lib/api";

type Estimate = { cvs: number; requirements: number; estimated_cost: string };

/** Scores every CV against every requirement again. The first press only asks the server what it
 * would cost; the person agrees in a popup before anything runs. */
export function RescoreAll({ projectId }: { projectId: string }) {
  const url = `/api/company/projects/${projectId}/rescore/`;
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [prompt, setPrompt] = useState<PromptKind | null>(null);
  const [started, setStarted] = useState(false);

  async function ask() {
    setError(null);
    const result = await postJson<{ queued: number }>(url, {});
    if (result.ok) return setStarted(true);
    if (result.error.code === "rescoring_needed") {
      return setEstimate(result.error.details as unknown as Estimate);
    }
    const promptKind = result.error.details?.prompt;
    if (isPromptKind(promptKind)) return setPrompt(promptKind);
    setError(result.error);
  }

  async function confirm() {
    setEstimate(null);
    const result = await postJson<{ queued: number }>(url, { acknowledge_rescoring: true });
    if (result.ok) setStarted(true);
    else setError(result.error);
  }

  return (
    <div className="page-form">
      <div className="page-actions">
        <Button variant="secondary" onClick={() => void ask()}>
          Score all CVs again
        </Button>
      </div>
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      <Dialog
        open={estimate !== null}
        onOpenChange={(open) => !open && setEstimate(null)}
        title="Score all CVs again"
        description={
          estimate
            ? `${estimate.cvs} CVs will be judged against ${estimate.requirements} requirements again. Estimated cost: ${estimate.estimated_cost}.`
            : undefined
        }
        confirmLabel="Score again"
        onConfirm={() => void confirm()}
      />
      <Dialog open={started} onOpenChange={setStarted} title="Scoring started" />
      <BillingPrompts kind={prompt} onClose={() => setPrompt(null)} />
    </div>
  );
}
