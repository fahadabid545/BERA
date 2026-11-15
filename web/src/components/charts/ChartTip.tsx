import type { CSSProperties, ReactNode } from "react";

import { Tooltip } from "@/components/ui";

/** The text of a chart tooltip: a short title and one line for each fact. */
export function TipLines({ title, lines }: { title: string; lines: string[] }) {
  return (
    <span className="chart-tip">
      <strong className="chart-tip__title">{title}</strong>
      {lines.map((line) => (
        <span key={line} className="chart-tip__line">
          {line}
        </span>
      ))}
    </span>
  );
}

/**
 * One mark of a chart that shows its details on hover and on keyboard focus. With `onOpen` it is
 * a button (the popup with what is behind the mark); without, it is only focusable, so the
 * tooltip is reachable without a mouse.
 */
export function ChartMark({
  tip,
  onOpen,
  className,
  as: Wrapper = "div",
  label,
  style,
  children,
}: {
  tip: ReactNode;
  onOpen?: () => void;
  className?: string;
  as?: "div" | "span";
  /** What a screen reader says for a mark that is not a button. */
  label?: string;
  style?: CSSProperties;
  children?: ReactNode;
}) {
  const classes = `${className ?? ""}${onOpen ? " chart-mark chart-mark--open" : " chart-mark"}`;
  return (
    <Tooltip content={tip}>
      {onOpen ? (
        <button type="button" className={classes} style={style} onClick={onOpen}>
          {children}
        </button>
      ) : (
        <Wrapper
          className={classes}
          style={style}
          tabIndex={0}
          role={label ? "img" : undefined}
          aria-label={label}
        >
          {children}
        </Wrapper>
      )}
    </Tooltip>
  );
}
