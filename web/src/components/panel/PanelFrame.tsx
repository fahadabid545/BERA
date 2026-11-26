"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { Button } from "@/components/ui";

import { isCurrentPath, type SidebarItem } from "./navigation";
import { NoAccess } from "./NoAccess";
import { PanelSidebar } from "./PanelSidebar";

/**
 * The shared frame of a signed-in area: sidebar, top bar and the page between.
 * The company panel and the admin panel both use it; `variant` only changes the look.
 */
export function PanelFrame({
  variant,
  navigationLabel,
  homeHref,
  items,
  blockedHrefs = [],
  topBar,
  belowTopBar,
  sidebarFooter,
  children,
}: {
  variant: "company" | "admin";
  navigationLabel: string;
  homeHref: string;
  items: SidebarItem[];
  blockedHrefs?: string[];
  topBar: ReactNode;
  /** Shown on every page between the top bar and the page, e.g. the company agent's talk bar. */
  belowTopBar?: ReactNode;
  /** Shown at the bottom of the sidebar, e.g. Feedback and Support. */
  sidebarFooter?: ReactNode;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const isBlocked = blockedHrefs.some((href) => isCurrentPath(pathname, href));

  // On phones the sidebar is a slide-out menu; close it after the user picks a page.
  useEffect(() => setMenuOpen(false), [pathname]);

  return (
    <div
      className={`panel-frame panel--${variant}`}
      data-menu-open={menuOpen}
      onKeyDown={(event) => event.key === "Escape" && setMenuOpen(false)}
    >
      <PanelSidebar
        items={items}
        pathname={pathname}
        label={navigationLabel}
        homeHref={homeHref}
        footer={sidebarFooter}
      />
      <div className="panel-scrim" onClick={() => setMenuOpen(false)} />
      <div className="panel-body">
        <header className="panel-topbar">
          <Button
            variant="secondary"
            className="panel-menu-button"
            aria-label="Menu"
            aria-expanded={menuOpen}
            aria-controls="panel-menu"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span aria-hidden="true">☰</span>
          </Button>
          {topBar}
        </header>
        {belowTopBar ? <div className="panel-below-topbar">{belowTopBar}</div> : null}
        <main className="panel-main">{isBlocked ? <NoAccess /> : children}</main>
      </div>
    </div>
  );
}
