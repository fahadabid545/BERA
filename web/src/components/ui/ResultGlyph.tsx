export type Result = "met" | "partly_met" | "missing" | "not_judged";

export const RESULT_WORDS: Record<Result, string> = {
  met: "Met",
  partly_met: "Partly met",
  missing: "Missing",
  not_judged: "Not judged",
};

const BOX = { x: 1.8, y: 1.8, width: 12.4, height: 12.4, rx: 4.2 };

/** One family of rounded squares, told apart by shape as well as colour. Always sits beside its word. */
export function ResultGlyph({ result, size = 14 }: { result: Result; size?: number }) {
  return (
    <svg
      className={`ui-glyph ui-glyph--${result}`}
      width={size}
      height={size}
      viewBox="0 0 16 16"
      aria-hidden="true"
      focusable="false"
    >
      {result === "met" && (
        <>
          <rect {...BOX} className="ui-glyph__fill" />
          <path d="M5 8.3l2.2 2.2 3.9-4.6" className="ui-glyph__mark" />
        </>
      )}
      {result === "partly_met" && (
        <>
          <clipPath id="ui-glyph-half">
            <path d="M0 16V0l16 16z" />
          </clipPath>
          <rect {...BOX} className="ui-glyph__line" />
          <rect {...BOX} className="ui-glyph__fill" clipPath="url(#ui-glyph-half)" />
        </>
      )}
      {result === "missing" && (
        <>
          <rect {...BOX} className="ui-glyph__line" />
          <path d="M5.2 8h5.6" className="ui-glyph__bar" />
        </>
      )}
      {result === "not_judged" && (
        <>
          <rect {...BOX} className="ui-glyph__line ui-glyph__line--dashed" />
          <rect x="7" y="7" width="2" height="2" rx=".6" className="ui-glyph__fill" />
        </>
      )}
    </svg>
  );
}
