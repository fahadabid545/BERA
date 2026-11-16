"use client";

import { useEffect, useState } from "react";

import { ChartMark, TipLines } from "@/components/charts/ChartTip";
import { Button, Table, TextLink } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";
import { startLive } from "@/lib/live";

import { ParetoFrontier } from "./ParetoFrontier";
import { TermLabel } from "./terms";
import { VerdictMark } from "./VerdictMark";
import { displayName, type Cell, type Requirement } from "./types";

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

/** Every candidate that passes the list's filters against every requirement, best first. New
 * candidates join without a reload. Each verdict can be hovered for its meaning. */
export function Matrix({ projectId, filterQuery }: { projectId: string; filterQuery: string }) {
  const [pageOf, setPageOf] = useState({ filterQuery, page: 1 });
  const page = pageOf.filterQuery === filterQuery ? pageOf.page : 1;
  const [shown, setShown] = useState<MatrixBody | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    const query = `?page=${page}${filterQuery && `&${filterQuery}`}`;
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
      <ParetoFrontier projectId={projectId} />
      {shown.count === 0 ? (
        <p role="status">No candidates to compare.</p>
      ) : (
        <>
          <Table label="Candidates against requirements">
            <thead>
              <tr>
                <th scope="col">Rank</th>
                <th scope="col">Candidate</th>
                <th scope="col">
                  <TermLabel term="ai_score">AI score</TermLabel>
                </th>
                {shown.requirements.map((requirement) => (
                  <th key={requirement.id} scope="col">
                    <ChartMark
                      as="span"
                      tip={
                        <TipLines
                          title={requirement.text}
                          lines={[
                            requirement.kind === "must" ? "Must-have" : "Nice-to-have",
                            `Weight ${requirement.weight}`,
                          ]}
                        />
                      }
                    >
                      {requirement.text}
                    </ChartMark>
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
                      <VerdictMark cell={cell} />
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
