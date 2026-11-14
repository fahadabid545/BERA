import { CandidateDetail } from "@/components/company/CandidateDetail";

export default async function CandidatePage({
  params,
}: {
  params: Promise<{ project: string; candidate: string }>;
}) {
  const { project, candidate } = await params;
  return <CandidateDetail projectId={project} candidateId={candidate} />;
}
