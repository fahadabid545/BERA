"use client";

import { useState } from "react";

import { RenewalPrompt, UpgradePrompt } from "@/components/company/BillingPrompt";
import { Button, Table, Tag } from "@/components/ui";
import { postJson, type ApiError } from "@/lib/api";

type Suggestion = {
  requirements: { kind: "must" | "nice"; text: string }[];
  warnings: { code: string; message: string }[];
  fallback: boolean;
  message: string;
};

/** Asks the AI to propose requirements. Nothing is saved: the editor, where the person edits
 * and confirms them, comes with the Requirement editor ticket. */
export function RequirementSuggestions({ projectId }: { projectId: string }) {
  const [asking, setAsking] = useState(false);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [prompt, setPrompt] = useState<"upgrade" | "renewal" | null>(null);

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
    if (promptKind === "upgrade" || promptKind === "renewal") return setPrompt(promptKind);
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
      <UpgradePrompt
        open={prompt === "upgrade"}
        onOpenChange={(open) => !open && setPrompt(null)}
      />
      <RenewalPrompt
        open={prompt === "renewal"}
        onOpenChange={(open) => !open && setPrompt(null)}
      />
    </div>
  );
}
