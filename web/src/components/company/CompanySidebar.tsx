"use client";

import Link from "next/link";
import { useState } from "react";

import { ToggleIcon } from "@/components/ui";

import { isCurrentPath, visibleNavigation, type CompanyRole } from "./navigation";

function Chevron() {
  return (
    <svg className="company-chevron" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path d="m4 6 4 4 4-4" />
    </svg>
  );
}

export function CompanySidebar({ role, pathname }: { role: CompanyRole; pathname: string }) {
  // Sub-menus start closed, even on one of their own pages, and only a click opens them.
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  return (
    <aside className="company-sidebar" id="company-menu">
      <Link href="/company" className="site-brand company-brand">
        Bera
      </Link>
      <nav aria-label="Company">
        <ul className="company-nav">
          {visibleNavigation(role).map((item) => {
            const label = <span className="company-label">{item.label}</span>;
            if (!item.children) {
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className="ui-icon-item"
                    title={item.label}
                    aria-current={
                      isCurrentPath(pathname, item.href, item.exact) ? "page" : undefined
                    }
                  >
                    <ToggleIcon name={item.icon} />
                    {label}
                  </Link>
                </li>
              );
            }

            const submenuId = `company-submenu-${item.label.toLowerCase()}`;
            const isOpen = openGroup === item.label;
            return (
              <li key={item.href}>
                <button
                  type="button"
                  className="ui-icon-item company-group"
                  title={item.label}
                  aria-expanded={isOpen}
                  aria-controls={submenuId}
                  data-active={isCurrentPath(pathname, item.href)}
                  onClick={() => setOpenGroup(isOpen ? null : item.label)}
                >
                  <ToggleIcon name={item.icon} />
                  {label}
                  <Chevron />
                </button>
                {isOpen && (
                  <ul id={submenuId} className="company-submenu">
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
