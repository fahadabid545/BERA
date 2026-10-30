import type { AdminRole } from "@/components/admin/navigation";

// Fixed fake values until the sign-in tickets provide the real signed-in admin.
export const PLACEHOLDER_ADMIN_SESSION: { userName: string; role: AdminRole } = {
  userName: "Fake Admin",
  role: "super",
};
