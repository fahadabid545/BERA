import { Menu, type MenuItem } from "@/components/ui";

function initialsOf(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .map((word) => word[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export function UserMenu({ userName, items }: { userName: string; items: MenuItem[] }) {
  return (
    <Menu
      trigger={
        <button type="button" className="panel-avatar">
          <span aria-hidden="true">{initialsOf(userName)}</span>
          <span className="visually-hidden">User menu</span>
        </button>
      }
      items={items}
    />
  );
}
