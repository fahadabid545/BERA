"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, ButtonLink, ToggleIcon } from "@/components/ui";

import { ACCOUNT_LINKS, NAV_LINKS } from "./links";

export function SiteHeader() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  // Close the phone menu after the visitor picks a page.
  useEffect(() => setMenuOpen(false), [pathname]);

  return (
    <header
      className="site-header"
      onKeyDown={(event) => event.key === "Escape" && setMenuOpen(false)}
    >
      <div className="site-header__inner">
        <Link href="/" className="site-brand">
          Bera
        </Link>
        <Button
          variant="secondary"
          className="site-header__menu-button"
          aria-expanded={menuOpen}
          aria-controls="site-menu"
          onClick={() => setMenuOpen((open) => !open)}
        >
          Menu
        </Button>
        <nav id="site-menu" aria-label="Main" className="site-nav" data-open={menuOpen}>
          <ul className="site-nav__links">
            {NAV_LINKS.map(({ label, href, icon }) => (
              <li key={href}>
                <Link
                  href={href}
                  className="ui-icon-item"
                  aria-current={pathname === href ? "page" : undefined}
                >
                  <ToggleIcon name={icon} />
                  {label}
                </Link>
              </li>
            ))}
          </ul>
          <div className="site-nav__actions">
            <ButtonLink variant="secondary" href={ACCOUNT_LINKS.logIn.href}>
              {ACCOUNT_LINKS.logIn.label}
            </ButtonLink>
            <ButtonLink href={ACCOUNT_LINKS.signUp.href}>{ACCOUNT_LINKS.signUp.label}</ButtonLink>
          </div>
        </nav>
      </div>
    </header>
  );
}
