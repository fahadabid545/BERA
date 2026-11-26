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
};

/** The words for a period: "today" or "the last 7 days". */
export const periodWords = (days: number) => (days === 1 ? "today" : `the last ${days} days`);
