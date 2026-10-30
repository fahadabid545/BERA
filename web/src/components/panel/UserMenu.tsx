"use client";

import { Menu, type MenuItem } from "@/components/ui";
import { logOut } from "@/lib/logout";

function initialsOf(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .map((word) => word[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

/** `items` are links; "Log out" is added last and ends this browser's session. */
export function UserMenu({ userName, items }: { userName: string; items: MenuItem[] }) {
  return (
    <Menu
      trigger={
        <button type="button" className="panel-avatar">
          <span aria-hidden="true">{initialsOf(userName)}</span>
          <span className="visually-hidden">User menu</span>
        </button>
      }
      items={[...items, { label: "Log out", onSelect: logOut }]}
    />
  );
}
