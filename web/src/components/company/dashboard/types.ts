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
  strengths: string[];
  ats_score: number | null;
};

export type ActivityEvent =
  | {
      kind: "scored" | "moved";
      id: string;
      project_id: string;
      project_title: string;
      name: string;
      file_name: string;
      score: string | null;
      to_stage?: string;
      at: string;
    }
  | {
      kind: "shared";
      id: string;
      project_id: string;
      project_title: string;
      views: number;
      at: string;
    };

export type DashboardData = {
  refresh_seconds: number;
  days: number;
  choices: number[];
  cards: {
    uploaded: Card;
    scored: Card;
    shortlisted: Card;
    average_score: Card;
  };
  insights: {
    hiring_pace: { current: number; previous: number; change: number | null };
    match_quality: { share: number | null; previous_share: number | null; change: number | null };
    time_to_shortlist: { hours: number | null; previous_hours: number | null };
  };
  recommendations: { total: number; parts: { label: string; count: number }[] };
  projects: { not_started: number; in_progress: number; ready: number };
  screening: { uploaded: number; scored: number; percent: number | null };
  top: {
    projects: { id: string; title: string }[];
    project_id: string | null;
    candidates: TopCandidate[];
    compare_limits: { min: number; max: number };
  };
  pending: { awaiting_confirmation: number; failed: number; links_expiring: number };
  activity: ActivityEvent[];
};

/** The words for a period: "today" or "the last 7 days". */
export const periodWords = (days: number) => (days === 1 ? "today" : `the last ${days} days`);
