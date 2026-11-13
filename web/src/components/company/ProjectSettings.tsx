"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { RenewalPrompt, UpgradePrompt } from "@/components/company/BillingPrompt";
import { PROJECTS_HREF } from "@/components/company/links";
import { Button, Dialog, Input, Textarea } from "@/components/ui";
import { deleteJson, getJson, patchJson, postJson, type ApiError } from "@/lib/api";

type Project = {
  id: string;
  title: string;
  job_description: string;
  status: "active" | "archived";
  may_delete: boolean;
};

/** Edit, archive, restore and delete one project. An archived project is read-only. */
export function ProjectSettings({ projectId }: { projectId: string }) {
  const router = useRouter();
  const base = `/api/company/projects/${projectId}/`;
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<ApiError | null>(null);
  const [prompt, setPrompt] = useState<"upgrade" | "renewal" | null>(null);

  const load = useCallback(async () => {
    const result = await getJson<Project>(base);
    if (result.ok) setProject(result.data);
    else setError(result.error);
  }, [base]);
  useEffect(() => {
    void load();
  }, [load]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    setFieldErrors({});
    const result = await patchJson<Project>(base, {
      title: String(form.get("title") ?? ""),
      job_description: String(form.get("job_description") ?? ""),
    });
    if (!result.ok) {
      setFieldErrors(result.error.fields ?? {});
      if (!result.error.fields) setError(result.error);
      return;
    }
    setProject(result.data);
    setSaved(true);
  }

  async function change(action: "archive" | "restore") {
    setError(null);
    const result = await postJson<Project>(`${base}${action}/`, {});
    if (result.ok) return setProject(result.data);
    const promptKind = result.error.details?.prompt;
    if (promptKind === "upgrade" || promptKind === "renewal") return setPrompt(promptKind);
    setError(result.error);
  }

  async function remove(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const typed = String(new FormData(event.currentTarget).get("confirm_title") ?? "");
    setDeleteError(null);
    const result = await deleteJson(base, { confirm_title: typed });
    if (!result.ok) return setDeleteError(result.error);
    router.push(PROJECTS_HREF);
  }

  if (!project) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const archived = project.status === "archived";
  const deleteFields = deleteError?.fields ?? {};
  return (
    <div className="page-stack">
      <form className="page-form" onSubmit={save} noValidate key={project.id + project.title}>
        <Input
          label="Project title"
          name="title"
          defaultValue={project.title}
          readOnly={archived}
          error={fieldErrors.title}
        />
        <Textarea
          label="Job description"
          name="job_description"
          rows={12}
          defaultValue={project.job_description}
          readOnly={archived}
          error={fieldErrors.job_description}
        />
        {error && (
          <p className="ui-error" role="alert">
            {error.message}
          </p>
        )}
        <div className="page-actions">
          {!archived && <Button type="submit">Save</Button>}
          {archived ? (
            <Dialog
              trigger={<Button variant="secondary">Restore project</Button>}
              title="Restore project"
              confirmLabel="Restore"
              onConfirm={() => change("restore")}
            />
          ) : (
            <Dialog
              trigger={<Button variant="secondary">Archive project</Button>}
              title="Archive project"
              confirmLabel="Archive"
              onConfirm={() => change("archive")}
            />
          )}
          {project.may_delete && (
            <Button
              variant="danger"
              onClick={() => {
                setDeleteError(null);
                setDeleting(true);
              }}
            >
              Delete project
            </Button>
          )}
        </div>
      </form>
      <Dialog open={saved} onOpenChange={setSaved} title="Project saved" />
      <Dialog open={deleting} onOpenChange={setDeleting} title="Delete project">
        <form className="page-form" onSubmit={remove} noValidate>
          <Input
            label={`Type "${project.title}" to confirm`}
            name="confirm_title"
            autoComplete="off"
            error={deleteFields.confirm_title}
          />
          {deleteError && !deleteError.fields && (
            <p className="ui-error" role="alert">
              {deleteError.message}
            </p>
          )}
          <div className="page-actions">
            <Button type="submit" variant="danger">
              Delete project
            </Button>
          </div>
        </form>
      </Dialog>
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
