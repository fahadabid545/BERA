import { blockedHrefs, visibleItems, type NavigationItem } from "@/components/panel/navigation";

// Support sees the Dashboard, Companies and Operations (Jobs, Announcements, Data requests).
// Everything else is for super admins, and typing its address shows support "no access".
export type AdminRole = "super" | "support";

const ALL_ADMINS: readonly AdminRole[] = ["super", "support"];
const SUPER_ONLY: readonly AdminRole[] = ["super"];

export const ADMIN_NAVIGATION: readonly NavigationItem<AdminRole>[] = [
  { label: "Dashboard", href: "/admin", icon: "dashboard", roles: ALL_ADMINS, exact: true },
  { label: "Companies", href: "/admin/companies", icon: "companies", roles: ALL_ADMINS },
  {
    label: "Plans and Pricing",
    href: "/admin/plans",
    icon: "pricing",
    roles: SUPER_ONLY,
    guarded: true,
  },
  {
    label: "AI",
    href: "/admin/ai",
    icon: "ai",
    roles: SUPER_ONLY,
    guarded: true,
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
      { label: "Payments", href: "/admin/operations/payments", roles: SUPER_ONLY },
      { label: "Announcements", href: "/admin/operations/announcements" },
      { label: "Data requests", href: "/admin/operations/data-requests" },
    ],
  },
  {
    label: "Settings",
    href: "/admin/settings",
    icon: "settings",
    roles: SUPER_ONLY,
    guarded: true,
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

export const visibleAdminNavigation = (role: AdminRole) => visibleItems(ADMIN_NAVIGATION, role);
export const blockedAdminHrefs = (role: AdminRole) => blockedHrefs(ADMIN_NAVIGATION, role);
