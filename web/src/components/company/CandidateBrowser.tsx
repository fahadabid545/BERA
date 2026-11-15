"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button, TextLink } from "@/components/ui";

import {
  CandidateFilters,
  FILTER_KEYS,
  type Filters,
  type RequirementChoice,
} from "./CandidateFilters";
import { CandidateList } from "./CandidateList";
import { SharedReports } from "./SharedReports";

/** The Candidates tab: the buttons and the ranked list. The filters live in the address, so a
 * link or a return visit shows the same result. */
export function CandidateBrowser({ projectId }: { projectId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [requirements, setRequirements] = useState<RequirementChoice[]>([]);

  const filters: Filters = {};
  for (const key of FILTER_KEYS) {
    const value = searchParams.get(key);
    if (value) filters[key] = value;
  }

  function change(next: Filters) {
    const query = new URLSearchParams(next).toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  const compareBase = `/company/projects/${projectId}/compare`;
  const matrixQuery = new URLSearchParams(filters).toString();
  return (
    <div className="page-stack">
      <div className="page-actions">
        <CandidateFilters
          filters={filters}
          requirements={requirements}
          onApply={change}
          onClearAll={() => change({})}
        />
        <TextLink href={matrixQuery ? `${compareBase}?${matrixQuery}` : compareBase}>
          Matrix
        </TextLink>
        <SharedReports projectId={projectId} />
        <Button>Upload CVs</Button>
        <Button variant="secondary">Download all</Button>
      </div>
      <CandidateList
        projectId={projectId}
        filters={filters}
        onClearAll={() => change({})}
        onRequirements={setRequirements}
        onCompare={(ids) => router.push(`${compareBase}?ids=${ids.join(",")}`)}
      />
    </div>
  );
}
