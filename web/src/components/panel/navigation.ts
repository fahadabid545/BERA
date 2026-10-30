import type { ToggleIconName } from "@/components/ui";

export type NavigationItem<Role extends string> = {
  label: string;
  href: string;
  icon: ToggleIconName;
  /** Roles that may open this item; everyone else never sees it. */
  roles: readonly Role[];
  /** The Dashboard is only current on its own address, not on every page below it. */
  exact?: boolean;
  /** Draws a divider above the item, to set rarely used areas apart from the daily ones. */
  separated?: boolean;
  /** A user who may not open it and types its address sees the "no access" page. */
  guarded?: boolean;
  children?: readonly { label: string; href: string }[];
};

/** What the sidebar draws: an item that has already been filtered for the user's role. */
export type SidebarItem = Omit<NavigationItem<string>, "roles" | "guarded">;

export function visibleItems<Role extends string>(
  items: readonly NavigationItem<Role>[],
  role: Role,
): SidebarItem[] {
  return items
    .filter((item) => item.roles.includes(role))
    .map(({ roles: _roles, guarded: _guarded, ...item }) => item);
}

/** Addresses this role must see the "no access" page for, even if it types them in. */
export function blockedHrefs<Role extends string>(
  items: readonly NavigationItem<Role>[],
  role: Role,
): string[] {
  return items
    .filter((item) => item.guarded && !item.roles.includes(role))
    .map((item) => item.href);
}

export function isCurrentPath(pathname: string, href: string, exact = false): boolean {
  return pathname === href || (!exact && pathname.startsWith(`${href}/`));
}
