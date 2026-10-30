import Link from "next/link";
import type { ComponentProps } from "react";

/** An inline link in body text colour; underlined so it never relies on colour alone. */
export function TextLink({ className = "", ...props }: ComponentProps<typeof Link>) {
  return <Link className={`ui-text-link ${className}`} {...props} />;
}
