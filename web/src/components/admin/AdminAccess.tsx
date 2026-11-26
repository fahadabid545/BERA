"use client";

import { Tabs } from "@/components/ui";

import { BetaSection } from "./access/BetaSection";
import { PaidSection } from "./access/PaidSection";
import { PermittedSection } from "./access/PermittedSection";

/** Who has access without or besides a plan: beta users, admin-permitted users, and (read-only,
 * with their own company pages) the companies that pay. The three are managed apart. */
export function AdminAccess() {
  return (
    <Tabs
      label="Access"
      tabs={[
        { value: "beta", label: "Beta users", content: <BetaSection /> },
        { value: "permitted", label: "Admin-permitted users", content: <PermittedSection /> },
        { value: "paid", label: "Paid users", content: <PaidSection /> },
      ]}
    />
  );
}
