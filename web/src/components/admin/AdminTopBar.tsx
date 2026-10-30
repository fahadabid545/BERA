import { UserMenu } from "@/components/panel/UserMenu";
import { Tag, ThemeToggle } from "@/components/ui";

export function AdminTopBar({ userName }: { userName: string }) {
  return (
    <>
      <div className="panel-topbar__name">
        <Tag variant="admin">Admin</Tag>
      </div>
      <ThemeToggle />
      <UserMenu userName={userName} items={[]} />
    </>
  );
}
