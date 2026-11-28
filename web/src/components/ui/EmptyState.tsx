import type { HTMLAttributes } from "react";

import { type Tint } from "./tints";

/** The card that stands in for a list with nothing in it. Words only; the caller says which. */
export function EmptyState({
  tint = "sky",
  className = "",
  ...props
}: HTMLAttributes<HTMLParagraphElement> & { tint?: Tint }) {
  return <p className={`empty-state ${className}`.trim()} data-tint={tint} {...props} />;
}
