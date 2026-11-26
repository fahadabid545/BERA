import { deleteJson, getJson, postJson } from "@/lib/api";

/** The company agent's chats. They are kept on the server and shared by the company's people. */

export type CandidateCard = {
  candidate_id: string;
  project_id: string;
  project_title: string;
  name: string;
  email: string;
  phone: string;
  years_of_experience: number | null;
  score: string | null;
  grade: string | null;
  label: string | null;
  ats_score: number | null;
  stage: string;
};

export type AgentMessage = {
  role: "user" | "assistant";
  text: string;
  suggestions: string[];
  candidates: CandidateCard[];
  /** A refusal or a failure shown in the chat; the server never stores it. */
  problem?: boolean;
};

export type ChatSummary = { id: string; title: string; updated_at: string; mine: boolean };

export type AgentAnswer = {
  chat_id: string | null;
  answer: string;
  refused: boolean;
  suggestions: string[];
  candidates: CandidateCard[];
};

const BASE = "/api/company/assistant";

export function listChats() {
  return getJson<{ chats: ChatSummary[] }>(`${BASE}/chats/`);
}

export function openChat(id: string) {
  return getJson<{ id: string; title: string; messages: AgentMessage[] }>(`${BASE}/chats/${id}/`);
}

export function deleteChat(id: string) {
  return deleteJson<{ deleted: boolean }>(`${BASE}/chats/${id}/`);
}

export function askAgent(body: {
  question: string;
  chat_id?: string | null;
  incognito?: boolean;
  history?: { role: string; text: string }[];
  shown?: string[];
}) {
  return postJson<AgentAnswer>(`${BASE}/ask/`, body);
}

/** How the server names a candidate inside an answer: "c_" and the first eight letters of the id. */
export function referenceOf(candidateId: string) {
  return `c_${candidateId.replace(/-/g, "").slice(0, 8)}`;
}
