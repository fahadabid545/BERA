"use client";

import { usePlatformInfo } from "@/lib/platformInfo";

/** While maintenance mode is on, every company page says so, in the admins' own words. */
export function MaintenanceNotice() {
  const info = usePlatformInfo();
  if (!info?.maintenance?.enabled) return null;
  return (
    <p className="announcement" role="status">
      {info.maintenance.message}
    </p>
  );
}
