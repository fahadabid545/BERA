export type Kind = "beta" | "permitted";
export type Status = "active" | "ended" | "revoked";

export type Grant = {
  id: string;
  kind: Kind;
  status: Status;
  company: { id: string; name: string } | null;
  owner: { name: string; email: string } | null;
  invite: { id: number; label: string; kind: string };
  plan: { id: number; name: string } | null;
  started_at: string;
  ends_at: string | null;
  revoked_at: string | null;
};

export type Page<Item> = { total: number; page: number; page_size: number; items: Item[] };

export type Invite = {
  id: number;
  kind: "beta_email" | "beta_code" | "permitted_email";
  label: string;
  email: string | null;
  plan: { id: number; name: string } | null;
  access_days: number | null;
  max_uses: number | null;
  uses: number;
  redeem_until: string | null;
  enabled: boolean;
  created_at: string;
};

export type DailyCvs = { day: string; cvs: number }[];

export type Overview = {
  active: number;
  ended: number;
  revoked: number;
  feedback: number;
  daily_cvs: DailyCvs;
};

export type GrantDetail = Grant & {
  usage: {
    cvs_today: number;
    cvs_per_day_limit?: number;
    cvs_this_period: number;
    cvs_per_month_limit: number;
    tokens_in: number;
    tokens_out: number;
    estimated_cost: string;
    projects: number;
  };
  daily_cvs: DailyCvs;
  activity: { id: number; kind: string; actor_name: string; created_at: string }[];
  feedback: {
    id: string;
    kind: string;
    status: string;
    message: string;
    user: string;
    created_at: string;
  }[];
};

export type PaidRow = {
  id: string;
  name: string;
  plan_name: string | null;
  state: string;
  period_end: string | null;
  cvs_used: number;
  cvs_limit: number;
  users: number;
  also_free_access: Kind[];
};

export type Plan = { id: number; name: string; status: string };

export const BASE = "/api/admin/free-access/";
export const STATUS_TEXT: Record<Status, string> = {
  active: "Active",
  ended: "Ended",
  revoked: "Revoked",
};
export const KIND_TEXT: Record<Kind, string> = { beta: "Beta", permitted: "Permitted" };

export const day = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-US", { dateStyle: "medium", timeZone: "UTC" }) : "";

export const pagesOf = (page: Page<unknown>) => Math.max(1, Math.ceil(page.total / page.page_size));
