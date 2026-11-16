export type Verdict = "met" | "partly_met" | "missing";
export type Requirement = { id: string; text: string; kind: "must" | "nice"; weight: number };
export type Cell = {
  verdict: Verdict | null;
  outdated: boolean;
  evidence?: string;
  confidence?: string | null;
};
type Counts = Record<Verdict | "not_judged", number>;
export type Compared = {
  id: string;
  file_name: string;
  name: string;
  stage: string;
  score: string | null;
  grade: string | null;
  outdated: boolean;
  label: "strong_match" | "possible" | "not_recommended" | null;
  borderline: boolean;
  ats_score: number | null;
  must_score: string | null;
  nice_score: string | null;
  capped: boolean;
  summary: { must: Counts; nice: Counts };
  results: Cell[];
};
export type Fact =
  | { kind: "lead"; candidate: string; over: string; points: number }
  | { kind: "tie"; candidates: string[] }
  | { kind: "must_gap"; candidate: string; requirements: string[] }
  | { kind: "best_on"; candidate: string; requirements: string[] };
export type SideBySideBody = {
  requirements: Requirement[];
  candidates: Compared[];
  insights: Fact[];
  points: Record<Verdict, number>;
};

/** Each candidate keeps one colour on the page: its card, its bars and its dot on the chart. */
export const CANDIDATE_COLOURS = ["green", "violet", "blue", "amber"] as const;
export type CandidateColour = (typeof CANDIDATE_COLOURS)[number];
export const colourOf = (index: number): CandidateColour =>
  CANDIDATE_COLOURS[index % CANDIDATE_COLOURS.length];

export const displayName = (item: { name: string; file_name: string }) =>
  item.name || item.file_name;

export const VERDICT_WORDS: Record<Verdict, string> = {
  met: "Met",
  partly_met: "Partly met",
  missing: "Missing",
};
export const LABEL_WORDS = {
  strong_match: "Strong match",
  possible: "Possible",
  not_recommended: "Not recommended",
};
