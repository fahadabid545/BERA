import type { ReactNode } from "react";

import { CheckIcon, ErrorIcon, WarningIcon } from "./icons";

export type TagVariant = "neutral" | "success" | "warning" | "danger" | "live";

const ICONS: Record<TagVariant, ReactNode> = {
  neutral: null,
  success: <CheckIcon />,
  warning: <WarningIcon />,
  danger: <ErrorIcon />,
  live: <span className="ui-tag__dot" aria-hidden="true" />,
};

/** Status is always shown by an icon and the words, never by colour alone. */
export function Tag({
  variant = "neutral",
  children,
}: {
  variant?: TagVariant;
  children: ReactNode;
}) {
  return (
    <span className={`ui-tag ui-tag--${variant}`}>
      {ICONS[variant]}
      {children}
    </span>
  );
}
