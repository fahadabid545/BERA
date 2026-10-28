import Link from "next/link";
import type { ComponentProps } from "react";

import type { ButtonVariant } from "./Button";

/** A link that looks like a Button, for actions that go to another page. */
export function ButtonLink({
  variant = "primary",
  className = "",
  ...props
}: ComponentProps<typeof Link> & { variant?: ButtonVariant }) {
  return <Link className={`ui-button ui-button--${variant} ${className}`} {...props} />;
}
