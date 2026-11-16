import { ChartMark, TipLines } from "@/components/charts/ChartTip";

import { colourOf, displayName, type Compared, type Fact, type Requirement } from "./types";

function Line({
  fact,
  candidates,
  requirements,
}: {
  fact: Fact;
  candidates: Compared[];
  requirements: Requirement[];
}) {
  const named = (id: string) => {
    const found = candidates.find((item) => item.id === id);
    return found ? displayName(found) : "";
  };
  const texts = (ids: string[]) =>
    ids.map((id) => requirements.find((item) => item.id === id)?.text ?? "").join(", ");
  if (fact.kind === "lead") {
    return (
      <>
        {named(fact.candidate)} is ahead of {named(fact.over)} by {fact.points} points
      </>
    );
  }
  if (fact.kind === "tie") {
    return <>{fact.candidates.map(named).join(" and ")} have the same AI score</>;
  }
  if (fact.kind === "must_gap") {
    return (
      <>
        {named(fact.candidate)} is missing{" "}
        {fact.requirements.length === 1 ? "a must-have" : "must-haves"}: {texts(fact.requirements)}
      </>
    );
  }
  return (
    <>
      {named(fact.candidate)} is clearly best on {texts(fact.requirements)}
    </>
  );
}

function tipOf(fact: Fact, candidates: Compared[]) {
  const scoreOf = (id: string) => {
    const found = candidates.find((item) => item.id === id);
    return found ? `${displayName(found)}: AI score ${found.score ?? "none"}` : "";
  };
  const ids =
    fact.kind === "lead"
      ? [fact.candidate, fact.over]
      : fact.kind === "tie"
        ? fact.candidates
        : [fact.candidate];
  return <TipLines title="Scores" lines={ids.map(scoreOf)} />;
}

/** What stands out in this comparison, in a sentence each: who leads, who is missing a
 * must-have, who is clearly best on what. Each sentence has the colour of its candidate. */
export function CompareInsights({
  facts,
  candidates,
  requirements,
}: {
  facts: Fact[];
  candidates: Compared[];
  requirements: Requirement[];
}) {
  if (facts.length === 0) return null;
  return (
    <ul className="compare-insights">
      {facts.map((fact, index) => {
        const owner = "candidate" in fact ? fact.candidate : fact.candidates[0];
        const colour = colourOf(
          Math.max(
            0,
            candidates.findIndex((item) => item.id === owner),
          ),
        );
        return (
          <li key={`${fact.kind}-${index}`}>
            <ChartMark
              className={`compare-insight compare-insight--${colour}`}
              tip={tipOf(fact, candidates)}
            >
              <Line fact={fact} candidates={candidates} requirements={requirements} />
            </ChartMark>
          </li>
        );
      })}
    </ul>
  );
}
