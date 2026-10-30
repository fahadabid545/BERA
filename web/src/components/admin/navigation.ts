import { blockedHrefs, visibleItems, type NavigationItem } from "@/components/panel/navigation";

// Only Advanced is limited to super admins so far; the Admin roles ticket decides the rest.
export type AdminRole = "super" | "support";

const ALL_ADMINS: readonly AdminRole[] = ["super", "support"];
const SUPER_ONLY: readonly AdminRole[] = ["super"];

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
      { label: "Audit log", href: "/admin/settings/audit-log" },
      { label: "Admin users", href: "/admin/settings/admins" },
    ],
  },
  {
    // Rarely changed platform settings, kept apart from the daily items.
    label: "Advanced",
    href: "/admin/advanced",
    icon: "advanced",
    roles: SUPER_ONLY,
    separated: true,
    guarded: true,
    children: [
      { label: "Platform values", href: "/admin/advanced/platform-values" },
      { label: "Limits", href: "/admin/advanced/limits" },
      { label: "Rate limiting", href: "/admin/advanced/rate-limits" },
      { label: "Security", href: "/admin/advanced/security" },
      { label: "AI controls", href: "/admin/advanced/ai-controls" },
      { label: "Maintenance", href: "/admin/advanced/maintenance" },
    ],
  },
];

// The sign-in tickets decide what Log out really does.
export const ADMIN_LOG_OUT_HREF = "/login";

export const visibleAdminNavigation = (role: AdminRole) => visibleItems(ADMIN_NAVIGATION, role);
export const blockedAdminHrefs = (role: AdminRole) => blockedHrefs(ADMIN_NAVIGATION, role);
