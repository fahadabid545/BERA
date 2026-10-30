import { visibleItems, type NavigationItem } from "@/components/panel/navigation";

export type CompanyRole = "owner" | "member";

const EVERYONE: readonly CompanyRole[] = ["owner", "member"];
const OWNER_ONLY: readonly CompanyRole[] = ["owner"];

export const NAVIGATION: readonly NavigationItem<CompanyRole>[] = [
  { label: "Dashboard", href: "/company", icon: "dashboard", roles: EVERYONE, exact: true },
  { label: "Projects", href: "/company/projects", icon: "projects", roles: EVERYONE },
  { label: "Team", href: "/company/team", icon: "team", roles: OWNER_ONLY },
  { label: "Usage and Billing", href: "/company/billing", icon: "billing", roles: OWNER_ONLY },
  {
    label: "Settings",
    href: "/company/settings",
    icon: "settings",
    roles: OWNER_ONLY,
    children: [
      { label: "Profile", href: "/company/settings/profile" },
      { label: "Company", href: "/company/settings/company" },
      { label: "Retention", href: "/company/settings/retention" },
      { label: "Defaults", href: "/company/settings/defaults" },
    ],
  },
];

export const NEW_PROJECT_HREF = "/company/projects/new";
export const PROFILE_HREF = "/company/settings/profile";
// The sign-in tickets decide what Log out really does.
export const LOG_OUT_HREF = "/login";

export const visibleNavigation = (role: CompanyRole) => visibleItems(NAVIGATION, role);
