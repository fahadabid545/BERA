import { RequirementSuggestions } from "@/components/company/RequirementSuggestions";
import { Button } from "@/components/ui";

export default async function ProjectRequirementsPage({
  params,
}: {
  params: Promise<{ project: string }>;
}) {
  const { project } = await params;
  return (
    <div className="page-stack">
      <div className="page-actions">
        <Button variant="secondary">Add requirement</Button>
        <Button>Save</Button>
      </div>
      <RequirementSuggestions projectId={project} />
    </div>
  );
}
