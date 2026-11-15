import { ChartMark, TipLines } from "@/components/charts/ChartTip";

const SEGMENTS = 11;
const CENTRE = 150;
const OUTER = 120;
const INNER = 80;
const GAP = 0.03;
const PERCENT = 100;

function segment(index: number) {
  const start = Math.PI - (index / SEGMENTS) * Math.PI - GAP;
  const end = Math.PI - ((index + 1) / SEGMENTS) * Math.PI + GAP;
  const at = (radius: number, angle: number) =>
    `${CENTRE + radius * Math.cos(angle)},${CENTRE - radius * Math.sin(angle)}`;
  return `M${at(OUTER, start)} A${OUTER},${OUTER} 0 0 1 ${at(OUTER, end)} L${at(INNER, end)} A${INNER},${INNER} 0 0 0 ${at(INNER, start)} Z`;
}

/** A half ring made of segments, filled as far as the percentage. The number is written in the
 * middle and the counts behind it in the tooltip; clicking opens the projects. */
export function Gauge({
  percent,
  scored,
  uploaded,
  onOpen,
}: {
  percent: number | null;
  scored: number;
  uploaded: number;
  onOpen: () => void;
}) {
  const filled = percent === null ? 0 : Math.round((percent / PERCENT) * SEGMENTS);
  return (
    <ChartMark
      className="gauge"
      onOpen={onOpen}
      tip={
        <TipLines
          title="Screening progress"
          lines={[
            `${scored} of ${uploaded} CVs scored`,
            `${Math.max(0, uploaded - scored)} still to go`,
          ]}
        />
      }
    >
      <svg viewBox="0 0 300 165" className="gauge__svg" aria-hidden="true">
        {Array.from({ length: SEGMENTS }, (_, index) => (
          <path
            key={index}
            d={segment(index)}
            className={index < filled ? "gauge__segment gauge__segment--on" : "gauge__segment"}
          />
        ))}
      </svg>
      <span className="gauge__value">{percent === null ? "No CVs" : `${percent}%`}</span>
      <span className="gauge__label">CVs scored</span>
    </ChartMark>
  );
}
