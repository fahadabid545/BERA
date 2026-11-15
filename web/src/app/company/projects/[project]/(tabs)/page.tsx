import { ProjectCharts } from "@/components/charts/ProjectCharts";
import { CvProcessing } from "@/components/company/CvProcessing";
import { CvUpload } from "@/components/company/CvUpload";

export default async function ProjectOverviewPage({
  params,
}: {
  params: Promise<{ project: string }>;
}) {
  const { project } = await params;
  return (
    <div className="page-stack">
      <ProjectCharts projectId={project} />
      <CvUpload projectId={project} />
      <CvProcessing projectId={project} />
    </div>
  );
}
