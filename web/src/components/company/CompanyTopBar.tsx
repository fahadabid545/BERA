import { ButtonLink } from "@/components/ui";

import { CompanyUserMenu } from "./CompanyUserMenu";
import { NEW_PROJECT_HREF, type CompanyRole } from "./navigation";
import { OfflineNotice } from "./OfflineNotice";
import { UsageMeter } from "./UsageMeter";

export function CompanyTopBar({
  companyName,
  userName,
  role,
}: {
  companyName: string;
  userName: string;
  role: CompanyRole;
}) {
  return (
    <>
      <p className="panel-topbar__name">{companyName}</p>
      <OfflineNotice />
      {role === "owner" && <UsageMeter />}
      <ButtonLink href={NEW_PROJECT_HREF}>
        <span aria-hidden="true">+</span>
        <span className="company-new-label">New project</span>
      </ButtonLink>
      <CompanyUserMenu userName={userName} role={role} />
    </>
  );
}
