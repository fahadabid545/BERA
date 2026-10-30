"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export type TabLinkItem = { label: string; href: string; exact?: boolean };

/** Tabs where every tab is its own page, so a link opens the same tab. */
export function TabLinks({ label, items }: { label: string; items: TabLinkItem[] }) {
  const pathname = usePathname() ?? "";
  const isCurrent = ({ href, exact }: TabLinkItem) =>
    pathname === href || (!exact && pathname.startsWith(`${href}/`));

  return (
    <nav className="ui-tabs-list" aria-label={label}>
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className="ui-tab"
          aria-current={isCurrent(item) ? "page" : undefined}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
