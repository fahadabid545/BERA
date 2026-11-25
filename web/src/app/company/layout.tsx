import type { ReactNode } from "react";

import { CompanySession } from "@/components/company/CompanySession";
import { SessionEndedWarning } from "@/components/panel/SessionEndedWarning";
import { privatePage } from "@/lib/seo";

export const metadata = privatePage;

export default function CompanyLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <CompanySession>{children}</CompanySession>
      <SessionEndedWarning />
    </>
  );
}
