"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Tabs } from "@/components/ui";

export const DASHBOARD_TABS = [
  { value: "overview", label: "Overview" },
  { value: "projects", label: "Projects" },
  { value: "candidates", label: "Candidates" },
  { value: "usage", label: "Usage" },
  { value: "activity", label: "Activity" },
] as const;

const TAB_PARAMETER = "tab";

export function DashboardTabs() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const requestedTab = searchParams.get(TAB_PARAMETER);
  const activeTab =
    DASHBOARD_TABS.find((tab) => tab.value === requestedTab)?.value ?? DASHBOARD_TABS[0].value;

  return (
    <Tabs
      label="Dashboard"
      value={activeTab}
      onValueChange={(tab) =>
        router.replace(`${pathname}?${TAB_PARAMETER}=${tab}`, { scroll: false })
      }
      tabs={DASHBOARD_TABS.map((tab) => ({ ...tab, content: null }))}
    />
  );
}
