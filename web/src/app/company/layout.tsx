import type { ReactNode } from "react";

import { CompanyFrame } from "@/components/company/CompanyFrame";
import { SessionEndedWarning } from "@/components/panel/SessionEndedWarning";

import { PLACEHOLDER_SESSION } from "./placeholder-session";

export default function CompanyLayout({ children }: { children: ReactNode }) {
  return (
    <CompanyFrame {...PLACEHOLDER_SESSION}>
      {children}
      <SessionEndedWarning />
    </CompanyFrame>
  );
}
