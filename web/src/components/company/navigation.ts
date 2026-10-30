import type { ToggleIconName } from "@/components/ui";

export type CompanyRole = "owner" | "member";

export type NavigationItem = {
  label: string;
  href: string;
  icon: ToggleIconName;
  /** Roles that may open this item; everyone else never sees it. */
  roles: readonly CompanyRole[];
  /** The Dashboard is only current on its own address, not on every page below it. */
  exact?: boolean;
  children?: readonly { label: string; href: string }[];
};

const EVERYONE: readonly CompanyRole[] = ["owner", "member"];
const OWNER_ONLY: readonly CompanyRole[] = ["owner"];

export const NAVIGATION: readonly NavigationItem[] = [
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

export function visibleNavigation(role: CompanyRole): NavigationItem[] {
  return NAVIGATION.filter((item) => item.roles.includes(role));
}

export function isCurrentPath(pathname: string, href: string, exact = false): boolean {
  return pathname === href || (!exact && pathname.startsWith(`${href}/`));
}
