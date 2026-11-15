import type { Metadata } from "next";

import { SharedReportView } from "@/components/company/SharedReportView";

// A shared report is for the people it was sent to, never for search engines.
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default async function SharedReportPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <SharedReportView token={token} />;
}
