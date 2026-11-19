import { CompanyDetail } from "@/components/admin/CompanyDetail";

export default async function CompanyDetailPage({
  params,
}: {
  params: Promise<{ company: string }>;
}) {
  const { company } = await params;
  return <CompanyDetail companyId={company} />;
}
