export type Card = {
  value: number | null;
  previous: number | null;
  change: number | null;
  series: number[];
};

export type TopCandidate = {
  id: string;
  project_id: string;
  project_title: string;
  name: string;
  file_name: string;
  score: string;
  grade: string;
  stage: string;
  rank: number;
  ats_score: number | null;
};

export type Counts = {
  projects: number;
  scored: number;
  shortlisted: number;
  interviewed: number;
  on_hold: number;
  selected: number;
  rejected: number;
};

export type DashboardData = {
  refresh_seconds: number;
  days: number;
  choices: number[];
  counts: Counts;
  recommendations: { total: number; parts: { label: string; count: number }[] };
  projects: { not_started: number; in_progress: number; ready: number };
  screening: { uploaded: number; scored: number; percent: number | null };
  top: TopCandidate[];
  project_rows: ProjectRow[];
  attention: AttentionItem[];
  uploads_per_day: { start: string; values: number[] };
  flag_split: { flag: string; count: number }[];
  missed_requirements: MissedRequirement[];
};

export type ProjectRow = {
  id: string;
  title: string;
  cvs: number;
  failed: number;
  capacity: number;
  scored: number;
  best_score: number | null;
  average_score: number | null;
  ats_average: number | null;
  shortlisted: number;
  interviewed: number;
  selected: number;
  updated_at: string;
};

export type AttentionItem = {
  id: string;
  title: string;
  capacity: number;
  reason: "failed" | "almost_full" | "none_scored";
  count: number;
};

export type MissedRequirement = {
  requirement: string;
  kind: "must" | "nice";
  project_id: string;
  project_title: string;
  missing: number;
  judged: number;
};

/** The words for a period: "today" or "the last 7 days". */
export const periodWords = (days: number) => (days === 1 ? "today" : `the last ${days} days`);
