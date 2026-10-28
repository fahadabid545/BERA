import type { HTMLAttributes } from "react";

export function Card({
  selected = false,
  ...props
}: HTMLAttributes<HTMLElement> & { selected?: boolean }) {
  return <section className="ui-card" data-selected={selected} {...props} />;
}
