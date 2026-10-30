import { UserMenu } from "@/components/panel/UserMenu";
import { Tag, ThemeToggle } from "@/components/ui";

import { ADMIN_LOG_OUT_HREF } from "./navigation";

export function AdminTopBar({ userName }: { userName: string }) {
  return (
    <>
      <div className="panel-topbar__name">
        <Tag variant="admin">Admin</Tag>
      </div>
      <ThemeToggle />
      <UserMenu userName={userName} items={[{ label: "Log out", href: ADMIN_LOG_OUT_HREF }]} />
    </>
  );
}
