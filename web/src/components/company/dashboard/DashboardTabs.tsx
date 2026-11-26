"use client";

import { useTabParam } from "@/lib/useTabParam";

import { CompanyDashboard } from "./CompanyDashboard";

export const DASHBOARD_TABS = [
  { value: "overview", label: "Overview" },
  { value: "projects", label: "Projects" },
  { value: "candidates", label: "Candidates" },
  { value: "usage", label: "Usage" },
] as const;

const TAB_VALUES = DASHBOARD_TABS.map((tab) => tab.value);

/** The dashboard with its chosen tab kept in the address (`?tab=`). */
export function DashboardTabs() {
  const [tab, chooseTab] = useTabParam(TAB_VALUES);
  return <CompanyDashboard tab={tab} onTab={chooseTab} />;
}
