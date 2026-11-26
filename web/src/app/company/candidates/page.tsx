import { Suspense } from "react";

import { CompanyCandidates } from "@/components/company/CompanyCandidates";

export default function CandidatesPage() {
  return (
    <Suspense>
      <CompanyCandidates />
    </Suspense>
  );
}
