"use client";

import { CandidateCards } from "@/components/company/comparison/CandidateCards";
import { CompareInsights } from "@/components/company/comparison/CompareInsights";
import { RequirementBars } from "@/components/company/comparison/RequirementBars";
import { TermLabel } from "@/components/company/comparison/terms";
import type { Compared, Requirement } from "@/components/company/comparison/types";
import { VerdictMark } from "@/components/company/comparison/VerdictMark";

const nothing = () => undefined;
const counts = { met: 0, partly_met: 0, missing: 0, not_judged: 0 };
const REQUIREMENTS: Requirement[] = [
  { id: "r1", text: "Python", kind: "must", weight: 5 },
  { id: "r2", text: "Docker", kind: "nice", weight: 2 },
];
const person = (
  id: string,
  name: string,
  score: string,
  verdicts: Compared["results"],
): Compared => ({
  id,
  file_name: `${id}.pdf`,
  name,
  stage: "shortlisted",
  score,
  grade: "A",
  outdated: false,
  label: "strong_match",
  borderline: false,
  ats_score: 90,
  must_score: "95.0",
  nice_score: "70.0",
  capped: false,
  summary: { must: counts, nice: counts },
  results: verdicts,
});
const CANDIDATES = [
  person("a", "A. H.", "94.5", [
    { verdict: "met", outdated: false, evidence: "Wrote Python daily", confidence: "high" },
    { verdict: "partly_met", outdated: false, evidence: "Used Docker once", confidence: "low" },
  ]),
  person("b", "D. O.", "91.0", [
    { verdict: "partly_met", outdated: false, evidence: "", confidence: "high" },
    { verdict: null, outdated: false, evidence: "", confidence: null },
  ]),
];

/** The building blocks of the comparison pages with sample figures. */
export function ComparisonSample() {
  return (
    <div className="page-stack">
      <CandidateCards projectId="sample" candidates={CANDIDATES} />
      <CompareInsights
        facts={[{ kind: "lead", candidate: "a", over: "b", points: 3.5 }]}
        candidates={CANDIDATES}
        requirements={REQUIREMENTS}
      />
      <RequirementBars
        requirements={REQUIREMENTS}
        candidates={CANDIDATES}
        points={{ met: 100, partly_met: 50, missing: 0 }}
        onOpen={nothing}
      />
      <p>
        <TermLabel term="frontier">On the frontier</TermLabel>{" "}
        <VerdictMark cell={{ verdict: "met", outdated: false }} />{" "}
        <VerdictMark cell={{ verdict: "missing", outdated: true }} />{" "}
        <VerdictMark cell={{ verdict: null, outdated: false }} />
      </p>
    </div>
  );
}
