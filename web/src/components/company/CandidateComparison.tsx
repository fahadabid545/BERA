"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, Table, Tag, TextLink } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";
import { startLive } from "@/lib/live";

import { FILTER_KEYS } from "./CandidateFilters";
import { stageLabel } from "./stages";

type Verdict = "met" | "partly_met" | "missing";
type Requirement = { id: string; text: string; kind: "must" | "nice"; weight: number };
type Cell = { verdict: Verdict | null; outdated: boolean; evidence?: string };
type Compared = {
  id: string;
  file_name: string;
  name: string;
  stage: string;
  score: string | null;
  grade: string | null;
  outdated: boolean;
  label: "strong_match" | "possible" | "not_recommended" | null;
  borderline: boolean;
  ats_score: number | null;
  results: Cell[];
};
type SideBySideBody = { requirements: Requirement[]; candidates: Compared[] };
type MatrixBody = {
  page: number;
  pages: number;
  count: number;
  refresh_seconds: number;
  requirements: Requirement[];
  rows: {
    candidate_id: string;
    file_name: string;
    name: string;
    rank: number | null;
    score: string | null;
    grade: string | null;
    cells: Cell[];
  }[];
};

const VERDICTS: Record<Verdict, string> = {
  met: "Met",
  partly_met: "Partly met",
  missing: "Missing",
};
const LABELS = {
  strong_match: "Strong match",
  possible: "Possible",
  not_recommended: "Not recommended",
};

function Verdicts({ cell }: { cell: Cell }) {
  return (
    <>
      {cell.verdict ? VERDICTS[cell.verdict] : <Tag variant="warning">Not judged</Tag>}{" "}
      {cell.verdict && cell.outdated && <Tag variant="warning">Outdated</Tag>}
    </>
  );
}

/** Candidates compared: with `ids` in the address, those candidates side by side; without, the
 * matrix of every candidate that passes the list's filters against every requirement. */
export function CandidateComparison({ projectId }: { projectId: string }) {
  const searchParams = useSearchParams();
  const ids = searchParams.get("ids");
  const filters = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    const value = searchParams.get(key);
    if (value) filters.set(key, value);
  }
  return ids ? (
    <SideBySide projectId={projectId} ids={ids} />
  ) : (
    <Matrix projectId={projectId} filterQuery={filters.toString()} />
  );
}

function SideBySide({ projectId, ids }: { projectId: string; ids: string }) {
  const [shown, setShown] = useState<SideBySideBody | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    let stopped = false;
    void getJson<SideBySideBody>(`/api/company/projects/${projectId}/compare/?ids=${ids}`).then(
      (result) => {
        if (stopped) return;
        if (result.ok) setShown(result.data);
        else setError(result.error);
      },
    );
    return () => {
      stopped = true;
    };
  }, [projectId, ids]);

  if (error) {
    return (
      <div className="page-stack">
        <p className="ui-error" role="alert">
          {error.message}
        </p>
        <TextLink href={`/company/projects/${projectId}/candidates`}>Back to candidates</TextLink>
      </div>
    );
  }
  if (!shown) return null;
  return (
    <div className="page-stack">
      <TextLink href={`/company/projects/${projectId}/candidates`}>Back to candidates</TextLink>
      <Table label="Side by side">
        <thead>
          <tr>
            <th scope="col">Candidate</th>
            {shown.candidates.map((item) => (
              <th key={item.id} scope="col">
                <TextLink href={`/company/projects/${projectId}/candidates/${item.id}`}>
                  {item.file_name}
                </TextLink>
                {item.name && <div>{item.name}</div>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">AI score</th>
            {shown.candidates.map((item) => (
              <td key={item.id}>
                {item.score ? `${item.score} (${item.grade})` : "Not scored"}{" "}
                {item.outdated && <Tag variant="warning">Outdated</Tag>}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">ATS score</th>
            {shown.candidates.map((item) => (
              <td key={item.id}>{item.ats_score}</td>
            ))}
          </tr>
          <tr>
            <th scope="row">Recommendation</th>
            {shown.candidates.map((item) => (
              <td key={item.id}>
                {item.label && LABELS[item.label]}{" "}
                {item.borderline && <Tag variant="neutral">Borderline</Tag>}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">Stage</th>
            {shown.candidates.map((item) => (
              <td key={item.id}>{stageLabel(item.stage)}</td>
            ))}
          </tr>
          {shown.requirements.map((requirement, index) => (
            <tr key={requirement.id}>
              <th scope="row">
                {requirement.text}{" "}
                <Tag variant="neutral">
                  {requirement.kind === "must" ? "Must-have" : "Nice-to-have"}
                </Tag>
              </th>
              {shown.candidates.map((item) => (
                <td key={item.id}>
                  <Verdicts cell={item.results[index]} />
                  {item.results[index].evidence && <div>“{item.results[index].evidence}”</div>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}

function Matrix({ projectId, filterQuery }: { projectId: string; filterQuery: string }) {
  const [pageOf, setPageOf] = useState({ filterQuery, page: 1 });
  const page = pageOf.filterQuery === filterQuery ? pageOf.page : 1;
  const [shown, setShown] = useState<MatrixBody | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    const query = `?page=${page}${filterQuery && `&${filterQuery}`}`;
    // New candidates join the matrix without a reload.
    return startLive(
      () => getJson<MatrixBody>(`/api/company/projects/${projectId}/matrix/${query}`),
      (result) => {
        if (result.ok) {
          setShown(result.data);
          setError(null);
        } else setError(result.error);
      },
    );
  }, [projectId, page, filterQuery]);

  if (error) {
    return (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    );
  }
  if (!shown) return null;
  const goTo = (next: number) => setPageOf({ filterQuery, page: next });
  return (
    <div className="page-stack">
      <TextLink href={`/company/projects/${projectId}/candidates`}>Back to candidates</TextLink>
      {shown.count === 0 ? (
        <p role="status">No candidates to compare.</p>
      ) : (
        <>
          <Table label="Candidates against requirements">
            <thead>
              <tr>
                <th scope="col">Rank</th>
                <th scope="col">Candidate</th>
                <th scope="col">AI score</th>
                {shown.requirements.map((requirement) => (
                  <th key={requirement.id} scope="col">
                    {requirement.text}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.rows.map((row) => (
                <tr key={row.candidate_id}>
                  <td>{row.rank}</td>
                  <td>
                    <TextLink
                      href={`/company/projects/${projectId}/candidates/${row.candidate_id}`}
                    >
                      {row.file_name}
                    </TextLink>
                    {row.name && <div>{row.name}</div>}
                  </td>
                  <td>{row.score ? `${row.score} (${row.grade})` : "Not scored"}</td>
                  {row.cells.map((cell, index) => (
                    <td key={shown.requirements[index].id}>
                      <Verdicts cell={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </Table>
          <div className="page-actions">
            <Button
              variant="secondary"
              disabled={shown.page <= 1}
              onClick={() => goTo(shown.page - 1)}
            >
              Previous page
            </Button>
            <span>
              Page {shown.page} of {shown.pages}, {shown.count} candidates
            </span>
            <Button
              variant="secondary"
              disabled={shown.page >= shown.pages}
              onClick={() => goTo(shown.page + 1)}
            >
              Next page
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
