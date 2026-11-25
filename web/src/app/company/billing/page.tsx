import { Suspense } from "react";

import { PlanCheckout } from "@/components/company/PlanCheckout";

export default function BillingPage() {
  return (
    <div className="page-stack">
      <Suspense>
        <PlanCheckout />
      </Suspense>
    </div>
  );
}
