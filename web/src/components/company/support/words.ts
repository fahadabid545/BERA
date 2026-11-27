import type { TagVariant } from "@/components/ui";

export type TicketStatus = "open" | "working" | "needs_reply" | "completed" | "closed";
export type TicketCategory = "bug" | "billing" | "how_to" | "account" | "other";

export const STATUS_WORDS: Record<TicketStatus, string> = {
  open: "Open",
  working: "Working on it",
  needs_reply: "Waiting for your reply",
  completed: "Completed",
  closed: "Closed",
};
/** Tags also differ by their words, never by colour alone. */
export const STATUS_TAGS: Record<TicketStatus, TagVariant> = {
  open: "warning",
  working: "live",
  needs_reply: "danger",
  completed: "success",
  closed: "neutral",
};
export const CATEGORY_WORDS: Record<TicketCategory, string> = {
  bug: "Bug",
  billing: "Billing",
  how_to: "How to",
  account: "Account",
  other: "Other",
};

export const ticketNumber = (number: number) => `SUP-${number}`;

export type TicketSummary = {
  id: string;
  number: number;
  title: string;
  category: TicketCategory;
  status: TicketStatus;
  created_at: string;
  updated_at: string;
};

export type TicketMessage = {
  id: string;
  author: "user" | "admin" | "system";
  text: string;
  created_at: string;
};

export type TicketDetail = TicketSummary & {
  summary: string;
  what_happened: string;
  expected: string;
  steps: string;
  messages: TicketMessage[];
};

export const when = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  });
