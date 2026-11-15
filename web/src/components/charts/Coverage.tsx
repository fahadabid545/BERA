import { Tag } from "@/components/ui";

const PERCENT = 100;

export type RequirementCoverage = {
  requirement_id: string;
  text: string;
  kind: "must" | "nice";
  met: number;
  partly_met: number;
  missing: number;
  not_judged: number;
};

const PARTS = [
  { key: "met", label: "Met" },
  { key: "partly_met", label: "Partly met" },
  { key: "missing", label: "Missing" },
  { key: "not_judged", label: "Not judged" },
] as const;

/** How well the candidates meet each requirement: one bar for each, split into met, partly met,
 * missing and not judged. Each part has its own surface (solid, hatched, outlined) and its
 * count is written below, so nothing depends on colour. */
export function Coverage({
  candidates,
  requirements,
}: {
  candidates: number;
  requirements: RequirementCoverage[];
}) {
  return (
    <ul className="chart-coverage" aria-label="Requirement coverage">
      {requirements.map((item) => (
        <li key={item.requirement_id} className="chart-coverage__row">
          <div className="chart-coverage__title">
            <span>{item.text}</span>
            <Tag variant="neutral">{item.kind === "must" ? "Must-have" : "Nice-to-have"}</Tag>
          </div>
          <div className="chart-coverage__bar">
            {PARTS.map(({ key }) =>
              item[key] > 0 ? (
                <span
                  key={key}
                  className={`chart-coverage__part chart-coverage__part--${key}`}
                  style={{ width: `${(item[key] * PERCENT) / Math.max(1, candidates)}%` }}
                />
              ) : null,
            )}
          </div>
          <div className="chart-coverage__counts">
            {PARTS.map(({ key, label }) => (
              <span key={key}>
                {label} {item[key]}
              </span>
            ))}
          </div>
        </li>
      ))}
    </ul>
  );
}
