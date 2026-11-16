import { Suspense } from "react";

import { AdminDashboardTabs } from "@/components/admin/dashboard/AdminDashboardTabs";

export default function AdminDashboardPage() {
  return (
    // useSearchParams needs a boundary so the page can still be built ahead of time.
    <Suspense>
      <AdminDashboardTabs />
    </Suspense>
  );
}
