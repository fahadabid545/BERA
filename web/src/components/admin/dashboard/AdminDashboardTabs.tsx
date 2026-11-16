"use client";

import { useTabParam } from "@/lib/useTabParam";

import { ADMIN_SECTIONS, AdminDashboard } from "./AdminDashboard";

/** The admin overview with its chosen tab kept in the address (`?tab=`). */
export function AdminDashboardTabs() {
  const [tab, chooseTab] = useTabParam(ADMIN_SECTIONS);
  return <AdminDashboard tab={tab} onTab={chooseTab} />;
}
