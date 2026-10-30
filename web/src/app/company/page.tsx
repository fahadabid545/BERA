import { Suspense } from "react";

import { DashboardTabs } from "@/components/company/dashboard/DashboardTabs";

export default function CompanyDashboard() {
  return (
    // useSearchParams needs a boundary so the page can still be built ahead of time.
    <Suspense>
      <DashboardTabs />
    </Suspense>
  );
}
