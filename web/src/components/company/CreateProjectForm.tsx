"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { RenewalPrompt, UpgradePrompt } from "@/components/company/BillingPrompt";
import { PROJECTS_HREF } from "@/components/company/links";
import { Button, ButtonLink, Dialog, Input, Textarea } from "@/components/ui";
import { postJson, type ApiError } from "@/lib/api";

const CREATE_URL = "/api/company/projects/";

type Warning = { code: string; message: string };
type Draft = { title: string; job_description: string };

function warningsOf(error: ApiError): Warning[] {
  return error.code === "project_warnings"
    ? ((error.details?.warnings as Warning[] | undefined) ?? [])
    : [];
}

/** The create-project form. Warnings are confirmed in a popup; a reached limit opens the
 * Upgrade (or Renewal) popup. */
export function CreateProjectForm() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [warnings, setWarnings] = useState<Warning[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [prompt, setPrompt] = useState<"upgrade" | "renewal" | null>(null);

  async function create(values: Draft, acknowledgeWarnings: boolean) {
    setSaving(true);
    setError(null);
    const result = await postJson(CREATE_URL, {
      ...values,
      acknowledge_warnings: acknowledgeWarnings,
    });
    setSaving(false);
    if (result.ok) return router.push(PROJECTS_HREF);
    const found = warningsOf(result.error);
    if (found.length > 0) {
      setDraft(values);
      return setWarnings(found);
    }
    const promptKind = result.error.details?.prompt;
    if (promptKind === "upgrade" || promptKind === "renewal") return setPrompt(promptKind);
    setError(result.error);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void create(
      {
        title: String(form.get("title") ?? ""),
        job_description: String(form.get("job_description") ?? ""),
      },
      false,
    );
  }

  const fields = error?.fields ?? {};
  const generalError = error && Object.keys(fields).length === 0 ? error.message : null;
  return (
    <form className="page-form" onSubmit={submit} noValidate>
      <Input label="Project title" name="title" error={fields.title} />
      <Textarea
        label="Job description"
        name="job_description"
        rows={12}
        error={fields.job_description}
      />
      {generalError && (
        <p className="ui-error" role="alert">
          {generalError}
        </p>
      )}
      <div className="page-actions">
        <Button type="submit" disabled={saving}>
          Create project
        </Button>
        <ButtonLink href={PROJECTS_HREF} variant="secondary">
          Cancel
        </ButtonLink>
      </div>
      <Dialog
        open={warnings.length > 0}
        onOpenChange={(open) => !open && setWarnings([])}
        title="Check before creating"
        confirmLabel="Create anyway"
        onConfirm={() => {
          setWarnings([]);
          if (draft) void create(draft, true);
        }}
      >
        <ul>
          {warnings.map((warning) => (
            <li key={warning.code}>{warning.message}</li>
          ))}
        </ul>
      </Dialog>
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
