import { visibleItems, type NavigationItem } from "@/components/panel/navigation";

// Which items a support admin may open is decided in the Admin roles ticket.
// Until then every item is open to both roles.
export type AdminRole = "admin" | "support";

const ALL_ADMINS: readonly AdminRole[] = ["admin", "support"];

export const ADMIN_NAVIGATION: readonly NavigationItem<AdminRole>[] = [
  { label: "Dashboard", href: "/admin", icon: "dashboard", roles: ALL_ADMINS, exact: true },
  { label: "Companies", href: "/admin/companies", icon: "companies", roles: ALL_ADMINS },
  { label: "Plans and Pricing", href: "/admin/plans", icon: "pricing", roles: ALL_ADMINS },
  {
    label: "AI",
    href: "/admin/ai",
    icon: "ai",
    roles: ALL_ADMINS,
    children: [
      { label: "Playground", href: "/admin/ai/playground" },
      { label: "Models", href: "/admin/ai/models" },
      { label: "Prompts", href: "/admin/ai/prompts" },
    ],
  },
  {
    label: "Operations",
    href: "/admin/operations",
    icon: "operations",
    roles: ALL_ADMINS,
    children: [
      { label: "Jobs", href: "/admin/operations/jobs" },
      { label: "Payments", href: "/admin/operations/payments" },
      { label: "Announcements", href: "/admin/operations/announcements" },
      { label: "Data requests", href: "/admin/operations/data-requests" },
    ],
  },
  {
    label: "Settings",
    href: "/admin/settings",
    icon: "settings",
    roles: ALL_ADMINS,
    children: [
      { label: "General", href: "/admin/settings/general" },
      { label: "Limits", href: "/admin/settings/limits" },
      { label: "Security", href: "/admin/settings/security" },
      { label: "Audit log", href: "/admin/settings/audit-log" },
      { label: "Admin users", href: "/admin/settings/admin-users" },
    ],
  },
];

// The sign-in tickets decide what Log out really does.
export const ADMIN_LOG_OUT_HREF = "/login";

export const visibleAdminNavigation = (role: AdminRole) => visibleItems(ADMIN_NAVIGATION, role);
