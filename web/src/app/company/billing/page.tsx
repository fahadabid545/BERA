import { Suspense } from "react";

import { BillingDetailsForm } from "@/components/company/BillingDetailsForm";
import { InvoiceList } from "@/components/company/InvoiceList";
import { PlanCheckout } from "@/components/company/PlanCheckout";

export default function BillingPage() {
  return (
    <div className="page-stack">
      <BillingDetailsForm />
      <Suspense>
        <PlanCheckout />
      </Suspense>
      <InvoiceList />
    </div>
  );
}
