import { ButtonLink } from "@/components/ui";
import { UserMenu } from "@/components/panel/UserMenu";

import { NEW_PROJECT_HREF, PROFILE_HREF, type CompanyRole } from "./navigation";
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
      {role === "owner" && <UsageMeter />}
      <ButtonLink href={NEW_PROJECT_HREF}>
        <span aria-hidden="true">+</span>
        <span className="company-new-label">New project</span>
      </ButtonLink>
      <UserMenu userName={userName} items={[{ label: "Profile", href: PROFILE_HREF }]} />
    </>
  );
}
