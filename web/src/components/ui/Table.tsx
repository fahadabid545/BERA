import type { ReactNode } from "react";

/** Scrolls sideways on narrow screens; the region is focusable so keyboard users can scroll it.
 * `sticky` keeps the header row and the first three columns in view while the rest scrolls. */
export function Table({
  label,
  sticky = false,
  children,
}: {
  label: string;
  sticky?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className={`ui-table-wrap${sticky ? " ui-table-wrap--sticky" : ""}`}
      role="region"
      aria-label={label}
      tabIndex={0}
    >
      <table className="ui-table">{children}</table>
    </div>
  );
}
