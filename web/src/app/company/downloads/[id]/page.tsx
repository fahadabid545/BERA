import { DownloadPackageView } from "@/components/company/DownloadPackageView";

export default async function DownloadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <DownloadPackageView packageId={id} />;
}
