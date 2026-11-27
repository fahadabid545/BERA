import { Suspense } from "react";

import { SupportPage } from "@/components/company/support/SupportPage";

export default function SupportRoute() {
  return (
    <Suspense>
      <SupportPage />
    </Suspense>
  );
}
