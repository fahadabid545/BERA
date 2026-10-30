"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { CompanySidebar } from "./CompanySidebar";
import { CompanyTopBar } from "./CompanyTopBar";
import type { CompanyRole } from "./navigation";

/** The shared frame of the logged-in company area: sidebar, top bar and the page between. */
export function CompanyFrame({
  companyName,
  userName,
  role,
  children,
}: {
  companyName: string;
  userName: string;
  role: CompanyRole;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  // On phones the sidebar is a slide-out menu; close it after the user picks a page.
  useEffect(() => setMenuOpen(false), [pathname]);

  return (
    <div
      className="company-frame"
      data-menu-open={menuOpen}
      onKeyDown={(event) => event.key === "Escape" && setMenuOpen(false)}
    >
      <CompanySidebar role={role} pathname={pathname} />
      <div className="company-scrim" onClick={() => setMenuOpen(false)} />
      <div className="company-body">
        <CompanyTopBar
          companyName={companyName}
          userName={userName}
          menuOpen={menuOpen}
          onMenuClick={() => setMenuOpen((open) => !open)}
        />
        <main className="company-main">{children}</main>
      </div>
    </div>
  );
}
