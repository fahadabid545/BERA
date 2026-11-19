import { postJson } from "@/lib/api";

export type DownloadPackage = {
  id: string;
  /** Empty for the whole-company export. */
  project_id: string | null;
  status: "preparing" | "ready" | "failed" | "expired";
  files: number;
  size_bytes: number | null;
  created_at: string;
  expires_at: string | null;
  refresh_seconds: number;
};

/** Asks for the whole-company export: every project's CVs and ranked list in one zip. */
export function requestCompanyExport() {
  return postJson<DownloadPackage>("/api/company/downloads/export/", {});
}

/** Asks for a zip of CVs: every CV of the project, or those of the chosen candidates. */
export function requestPackage(
  projectId: string,
  choice: { all: true } | { candidates: string[] },
) {
  const body = "all" in choice ? { all: true } : { candidate_ids: choice.candidates };
  return postJson<DownloadPackage>(`/api/company/projects/${projectId}/downloads/`, body);
}

export const packagePage = (id: string) => `/company/downloads/${id}`;
