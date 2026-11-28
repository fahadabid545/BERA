"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button, ButtonLink } from "@/components/ui";
import type { ApiError } from "@/lib/api";

import {
  CandidateFilters,
  FILTER_KEYS,
  type Filters,
  type RequirementChoice,
} from "./CandidateFilters";
import { CandidateList } from "./CandidateList";
import { DownloadMenu } from "./DownloadMenu";
import { packagePage, requestPackage } from "./downloads";
import { SharedReports } from "./SharedReports";

/** The Candidates tab: the buttons and the ranked list. The filters live in the address, so a
 * link or a return visit shows the same result. */
export function CandidateBrowser({ projectId }: { projectId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [requirements, setRequirements] = useState<RequirementChoice[]>([]);
  const [selecting, setSelecting] = useState(false);
  const [hasRows, setHasRows] = useState(false);
  const [downloadError, setDownloadError] = useState<ApiError | null>(null);

  const filters: Filters = {};
  for (const key of FILTER_KEYS) {
    const value = searchParams.get(key);
    if (value) filters[key] = value;
  }

  function change(next: Filters) {
    const query = new URLSearchParams(next).toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  async function downloadSelected(candidates: string[]) {
    const result = await requestPackage(projectId, { candidates });
    if (result.ok) router.push(packagePage(result.data.id));
    else setDownloadError(result.error);
  }

  const compareBase = `/company/projects/${projectId}/compare`;
  return (
    <div className="page-stack">
      <div className="toolbar">
        <CandidateFilters
          filters={filters}
          requirements={requirements}
          onApply={change}
          onClearAll={() => change({})}
        />
        <div className="toolbar__end">
          {hasRows && !selecting && (
            <Button variant="secondary" onClick={() => setSelecting(true)}>
              Select
            </Button>
          )}
          <SharedReports projectId={projectId} />
          <DownloadMenu projectId={projectId} filters={filters} />
          <ButtonLink href={`/company/projects/${projectId}#upload`}>Upload CVs</ButtonLink>
        </div>
      </div>
      <CandidateList
        projectId={projectId}
        filters={filters}
        onClearAll={() => change({})}
        selecting={selecting}
        onSelectingChange={setSelecting}
        onHasRows={setHasRows}
        onRequirements={setRequirements}
        onCompare={(ids) => router.push(`${compareBase}?ids=${ids.join(",")}`)}
        onDownload={(ids) => void downloadSelected(ids)}
      />
      {downloadError && (
        <p className="ui-error" role="alert">
          {downloadError.message}
        </p>
      )}
    </div>
  );
}
