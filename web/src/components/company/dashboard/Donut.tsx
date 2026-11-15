import { ChartMark, TipLines } from "@/components/charts/ChartTip";
import { Tooltip } from "@/components/ui";

const CIRCUMFERENCE = 100; // the circle's radius is chosen so its length is 100 units
const RADIUS = 15.9155;
const PERCENT = 100;

export type DonutPart = { key: string; label: string; count: number; colour: string };

/** A ring split into parts with the total in the middle. Hovering a slice or a legend line gives
 * its count and share; clicking opens who is in it. The legend repeats every part as a button,
 * so the ring is also reachable by keyboard and never relies on colour. */
export function Donut({
  parts,
  total,
  centreLabel,
  noun,
  onOpen,
}: {
  parts: DonutPart[];
  total: number;
  centreLabel: string;
  noun: string;
  onOpen: (key: string) => void;
}) {
  let offset = 0;
  const share = (count: number) => (total ? Math.round((count * PERCENT) / total) : 0);
  const tip = (part: DonutPart) => (
    <TipLines
      title={part.label}
      lines={[`${part.count} ${noun}`, `${share(part.count)}% of ${total}`]}
    />
  );
  return (
    <div className="donut">
      <div className="donut__ring">
        <svg viewBox="0 0 36 36" aria-hidden="true">
          <circle className="donut__track" cx="18" cy="18" r={RADIUS} />
          {total > 0 &&
            parts.map((part) => {
              const length = (part.count * CIRCUMFERENCE) / total;
              const slice = (
                <circle
                  key={part.key}
                  className="donut__slice"
                  cx="18"
                  cy="18"
                  r={RADIUS}
                  stroke={`var(--color-data-${part.colour})`}
                  strokeDasharray={`${length} ${CIRCUMFERENCE - length}`}
                  strokeDashoffset={-offset}
                  onClick={() => onOpen(part.key)}
                />
              );
              offset += length;
              return length > 0 ? (
                <Tooltip key={part.key} content={tip(part)}>
                  {slice}
                </Tooltip>
              ) : null;
            })}
        </svg>
        <span className="donut__centre">
          <strong>{total}</strong>
          <span>{centreLabel}</span>
        </span>
      </div>
      <ul className="donut__legend">
        {parts.map((part) => (
          <li key={part.key}>
            <ChartMark className="donut__item" tip={tip(part)} onOpen={() => onOpen(part.key)}>
              <span
                className="donut__swatch"
                style={{ background: `var(--color-data-${part.colour})` }}
              />
              <span>{part.label}</span>
              <strong>{part.count}</strong>
            </ChartMark>
          </li>
        ))}
      </ul>
    </div>
  );
}
