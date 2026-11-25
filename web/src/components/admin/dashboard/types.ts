import type { TrendData } from "@/components/charts/TrendCard";

export type Card = {
  value: number | null;
  previous: number | null;
  change: number | null;
  series: number[];
};

export type CompanyRow = {
  type: "company";
  id: string;
  name: string;
  country: string;
  status: string;
  plan: string | null;
  state: string;
  cvs_scored?: number;
  tokens?: number;
  cost?: number;
  created_at?: string;
};

export type AdminData = {
  refresh_seconds: number;
  role: "super" | "support";
  days: number;
  choices: number[];
  cards: { companies: Card; cvs_scored: Card; ai_cost?: Card };
  totals: { companies: number; suspended: number; paying: number };
  usage: { trend: TrendData; top_companies: CompanyRow[] };
  pending: {
    past_due: number;
    grants_expiring: number;
    suspended: number;
    failed_ai_calls?: number;
    failed_jobs?: number;
    data_requests?: number;
    feedback?: number;
  };
  recent: CompanyRow[];
  /** Only a super admin gets these two. */
  revenue?: {
    received: number;
    ai_cost: number;
    margin_days: number;
    margin_percent: number | null;
    plans: { id: number; name: string; subscribers: number; received: number; share: number }[];
    states: Record<string, number>;
    history: { month: string; received: number; ai_cost: number; margin_percent: number | null }[];
  };
  ai?: {
    calls: { total: number; failed: number; failure_percent: number | null };
    by_purpose: { purpose: string; count: number }[];
    by_model: { model: string; calls: number; tokens: number; cost: number }[];
    tokens: { used: number; cap: number; percent: number | null; days: number };
    control: { paused: boolean; paused_by_admin: boolean; paused_automatically: boolean };
  };
};

export const STATE_WORDS: Record<string, string> = {
  no_plan: "No plan",
  active: "Active",
  past_due: "Past due",
  cancelled: "Cancelled",
  expired: "Expired",
  granted_free: "Free grant",
};
export const PURPOSE_WORDS: Record<string, string> = {
  reading: "Reading",
  scoring: "Scoring",
  requirement_extraction: "Requirement extraction",
  playground: "Playground",
};

const USD_FRACTION = 2;
export const usd = (value: number) =>
  value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value >= 1000 ? 0 : USD_FRACTION,
    maximumFractionDigits: value >= 1000 ? 0 : USD_FRACTION,
  });
export const whole = (value: number) => value.toLocaleString("en-US");
