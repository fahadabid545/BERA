import type { ReactNode } from "react";

import { Tooltip } from "@/components/ui";

/** What each word on the comparison pages means, shown on hover and keyboard focus. */
export const TERMS = {
  ai_score:
    "How well the CV meets the project's requirements, from 0 to 100. Must-haves count for more.",
  ats_score: "How easily an applicant tracking system can read the CV, from 0 to 100.",
  must_score: "The score for the must-have requirements alone, from 0 to 100.",
  nice_score: "The score for the nice-to-have requirements alone, from 0 to 100.",
  grade: "The band the AI score falls in. A is the best.",
  recommendation: "Strong match, possible or not recommended, set from the AI score.",
  must: "Must-have: the CV has to show this. A missing one can cap the score.",
  nice: "Nice-to-have: it adds to the score but is not required.",
  met: "The CV clearly shows it.",
  partly_met: "The CV shows part of it.",
  missing: "The CV does not show it.",
  not_judged: "The CV has not been judged against this requirement yet.",
  outdated: "The requirement was edited after the CV was judged against it.",
  frontier:
    "On the frontier: no other candidate is higher on both scores. Everyone else has someone better on both.",
} as const;

export type Term = keyof typeof TERMS;

/** A word with its meaning on hover. It is focusable, so the meaning is reachable by keyboard. */
export function TermLabel({ term, children }: { term: Term; children: ReactNode }) {
  return (
    <Tooltip content={TERMS[term]}>
      <span className="term" tabIndex={0}>
        {children}
      </span>
    </Tooltip>
  );
}
