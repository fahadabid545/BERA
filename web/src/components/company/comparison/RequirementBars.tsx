import { ChartMark, TipLines } from "@/components/charts/ChartTip";
import { Tag } from "@/components/ui";

import { TermLabel } from "./terms";
import {
  VERDICT_WORDS,
  colourOf,
  displayName,
  type Compared,
  type Requirement,
  type Verdict,
} from "./types";
import type { Evidence } from "./EvidencePopup";

const PERCENT = 100;

/** Requirement by requirement: for each one a bar for every candidate, as long as the points its
 * result earns and in the candidate's colour, with the verdict written beside it. Hovering a bar
 * gives the details, clicking it opens the words from the CV the verdict rests on. */
export function RequirementBars({
  requirements,
  candidates,
  points,
  onOpen,
}: {
  requirements: Requirement[];
  candidates: Compared[];
  points: Record<Verdict, number>;
  onOpen: (selection: Evidence) => void;
}) {
  return (
    <div className="req-bars">
      <ul className="req-bars__legend" aria-label="Candidates">
        {candidates.map((item, index) => (
          <li key={item.id}>
            <span className={`req-bars__swatch req-bars__swatch--${colourOf(index)}`} />
            {displayName(item)}
          </li>
        ))}
      </ul>
      {requirements.map((requirement, row) => (
        <div key={requirement.id} className="req-bars__group">
          <div className="req-bars__title">
            <span>{requirement.text}</span>
            <TermLabel term={requirement.kind}>
              <Tag variant="neutral">
                {requirement.kind === "must" ? "Must-have" : "Nice-to-have"}
              </Tag>
            </TermLabel>
          </div>
          {candidates.map((item, index) => {
            const cell = item.results[row];
            const verdict = cell.verdict;
            const earned = verdict ? points[verdict] : 0;
            return (
              <ChartMark
                key={item.id}
                className="req-bar"
                onOpen={() => onOpen({ candidate: item, requirement, cell })}
                tip={
                  <TipLines
                    title={displayName(item)}
                    lines={[
                      requirement.text,
                      verdict ? `${VERDICT_WORDS[verdict]}, ${earned} points` : "Not judged yet",
                      `Weight ${requirement.weight}`,
                    ]}
                  />
                }
              >
                <span className="req-bar__name">{displayName(item)}</span>
                <span className="req-bar__track">
                  <span
                    className={`req-bar__fill req-bar__fill--${colourOf(index)}${
                      verdict === "partly_met" ? " req-bar__fill--partly" : ""
                    }${verdict === null ? " req-bar__fill--none" : ""}`}
                    style={{ width: `${Math.min(PERCENT, earned)}%` }}
                  />
                </span>
                <span className="req-bar__verdict">
                  {verdict ? VERDICT_WORDS[verdict] : "Not judged"}
                </span>
              </ChartMark>
            );
          })}
        </div>
      ))}
    </div>
  );
}
