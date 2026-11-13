import { ProjectSettings } from "@/components/company/ProjectSettings";

export default async function ProjectSettingsPage({
  params,
}: {
  params: Promise<{ project: string }>;
}) {
  const { project } = await params;
  return <ProjectSettings projectId={project} />;
}
