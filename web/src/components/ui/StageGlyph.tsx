export type StageName = "new" | "shortlisted" | "interviewed" | "on_hold" | "selected" | "rejected";

const BOX = { x: 1.8, y: 1.8, width: 12.4, height: 12.4, rx: 4.2 };

/** Same family as ResultGlyph: the fill level tells how far the candidate has come. */
export function StageGlyph({ stage, size = 13 }: { stage: StageName; size?: number }) {
  const partial = stage === "shortlisted" || stage === "interviewed";
  return (
    <svg
      className={`ui-glyph ui-glyph--stage-${stage}`}
      width={size}
      height={size}
      viewBox="0 0 16 16"
      aria-hidden="true"
      focusable="false"
    >
      {stage === "new" && <rect {...BOX} className="ui-glyph__line ui-glyph__line--dashed" />}
      {partial && (
        <>
          <clipPath id={`ui-glyph-${stage}`}>
            {stage === "shortlisted" ? (
              <path d="M0 0h16L0 16z" />
            ) : (
              <rect x="0" y="0" width="8" height="16" />
            )}
          </clipPath>
          <rect {...BOX} className="ui-glyph__line" />
          <rect {...BOX} className="ui-glyph__fill" clipPath={`url(#ui-glyph-${stage})`} />
        </>
      )}
      {stage === "on_hold" && (
        <>
          <rect {...BOX} className="ui-glyph__fill" />
          <path d="M6.2 5.6v4.8M9.8 5.6v4.8" className="ui-glyph__mark" />
        </>
      )}
      {stage === "selected" && (
        <>
          <rect {...BOX} className="ui-glyph__fill" />
          <path d="M5 8.3l2.2 2.2 3.9-4.6" className="ui-glyph__mark" />
        </>
      )}
      {stage === "rejected" && (
        <>
          <rect {...BOX} className="ui-glyph__fill" />
          <path d="M5.6 10.4l4.8-4.8" className="ui-glyph__mark" />
        </>
      )}
    </svg>
  );
}
