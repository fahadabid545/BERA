"use client";

import { useEffect, useState } from "react";

import { Button, Table, Tag, TextLink, type TagVariant } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

import type { Filters, RequirementChoice } from "./CandidateFilters";

type SortKey = "rank" | "candidate" | "score" | "ats" | "label" | "stage" | "added";
type Direction = "asc" | "desc";
type Row = {
  id: string;
  candidate_id: string | null;
  file_name: string;
  name: string;
  status: string;
  reason: string;
  rank: number | null;
  score: string | null;
  grade: string | null;
  outdated: boolean;
  ats_score: number | null;
  label: "strong_match" | "possible" | "not_recommended" | null;
  borderline: boolean;
  stage: string | null;
  added_at: string;
};
type Page = {
  page: number;
  pages: number;
  count: number;
  filtered: boolean;
  requirements: RequirementChoice[];
  refresh_seconds: number;
  rows: Row[];
};

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "rank", label: "Rank" },
  { key: "candidate", label: "Candidate" },
  { key: "score", label: "AI score" },
  { key: "ats", label: "ATS score" },
  { key: "label", label: "Recommendation" },
  { key: "stage", label: "Stage" },
  { key: "added", label: "Date added" },
];
const NEWEST_OR_BEST_FIRST: SortKey[] = ["score", "ats", "added"];
const LABELS = {
  strong_match: "Strong match",
  possible: "Possible",
  not_recommended: "Not recommended",
};
const STATUSES: Record<string, { label: string; variant: TagVariant }> = {
  awaiting_confirmation: { label: "Awaiting confirmation", variant: "neutral" },
  waiting: { label: "Waiting", variant: "neutral" },
  reading: { label: "Reading", variant: "live" },
  scoring: { label: "Scoring", variant: "live" },
  done: { label: "Done", variant: "neutral" },
  failed: { label: "Failed", variant: "danger" },
};
const MILLISECONDS = 1000;
const DATE_LENGTH = 10;
const firstDirection = (key: SortKey): Direction =>
  NEWEST_OR_BEST_FIRST.includes(key) ? "desc" : "asc";

/** The project's candidates, best first. The server sorts and pages; this looks again every few
 * seconds, so a CV that finishes appears and takes its rank on its own. Items still on their way
 * show their status instead of a score and stay at the bottom. */
export function CandidateList({
  projectId,
  filters = {},
  onClearAll,
  onRequirements,
}: {
  projectId: string;
  filters?: Filters;
  onClearAll?: () => void;
  onRequirements?: (requirements: RequirementChoice[]) => void;
}) {
  const base = `/api/company/projects/${projectId}/candidates/`;
  const [sort, setSort] = useState<SortKey>("score");
  const [direction, setDirection] = useState<Direction>("desc");
  const filterQuery = new URLSearchParams(filters).toString();
  // A change of filters starts again at the first page.
  const [pageOf, setPageOf] = useState({ filterQuery, page: 1 });
  const page = pageOf.filterQuery === filterQuery ? pageOf.page : 1;
  const setPage = (next: number) => setPageOf({ filterQuery, page: next });
  const [shown, setShown] = useState<Page | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;
    const load = async () => {
      const query = `?sort=${sort}&direction=${direction}&page=${page}${filterQuery && `&${filterQuery}`}`;
      const result = await getJson<Page>(`${base}${query}`);
      if (stopped) return;
      if (result.ok) {
        setShown(result.data);
        onRequirements?.(result.data.requirements ?? []);
        setError(null);
        timer = setTimeout(load, result.data.refresh_seconds * MILLISECONDS);
      } else setError(result.error);
    };
    void load();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [base, sort, direction, page, filterQuery, onRequirements]);

  function sortBy(key: SortKey) {
    setPage(1);
    if (key === sort) return setDirection(direction === "asc" ? "desc" : "asc");
    setSort(key);
    setDirection(firstDirection(key));
  }

  if (!shown) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  if (shown.count === 0) {
    return shown.filtered ? (
      <div className="page-stack">
        <p role="status">No candidates match these filters.</p>
        <div className="page-actions">
          <Button variant="secondary" onClick={onClearAll}>
            Clear all
          </Button>
        </div>
      </div>
    ) : null;
  }
  return (
    <div className="page-stack">
      <Table label="Candidates">
        <thead>
          <tr>
            {COLUMNS.map(({ key, label }) => (
              <th
                key={key}
                scope="col"
                aria-sort={
                  key === sort ? (direction === "asc" ? "ascending" : "descending") : undefined
                }
              >
                <button type="button" className="ui-table__sort" onClick={() => sortBy(key)}>
                  {label}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.rows.map((row) => (
            <CandidateRow key={row.id} row={row} projectId={projectId} />
          ))}
        </tbody>
      </Table>
      <div className="page-actions">
        <Button
          variant="secondary"
          disabled={shown.page <= 1}
          onClick={() => setPage(shown.page - 1)}
        >
          Previous page
        </Button>
        <span>
          Page {shown.page} of {shown.pages}, {shown.count} candidates
        </span>
        <Button
          variant="secondary"
          disabled={shown.page >= shown.pages}
          onClick={() => setPage(shown.page + 1)}
        >
          Next page
        </Button>
      </div>
    </div>
  );
}

function CandidateRow({ row, projectId }: { row: Row; projectId: string }) {
  const status = STATUSES[row.status] ?? { label: row.status, variant: "neutral" as TagVariant };
  return (
    <tr>
      <td>{row.rank}</td>
      <td>
        {row.candidate_id ? (
          <TextLink href={`/company/projects/${projectId}/candidates/${row.candidate_id}`}>
            {row.file_name}
          </TextLink>
        ) : (
          row.file_name
        )}
        {row.name && <div>{row.name}</div>}
      </td>
      <td>
        {row.score ? (
          <>
            {row.score} ({row.grade}) {row.outdated && <Tag variant="warning">Outdated</Tag>}
          </>
        ) : (
          <>
            <Tag variant={status.variant}>{status.label}</Tag>
            {row.reason && <div>{row.reason}</div>}
          </>
        )}
      </td>
      <td>{row.ats_score}</td>
      <td>
        {row.label && LABELS[row.label]} {row.borderline && <Tag variant="neutral">Borderline</Tag>}
      </td>
      <td>{row.stage && "New"}</td>
      <td>{row.added_at.slice(0, DATE_LENGTH)}</td>
    </tr>
  );
}
