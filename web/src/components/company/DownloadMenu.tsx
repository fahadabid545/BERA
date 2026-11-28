"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, Dialog } from "@/components/ui";
import type { ApiError } from "@/lib/api";

import type { Filters } from "./CandidateFilters";
import { packagePage, requestPackage } from "./downloads";

/** The Download button of the Candidates tab: every CV as one zip, or the ranked list (with the
 * filters on screen) as a spreadsheet or a PDF. */
export function DownloadMenu({ projectId, filters }: { projectId: string; filters: Filters }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const listLink = (format: "xlsx" | "pdf") =>
    `/api/company/projects/${projectId}/candidates/export/?${new URLSearchParams({ ...filters, as: format })}`;

  async function allCvs() {
    const result = await requestPackage(projectId, { all: true });
    if (result.ok) router.push(packagePage(result.data.id));
    else setError(result.error);
  }

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        trigger={<Button variant="secondary">Download</Button>}
        title="Download"
      >
        <div className="export-choices">
          <Button onClick={() => void allCvs()}>All CVs as zip</Button>
          <a className="ui-button ui-button--secondary" href={listLink("xlsx")} download>
            Ranked list as spreadsheet
          </a>
          <a className="ui-button ui-button--secondary" href={listLink("pdf")} download>
            Ranked list as PDF
          </a>
          <a
            className="ui-button ui-button--secondary"
            href={`/api/company/projects/${projectId}/export/`}
            download
          >
            Whole project as spreadsheet
          </a>
        </div>
        {error && (
          <p className="ui-error" role="alert">
            {error.message}
          </p>
        )}
      </Dialog>
    </>
  );
}
