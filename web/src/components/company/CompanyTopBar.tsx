import { ButtonLink } from "@/components/ui";
import { UserMenu } from "@/components/panel/UserMenu";

import { LOG_OUT_HREF, NEW_PROJECT_HREF, PROFILE_HREF } from "./navigation";

export function CompanyTopBar({
  companyName,
  userName,
}: {
  companyName: string;
  userName: string;
}) {
  return (
    <>
      <p className="panel-topbar__name">{companyName}</p>
      <ButtonLink href={NEW_PROJECT_HREF}>
        <span aria-hidden="true">+</span>
        <span className="company-new-label">New project</span>
      </ButtonLink>
      <UserMenu
        userName={userName}
        items={[
          { label: "Profile", href: PROFILE_HREF },
          { label: "Log out", href: LOG_OUT_HREF },
        ]}
      />
    </>
  );
}
