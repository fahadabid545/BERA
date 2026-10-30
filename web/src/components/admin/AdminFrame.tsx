import type { ReactNode } from "react";

import { PanelFrame } from "@/components/panel/PanelFrame";

import { AdminTopBar } from "./AdminTopBar";
import { blockedAdminHrefs, visibleAdminNavigation, type AdminRole } from "./navigation";

/** The shared frame of the admin area. It looks different from the company panel on purpose. */
export function AdminFrame({
  userName,
  role,
  children,
}: {
  userName: string;
  role: AdminRole;
  children: ReactNode;
}) {
  return (
    <PanelFrame
      variant="admin"
      navigationLabel="Admin"
      homeHref="/admin"
      items={visibleAdminNavigation(role)}
      blockedHrefs={blockedAdminHrefs(role)}
      topBar={<AdminTopBar userName={userName} />}
    >
      {children}
    </PanelFrame>
  );
}
