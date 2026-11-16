import { Tag } from "@/components/ui";

import { TermLabel } from "./terms";
import { VERDICT_WORDS, type Cell } from "./types";

const VARIANTS = { met: "success", partly_met: "warning", missing: "danger" } as const;

/** A requirement's result in words, on a surface of its own: solid for met, warning for partly
 * met, danger for missing, plain for not judged yet. Hovering a word gives its meaning. */
export function VerdictMark({ cell }: { cell: Cell }) {
  return (
    <span className="verdict-mark">
      {cell.verdict ? (
        <TermLabel term={cell.verdict}>
          <Tag variant={VARIANTS[cell.verdict]}>{VERDICT_WORDS[cell.verdict]}</Tag>
        </TermLabel>
      ) : (
        <TermLabel term="not_judged">
          <Tag variant="neutral">Not judged</Tag>
        </TermLabel>
      )}
      {cell.verdict && cell.outdated && (
        <TermLabel term="outdated">
          <Tag variant="warning">Outdated</Tag>
        </TermLabel>
      )}
    </span>
  );
}
