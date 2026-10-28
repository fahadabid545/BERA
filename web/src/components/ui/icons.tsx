/* Small inline icons. They are decorative: the words next to them carry the meaning. */
import type { ReactNode } from "react";

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      className="ui-icon"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export const WarningIcon = () => (
  <Icon>
    <path d="M8 2 14.5 13.5h-13z" />
    <path d="M8 6.5v3.2M8 11.7v.1" />
  </Icon>
);

export const ErrorIcon = () => (
  <Icon>
    <circle cx="8" cy="8" r="6.2" />
    <path d="m5.7 5.7 4.6 4.6M10.3 5.7l-4.6 4.6" />
  </Icon>
);

export const CheckIcon = () => (
  <Icon>
    <path d="m3 8.5 3.2 3.2L13 4.8" />
  </Icon>
);
