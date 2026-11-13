import { ProjectSettings } from "@/components/company/ProjectSettings";
import { ScoringSettings } from "@/components/company/ScoringSettings";

export default async function ProjectSettingsPage({
  params,
}: {
  params: Promise<{ project: string }>;
}) {
  const { project } = await params;
  return (
    <div className="page-stack">
      <ProjectSettings projectId={project} />
      <ScoringSettings projectId={project} />
    </div>
  );
}
