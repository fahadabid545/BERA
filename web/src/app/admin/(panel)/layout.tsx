import type { ReactNode } from "react";

import { AdminFrame } from "@/components/admin/AdminFrame";

import { PLACEHOLDER_ADMIN_SESSION } from "./placeholder-session";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return <AdminFrame {...PLACEHOLDER_ADMIN_SESSION}>{children}</AdminFrame>;
}
