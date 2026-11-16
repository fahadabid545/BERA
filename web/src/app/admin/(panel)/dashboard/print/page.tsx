import { Suspense } from "react";

import { AdminPrintableReport } from "@/components/admin/dashboard/AdminPrintableReport";

export default function AdminPrintableReportPage() {
  return (
    // useSearchParams needs a boundary so the page can still be built ahead of time.
    <Suspense>
      <AdminPrintableReport />
    </Suspense>
  );
}
