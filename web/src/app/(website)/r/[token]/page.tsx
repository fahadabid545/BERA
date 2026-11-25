import { SharedReportView } from "@/components/company/SharedReportView";
import { tokenLinkPage } from "@/lib/seo";

// A shared report is for the people it was sent to, never for search engines.
export const metadata = tokenLinkPage;

export default async function SharedReportPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <SharedReportView token={token} />;
}
