import { Suspense } from "react";

import { CheckoutReturn } from "@/components/company/CheckoutReturn";

export default function CheckoutReturnPage() {
  return (
    // useSearchParams needs a boundary so the page can still be built ahead of time.
    <Suspense>
      <CheckoutReturn />
    </Suspense>
  );
}
