import type { ReactNode } from "react";

import { PanelFrame } from "@/components/panel/PanelFrame";

import { AgentBar } from "./agent/AgentBar";
import { AgentProvider } from "./agent/AgentProvider";
import { CompanyTopBar } from "./CompanyTopBar";
import { blockedCompanyHrefs, visibleNavigation, type CompanyRole } from "./navigation";

/** The shared frame of the logged-in company area. */
export function CompanyFrame({
  companyName,
  userName,
  role,
  children,
}: {
  companyName: string;
  userName: string;
  role: CompanyRole;
  children: ReactNode;
}) {
  return (
    <AgentProvider>
      <PanelFrame
        variant="company"
        navigationLabel="Company"
        homeHref="/company"
        items={visibleNavigation(role)}
        blockedHrefs={blockedCompanyHrefs(role)}
        topBar={<CompanyTopBar companyName={companyName} userName={userName} role={role} />}
        belowTopBar={<AgentBar />}
      >
        {children}
      </PanelFrame>
    </AgentProvider>
  );
}
