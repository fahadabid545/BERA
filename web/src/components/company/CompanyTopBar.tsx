import { Button, ButtonLink, Menu } from "@/components/ui";

import { LOG_OUT_HREF, NEW_PROJECT_HREF, PROFILE_HREF } from "./navigation";

function initialsOf(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .map((word) => word[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export function CompanyTopBar({
  companyName,
  userName,
  menuOpen,
  onMenuClick,
}: {
  companyName: string;
  userName: string;
  menuOpen: boolean;
  onMenuClick: () => void;
}) {
  return (
    <header className="company-topbar">
      <Button
        variant="secondary"
        className="company-menu-button"
        aria-label="Menu"
        aria-expanded={menuOpen}
        aria-controls="company-menu"
        onClick={onMenuClick}
      >
        <span aria-hidden="true">☰</span>
      </Button>
      <p className="company-topbar__name">{companyName}</p>
      <ButtonLink href={NEW_PROJECT_HREF}>
        <span aria-hidden="true">+</span>
        <span className="company-new-label">New project</span>
      </ButtonLink>
      <Menu
        trigger={
          <button type="button" className="company-avatar">
            <span aria-hidden="true">{initialsOf(userName)}</span>
            <span className="visually-hidden">User menu</span>
          </button>
        }
        items={[
          { label: "Profile", href: PROFILE_HREF },
          { label: "Log out", href: LOG_OUT_HREF },
        ]}
      />
    </header>
  );
}
