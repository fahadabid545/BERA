"use client";

import { useEffect, useState } from "react";

import {
  Button,
  Checkbox,
  Dialog,
  Select,
  Table,
  Tag,
  TextLink,
  type TagVariant,
} from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";
import { startLive } from "@/lib/live";

import type { Filters, RequirementChoice } from "./CandidateFilters";
import { STAGES, stageLabel } from "./stages";

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
  top: boolean;
  added_at: string;
};
type Page = {
  page: number;
  pages: number;
  count: number;
  filtered: boolean;
  requirements: RequirementChoice[];
  compare_limits?: { min: number; max: number };
  top?: { n: number; included: number; tied: boolean };
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
  onCompare,
  onDownload,
}: {
  projectId: string;
  filters?: Filters;
  onClearAll?: () => void;
  onRequirements?: (requirements: RequirementChoice[]) => void;
  onCompare?: (candidateIds: string[]) => void;
  onDownload?: (candidateIds: string[]) => void;
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
  const [selected, setSelected] = useState<string[]>([]);
  const [targetStage, setTargetStage] = useState(STAGES[1].value);
  const [confirming, setConfirming] = useState(false);
  const [changeError, setChangeError] = useState<ApiError | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const query = `?sort=${sort}&direction=${direction}&page=${page}${filterQuery && `&${filterQuery}`}`;
    return startLive(
      () => getJson<Page>(`${base}${query}`),
      (result) => {
        if (result.ok) {
          setShown(result.data);
          onRequirements?.(result.data.requirements ?? []);
          setError(null);
        } else setError(result.error);
      },
    );
  }, [base, sort, direction, page, filterQuery, onRequirements, version]);

  function sortBy(key: SortKey) {
    setPage(1);
    if (key === sort) return setDirection(direction === "asc" ? "desc" : "asc");
    setSort(key);
    setDirection(firstDirection(key));
  }

  async function applyStage() {
    const result = await postJson(`${base}stage/`, {
      candidate_ids: selected,
      stage: targetStage,
    });
    if (result.ok) {
      setSelected([]);
      setChangeError(null);
      setVersion((current) => current + 1);
    } else setChangeError(result.error);
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
  const selectable = shown.rows.filter((row) => row.candidate_id).map((row) => row.candidate_id!);
  const allSelected = selectable.length > 0 && selectable.every((id) => selected.includes(id));
  const toggle = (id: string, on: boolean) =>
    setSelected((current) => (on ? [...current, id] : current.filter((item) => item !== id)));
  const limits = shown.compare_limits ?? { min: 2, max: 4 };
  const tooManyToCompare = selected.length > limits.max;
  return (
    <div className="page-stack">
      <div className="page-actions">
        <Button
          variant="secondary"
          disabled={selected.length < limits.min || tooManyToCompare}
          onClick={() => onCompare?.(selected)}
        >
          Compare
        </Button>
        <Button
          variant="secondary"
          disabled={selected.length === 0}
          onClick={() => onDownload?.(selected)}
        >
          Download selected
        </Button>
        <Select
          label="Move selected to"
          value={targetStage}
          onChange={(event) => setTargetStage(event.target.value)}
          options={STAGES}
        />
        <Dialog
          open={confirming}
          onOpenChange={setConfirming}
          trigger={
            <Button variant="secondary" disabled={selected.length === 0}>
              Change stage
            </Button>
          }
          title="Change stage"
          description={`Move ${selected.length} ${
            selected.length === 1 ? "candidate" : "candidates"
          } to ${stageLabel(targetStage)}?`}
          confirmLabel="Change stage"
          onConfirm={() => void applyStage()}
        />
      </div>
      {shown.top?.tied && (
        <p role="status">
          The top {shown.top.n} shows {shown.top.included} candidates because of a tie at the
          cut-off score.
        </p>
      )}
      {tooManyToCompare && (
        <p role="status">You can compare up to {limits.max} candidates at a time. Choose fewer.</p>
      )}
      {changeError && (
        <p className="ui-error" role="alert">
          {changeError.message}
        </p>
      )}
      <Table label="Candidates">
        <thead>
          <tr>
            <th scope="col">
              <Checkbox
                label={<span className="visually-hidden">Select all on this page</span>}
                checked={allSelected}
                disabled={selectable.length === 0}
                onChange={(event) =>
                  setSelected((current) => [
                    ...current.filter((id) => !selectable.includes(id)),
                    ...(event.target.checked ? selectable : []),
                  ])
                }
              />
            </th>
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
            <CandidateRow
              key={row.id}
              row={row}
              projectId={projectId}
              checked={row.candidate_id ? selected.includes(row.candidate_id) : false}
              onToggle={toggle}
            />
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

function CandidateRow({
  row,
  projectId,
  checked,
  onToggle,
}: {
  row: Row;
  projectId: string;
  checked: boolean;
  onToggle: (id: string, on: boolean) => void;
}) {
  const status = STATUSES[row.status] ?? { label: row.status, variant: "neutral" as TagVariant };
  return (
    <tr>
      <td>
        {row.candidate_id && (
          <Checkbox
            label={<span className="visually-hidden">Select {row.file_name}</span>}
            checked={checked}
            onChange={(event) => onToggle(row.candidate_id!, event.target.checked)}
          />
        )}
      </td>
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
        {row.top && <Tag variant="success">Top</Tag>}
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
      <td>{stageLabel(row.stage)}</td>
      <td>{row.added_at.slice(0, DATE_LENGTH)}</td>
    </tr>
  );
}
