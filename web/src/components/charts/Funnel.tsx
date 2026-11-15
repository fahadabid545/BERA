import { ChartMark, TipLines } from "./ChartTip";

const LABELS: Record<string, string> = {
  uploaded: "Uploaded",
  read: "Read",
  scored: "Scored",
  shortlisted: "Shortlisted",
  interview: "Interview",
  approved: "Approved",
};
const PERCENT = 100;

export type FunnelStep = { step: string; count: number };

/** How far the CVs get: one bar for each step, each as wide as its count against the first step,
 * with the share kept from the step before written beside it. Hovering a step says how it
 * compares; with `onOpen`, clicking it opens who is behind it. */
export function Funnel({
  steps,
  onOpen,
}: {
  steps: FunnelStep[];
  onOpen?: (step: string) => void;
}) {
  const widest = Math.max(1, ...steps.map((item) => item.count));
  const first = steps[0]?.count ?? 0;
  return (
    <ol className="chart-funnel" aria-label="Funnel">
      {steps.map((item, index) => {
        const before = index > 0 ? steps[index - 1] : null;
        const kept =
          before && before.count > 0 ? Math.round((item.count * PERCENT) / before.count) : null;
        const label = LABELS[item.step] ?? item.step;
        const lines = [`${item.count} in this step`];
        if (before && kept !== null) {
          lines.push(`${kept}% of ${LABELS[before.step] ?? before.step}`);
        }
        if (index > 0 && first > 0) {
          lines.push(`${Math.round((item.count * PERCENT) / first)}% of all uploaded`);
        }
        return (
          <li key={item.step} className="chart-funnel__item">
            <ChartMark
              tip={<TipLines title={label} lines={lines} />}
              onOpen={onOpen ? () => onOpen(item.step) : undefined}
              className="chart-funnel__step"
            >
              <span className="chart-funnel__label">{label}</span>
              <span className="chart-funnel__track">
                <span
                  className={`chart-funnel__bar chart-funnel__bar--${item.step}`}
                  style={{ width: `${(item.count * PERCENT) / widest}%` }}
                />
              </span>
              <span className="chart-funnel__value">
                {item.count}
                {kept !== null && <span className="chart-funnel__kept"> · {kept}%</span>}
              </span>
            </ChartMark>
          </li>
        );
      })}
    </ol>
  );
}
