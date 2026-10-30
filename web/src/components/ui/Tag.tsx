import type { ReactNode } from "react";

export type TagVariant = "neutral" | "success" | "warning" | "danger" | "live" | "admin";

/** Status is always shown in words; each variant also has its own surface (see components.css). */
export function Tag({
  variant = "neutral",
  children,
}: {
  variant?: TagVariant;
  children: ReactNode;
}) {
  return (
    <span className={`ui-tag ui-tag--${variant}`}>
      {variant === "live" && <span className="ui-tag__dot" aria-hidden="true" />}
      {children}
    </span>
  );
}
