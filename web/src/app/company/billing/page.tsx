import { Suspense } from "react";

import { PlanCheckout } from "@/components/company/PlanCheckout";
import { Button } from "@/components/ui";

export default function BillingPage() {
  return (
    <div className="page-stack">
      <Suspense>
        <PlanCheckout />
      </Suspense>
      <div className="page-actions">
        <Button variant="secondary">Manage billing</Button>
      </div>
    </div>
  );
}
