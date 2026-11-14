import { CandidateList } from "@/components/company/CandidateList";
import { Button } from "@/components/ui";

export default async function ProjectCandidatesPage({
  params,
}: {
  params: Promise<{ project: string }>;
}) {
  const { project } = await params;
  return (
    <div className="page-stack">
      <div className="page-actions">
        <Button variant="secondary">Filters</Button>
        <Button>Upload CVs</Button>
        <Button variant="secondary">Download all</Button>
      </div>
      <CandidateList projectId={project} />
    </div>
  );
}
