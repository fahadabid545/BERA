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
  /** For a guarded item some of whose pages everyone may open: only these addresses are
   * refused, instead of the item's own address and everything below it. */
  guardedHrefs?: readonly string[];
  /** A child only some of the item's roles may open; leave out to follow the item. */
  children?: readonly NavigationChild<Role>[];
};

export type NavigationChild<Role extends string> = {
  label: string;
  href: string;
  roles?: readonly Role[];
};

/** What the sidebar draws: an item that has already been filtered for the user's role. */
export type SidebarItem = Omit<
  NavigationItem<string>,
  "roles" | "guarded" | "guardedHrefs" | "children"
> & { children?: readonly { label: string; href: string }[] };

export function visibleItems<Role extends string>(
  items: readonly NavigationItem<Role>[],
  role: Role,
): SidebarItem[] {
  return items
    .filter((item) => item.roles.includes(role))
    .map(
      ({ roles: _roles, guarded: _guarded, guardedHrefs: _guardedHrefs, children, ...item }) => ({
        ...item,
        ...(children && {
          children: children
            .filter((child) => !child.roles || child.roles.includes(role))
            .map(({ label, href }) => ({ label, href })),
        }),
      }),
    );
}

/** Addresses this role must see the "no access" page for, even if it types them in. */
export function blockedHrefs<Role extends string>(
  items: readonly NavigationItem<Role>[],
  role: Role,
): string[] {
  const blockedItems = items
    .filter((item) => item.guarded && !item.roles.includes(role))
    .flatMap((item) => item.guardedHrefs ?? [item.href]);
  // Pages of an item the role may open, which it may not open itself.
  const blockedChildren = items
    .filter((item) => item.roles.includes(role))
    .flatMap((item) => item.children ?? [])
    .filter((child) => child.roles && !child.roles.includes(role))
    .map((child) => child.href);
  return [...blockedItems, ...blockedChildren];
}

export function isCurrentPath(pathname: string, href: string, exact = false): boolean {
  return pathname === href || (!exact && pathname.startsWith(`${href}/`));
}
