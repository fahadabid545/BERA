import type { ReactNode } from "react";

/* Each icon is a main shape plus an optional detail. The detail turns into a cut-out when filled. */
const ICONS = {
  features: {
    shape: (
      <>
        <rect x="2" y="2" width="5" height="5" rx="1" />
        <rect x="9" y="2" width="5" height="5" rx="1" />
        <rect x="2" y="9" width="5" height="5" rx="1" />
        <rect x="9" y="9" width="5" height="5" rx="1" />
      </>
    ),
  },
  "how-it-works": {
    shape: <circle cx="8" cy="8" r="6.2" />,
    detail: <path d="M6.6 5.6v4.8l3.8-2.4z" />,
  },
  pricing: {
    shape: <path d="M2 2h5.6l6.4 6.4-5.6 5.6L2 7.6z" />,
    detail: <path d="M5 5v.1" />,
  },
  faq: {
    shape: <circle cx="8" cy="8" r="6.2" />,
    detail: <path d="M6.3 6.3a1.8 1.8 0 1 1 2.6 1.6c-.6.3-.9.7-.9 1.3M8 11.5v.1" />,
  },
  contact: {
    shape: <rect x="1.5" y="3" width="13" height="10" rx="1.5" />,
    detail: <path d="m2.2 4.3 5.8 4.6 5.8-4.6" />,
  },
} satisfies Record<string, { shape: ReactNode; detail?: ReactNode }>;

export type ToggleIconName = keyof typeof ICONS;

/** Decorative icon that swaps from outline to filled inside a current (active) item. */
export function ToggleIcon({ name }: { name: ToggleIconName }) {
  const { shape, detail } = ICONS[name] as { shape: ReactNode; detail?: ReactNode };
  const drawing = (
    <>
      <g className="shape">{shape}</g>
      <g className="detail">{detail}</g>
    </>
  );
  return (
    <span className="ui-toggle-icon" aria-hidden="true">
      <svg className="ui-toggle-icon__outline" viewBox="0 0 16 16" focusable="false">
        {drawing}
      </svg>
      <svg className="ui-toggle-icon__filled" viewBox="0 0 16 16" focusable="false">
        {drawing}
      </svg>
    </span>
  );
}
