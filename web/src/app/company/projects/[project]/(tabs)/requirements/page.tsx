import { RequirementEditor } from "@/components/company/RequirementEditor";

export default async function ProjectRequirementsPage({
  params,
}: {
  params: Promise<{ project: string }>;
}) {
  const { project } = await params;
  return <RequirementEditor projectId={project} />;
}
