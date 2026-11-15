import { Tag, TextLink } from "@/components/ui";

import { ChartMark, TipLines } from "./ChartTip";

export type RankedCandidate = {
  rank: number;
  candidate_id: string;
  file_name: string;
  name: string;
  score: string;
  grade: string;
};

const TOP_COLOURED = 3;

/** The best candidates by AI score, best first: a bar as long as the score out of 100. The top
 * three are filled with the accent, the rest are neutral. Each name opens the candidate. */
export function Ranking({
  projectId,
  candidates,
}: {
  projectId: string;
  candidates: RankedCandidate[];
}) {
  return (
    <ol className="chart-ranking" aria-label="Ranking">
      {candidates.map((item) => (
        <li key={item.candidate_id} className="chart-ranking__item">
          <ChartMark
            tip={
              <TipLines
                title={item.name || item.file_name}
                lines={[`Rank ${item.rank}`, `AI score ${item.score}`, `Grade ${item.grade}`]}
              />
            }
            className="chart-ranking__row"
          >
            <span className="chart-ranking__rank">{item.rank}</span>
            <span className="chart-ranking__name">
              <TextLink href={`/company/projects/${projectId}/candidates/${item.candidate_id}`}>
                {item.name || item.file_name}
              </TextLink>
            </span>
            <span className="chart-ranking__track">
              <span
                className={`chart-ranking__bar${item.rank > TOP_COLOURED ? " chart-ranking__bar--rest" : ""}`}
                style={{ width: `${Number(item.score)}%` }}
              />
            </span>
            <span className="chart-ranking__value">
              {item.score} <Tag variant="neutral">Grade {item.grade}</Tag>
            </span>
          </ChartMark>
        </li>
      ))}
    </ol>
  );
}
