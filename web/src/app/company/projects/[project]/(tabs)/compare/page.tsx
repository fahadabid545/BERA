import { Suspense } from "react";

import { CandidateComparison } from "@/components/company/CandidateComparison";

export default async function ProjectComparePage({
  params,
}: {
  params: Promise<{ project: string }>;
}) {
  const { project } = await params;
  return (
    // useSearchParams needs a boundary so the page can still be built ahead of time.
    <Suspense>
      <CandidateComparison projectId={project} />
    </Suspense>
  );
}
