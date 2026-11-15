import { Tag, TextLink } from "@/components/ui";

import { ChartMark, TipLines } from "./ChartTip";

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
 * count is written below; hovering a part gives its share. The requirement opens the list of
 * requirements when the project is known. */
export function Coverage({
  candidates,
  requirements,
  projectId,
}: {
  candidates: number;
  requirements: RequirementCoverage[];
  projectId?: string;
}) {
  return (
    <ul className="chart-coverage" aria-label="Requirement coverage">
      {requirements.map((item) => (
        <li key={item.requirement_id} className="chart-coverage__row">
          <div className="chart-coverage__title">
            {projectId ? (
              <TextLink href={`/company/projects/${projectId}/requirements`}>{item.text}</TextLink>
            ) : (
              <span>{item.text}</span>
            )}
            <Tag variant="neutral">{item.kind === "must" ? "Must-have" : "Nice-to-have"}</Tag>
          </div>
          <div className="chart-coverage__bar">
            {PARTS.map(({ key, label }) =>
              item[key] > 0 ? (
                <ChartMark
                  key={key}
                  as="span"
                  label={`${label} ${item[key]}`}
                  tip={
                    <TipLines
                      title={item.text}
                      lines={[
                        `${label}: ${item[key]} of ${candidates} candidates`,
                        `${Math.round((item[key] * PERCENT) / Math.max(1, candidates))}% of those scored`,
                      ]}
                    />
                  }
                  className={`chart-coverage__part chart-coverage__part--${key}`}
                  style={{ width: `${(item[key] * PERCENT) / Math.max(1, candidates)}%` }}
                ></ChartMark>
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
