import { ChartMark, TipLines } from "@/components/charts/ChartTip";
import { Tag, TextLink } from "@/components/ui";

import { stageLabel } from "../stages";
import { TermLabel } from "./terms";
import { LABEL_WORDS, colourOf, displayName, type Compared } from "./types";

/** One card for each candidate: colour, name, the scores and where they stand. The candidate
 * with the highest AI score is marked. Hovering a card gives the scores of each group. */
export function CandidateCards({
  projectId,
  candidates,
}: {
  projectId: string;
  candidates: Compared[];
}) {
  const best = Math.max(...candidates.map((item) => (item.score ? Number(item.score) : -1)));
  return (
    <ul className="compare-cards">
      {candidates.map((item, index) => (
        <li key={item.id}>
          <ChartMark
            className={`compare-card compare-card--${colourOf(index)}`}
            tip={
              <TipLines
                title={displayName(item)}
                lines={[
                  `Must-have score ${item.must_score ?? "none"}`,
                  `Nice-to-have score ${item.nice_score ?? "none"}`,
                  item.capped ? "Capped: a must-have is missing" : "Not capped",
                  `Must-haves met ${item.summary.must.met} of ${Object.values(item.summary.must).reduce((a, b) => a + b, 0)}`,
                ]}
              />
            }
          >
            <span className="compare-card__name">
              <TextLink href={`/company/projects/${projectId}/candidates/${item.id}`}>
                {displayName(item)}
              </TextLink>
            </span>
            <span className="compare-card__score">
              <TermLabel term="ai_score">{item.score ?? "Not scored"}</TermLabel>
              {item.grade && (
                <TermLabel term="grade">
                  <Tag variant="neutral">Grade {item.grade}</Tag>
                </TermLabel>
              )}
            </span>
            <span className="compare-card__facts">
              <TermLabel term="ats_score">ATS {item.ats_score ?? "none"}</TermLabel>
              {item.label && (
                <TermLabel term="recommendation">
                  <Tag variant={item.label === "strong_match" ? "success" : "neutral"}>
                    {LABEL_WORDS[item.label]}
                  </Tag>
                </TermLabel>
              )}
              {item.borderline && <Tag variant="neutral">Borderline</Tag>}
              {item.outdated && <Tag variant="warning">Outdated</Tag>}
              <Tag variant="neutral">{stageLabel(item.stage)}</Tag>
              {item.score !== null && Number(item.score) === best && candidates.length > 1 && (
                <Tag variant="live">Highest score</Tag>
              )}
            </span>
          </ChartMark>
        </li>
      ))}
    </ul>
  );
}
