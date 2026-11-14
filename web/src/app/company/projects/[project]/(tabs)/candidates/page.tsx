import { Suspense } from "react";

import { CandidateBrowser } from "@/components/company/CandidateBrowser";

export default async function ProjectCandidatesPage({
  params,
}: {
  params: Promise<{ project: string }>;
}) {
  const { project } = await params;
  return (
    // useSearchParams needs a boundary so the page can still be built ahead of time.
    <Suspense>
      <CandidateBrowser projectId={project} />
    </Suspense>
  );
}
