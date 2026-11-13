import { CvUpload } from "@/components/company/CvUpload";

export default async function ProjectOverviewPage({
  params,
}: {
  params: Promise<{ project: string }>;
}) {
  const { project } = await params;
  return <CvUpload projectId={project} />;
}
