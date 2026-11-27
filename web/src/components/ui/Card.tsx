import type { HTMLAttributes } from "react";

export function Card({
  selected = false,
  className = "",
  ...props
}: HTMLAttributes<HTMLElement> & { selected?: boolean }) {
  return <section className={`ui-card ${className}`.trim()} data-selected={selected} {...props} />;
}
