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
 * with the share kept from the step before written beside it. */
export function Funnel({ steps }: { steps: FunnelStep[] }) {
  const widest = Math.max(1, ...steps.map((item) => item.count));
  return (
    <ol className="chart-funnel" aria-label="Funnel">
      {steps.map((item, index) => {
        const before = index > 0 ? steps[index - 1].count : 0;
        const kept = before > 0 ? Math.round((item.count * PERCENT) / before) : null;
        return (
          <li key={item.step} className="chart-funnel__step">
            <span className="chart-funnel__label">{LABELS[item.step] ?? item.step}</span>
            <span className="chart-funnel__track">
              <span
                className="chart-funnel__bar"
                style={{ width: `${(item.count * PERCENT) / widest}%` }}
              />
            </span>
            <span className="chart-funnel__value">
              {item.count}
              {kept !== null && <span className="chart-funnel__kept"> · {kept}%</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
