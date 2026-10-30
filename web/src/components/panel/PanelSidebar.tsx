"use client";

import Link from "next/link";
import { useState } from "react";

import { ToggleIcon } from "@/components/ui";

import { isCurrentPath, type SidebarItem } from "./navigation";

function Chevron() {
  return (
    <svg className="panel-chevron" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path d="m4 6 4 4 4-4" />
    </svg>
  );
}

export function PanelSidebar({
  items,
  pathname,
  label,
  homeHref,
}: {
  items: SidebarItem[];
  pathname: string;
  label: string;
  homeHref: string;
}) {
  // Sub-menus start closed, even on one of their own pages, and only a click opens them.
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  return (
    <aside className="panel-sidebar" id="panel-menu">
      <Link href={homeHref} className="site-brand panel-brand">
        Bera
      </Link>
      <nav aria-label={label}>
        <ul className="panel-nav">
          {items.map((item) => {
            const itemLabel = <span className="panel-label">{item.label}</span>;
            if (!item.children) {
              return (
                <li key={item.href} data-separated={item.separated || undefined}>
                  <Link
                    href={item.href}
                    className="ui-icon-item"
                    title={item.label}
                    aria-current={
                      isCurrentPath(pathname, item.href, item.exact) ? "page" : undefined
                    }
                  >
                    <ToggleIcon name={item.icon} />
                    {itemLabel}
                  </Link>
                </li>
              );
            }

            const submenuId = `panel-submenu-${item.label.toLowerCase().replace(/ /g, "-")}`;
            const isOpen = openGroup === item.label;
            return (
              <li key={item.href} data-separated={item.separated || undefined}>
                <button
                  type="button"
                  className="ui-icon-item panel-group"
                  title={item.label}
                  aria-expanded={isOpen}
                  aria-controls={submenuId}
                  data-active={isCurrentPath(pathname, item.href)}
                  onClick={() => setOpenGroup(isOpen ? null : item.label)}
                >
                  <ToggleIcon name={item.icon} />
                  {itemLabel}
                  <Chevron />
                </button>
                {isOpen && (
                  <ul id={submenuId} className="panel-submenu">
                    {item.children.map((child) => (
                      <li key={child.href}>
                        <Link
                          href={child.href}
                          className="ui-icon-item"
                          aria-current={isCurrentPath(pathname, child.href) ? "page" : undefined}
                        >
                          {child.label}
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
