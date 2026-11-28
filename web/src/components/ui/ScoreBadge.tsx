/** The grade letters come from the server, which decides the bands (scoring.grade_*_min). */
const TONE_BY_GRADE: Record<string, "strong" | "fair" | "weak"> = {
  A: "strong",
  B: "strong",
  C: "fair",
  D: "weak",
  E: "weak",
};

export function ScoreBadge({
  score,
  grade,
  large = false,
}: {
  score: number | null;
  grade: string | null;
  large?: boolean;
}) {
  if (score === null) {
    return <span className="ui-score ui-score--none">No score</span>;
  }
  const tone = (grade && TONE_BY_GRADE[grade]) || "fair";
  return (
    <span className={`ui-score ui-score--${tone}${large ? " ui-score--large" : ""}`}>
      <b>{score}</b>
      {grade && <small>Grade {grade}</small>}
    </span>
  );
}
