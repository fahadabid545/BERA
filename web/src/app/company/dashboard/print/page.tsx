import { Suspense } from "react";

import { PrintableReport } from "@/components/company/dashboard/PrintableReport";

export default function PrintableReportPage() {
  return (
    // useSearchParams needs a boundary so the page can still be built ahead of time.
    <Suspense>
      <PrintableReport />
    </Suspense>
  );
}
