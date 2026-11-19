"use client";

import { useState } from "react";

import { BillingPrompts, isPromptKind, type PromptKind } from "@/components/company/BillingPrompt";
import { Button, Table, Tag } from "@/components/ui";
import { postJson, type ApiError } from "@/lib/api";

export type SuggestedRequirement = { kind: "must" | "nice"; text: string };

type Suggestion = {
  requirements: SuggestedRequirement[];
  warnings: { code: string; message: string }[];
  fallback: boolean;
  message: string;
};

/** Asks the AI to propose requirements. Nothing is saved: "Add to requirements" puts them in
 * the editor, where the person edits and confirms them. */
export function RequirementSuggestions({
  projectId,
  onUse,
}: {
  projectId: string;
  onUse?: (requirements: SuggestedRequirement[]) => void;
}) {
  const [asking, setAsking] = useState(false);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [prompt, setPrompt] = useState<PromptKind | null>(null);

  async function ask() {
    setAsking(true);
    setError(null);
    const result = await postJson<Suggestion>(
      `/api/company/projects/${projectId}/requirements/suggest/`,
      {},
    );
    setAsking(false);
    if (result.ok) return setSuggestion(result.data);
    const promptKind = result.error.details?.prompt;
    if (isPromptKind(promptKind)) return setPrompt(promptKind);
    setError(result.error);
  }

  return (
    <div className="page-stack">
      <div className="page-actions">
        <Button variant="secondary" onClick={ask} disabled={asking}>
          Suggest requirements
        </Button>
      </div>
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      {suggestion?.fallback && <p role="status">{suggestion.message}</p>}
      {suggestion?.warnings.map((warning) => (
        <p key={warning.code} role="status">
          {warning.message}
        </p>
      ))}
      {suggestion && suggestion.requirements.length > 0 && (
        <Table label="Suggested requirements">
          <thead>
            <tr>
              <th scope="col">Type</th>
              <th scope="col">Requirement</th>
            </tr>
          </thead>
          <tbody>
            {suggestion.requirements.map((requirement) => (
              <tr key={`${requirement.kind}-${requirement.text}`}>
                <td>
                  <Tag variant={requirement.kind === "must" ? "success" : "neutral"}>
                    {requirement.kind === "must" ? "Must have" : "Nice to have"}
                  </Tag>
                </td>
                <td>{requirement.text}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {onUse && suggestion && suggestion.requirements.length > 0 && (
        <div className="page-actions">
          <Button
            onClick={() => {
              onUse(suggestion.requirements);
              setSuggestion(null);
            }}
          >
            Add to requirements
          </Button>
        </div>
      )}
      <BillingPrompts kind={prompt} onClose={() => setPrompt(null)} />
    </div>
  );
}
