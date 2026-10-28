import type { ReactNode } from "react";

/** Scrolls sideways on narrow screens; the region is focusable so keyboard users can scroll it. */
export function Table({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="ui-table-wrap" role="region" aria-label={label} tabIndex={0}>
      <table className="ui-table">{children}</table>
    </div>
  );
}
