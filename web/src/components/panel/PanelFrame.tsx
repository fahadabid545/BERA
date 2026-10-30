"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { Button } from "@/components/ui";

import type { SidebarItem } from "./navigation";
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
  topBar,
  children,
}: {
  variant: "company" | "admin";
  navigationLabel: string;
  homeHref: string;
  items: SidebarItem[];
  topBar: ReactNode;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  // On phones the sidebar is a slide-out menu; close it after the user picks a page.
  useEffect(() => setMenuOpen(false), [pathname]);

  return (
    <div
      className={`panel-frame panel--${variant}`}
      data-menu-open={menuOpen}
      onKeyDown={(event) => event.key === "Escape" && setMenuOpen(false)}
    >
      <PanelSidebar items={items} pathname={pathname} label={navigationLabel} homeHref={homeHref} />
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
        <main className="panel-main">{children}</main>
      </div>
    </div>
  );
}
