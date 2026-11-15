import { Tag, TextLink } from "@/components/ui";

export type RankedCandidate = {
  rank: number;
  candidate_id: string;
  file_name: string;
  name: string;
  score: string;
  grade: string;
};

/** The best candidates by AI score, best first: a bar as long as the score out of 100. */
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
        <li key={item.candidate_id} className="chart-ranking__row">
          <span className="chart-ranking__rank">{item.rank}</span>
          <span className="chart-ranking__name">
            <TextLink href={`/company/projects/${projectId}/candidates/${item.candidate_id}`}>
              {item.name || item.file_name}
            </TextLink>
          </span>
          <span className="chart-ranking__track">
            <span className="chart-ranking__bar" style={{ width: `${Number(item.score)}%` }} />
          </span>
          <span className="chart-ranking__value">
            {item.score} <Tag variant="neutral">Grade {item.grade}</Tag>
          </span>
        </li>
      ))}
    </ol>
  );
}
