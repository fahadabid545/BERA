"use client";

import { useEffect, useState } from "react";

import { ChartCard } from "@/components/charts/ChartCard";
import { Table, Tag, TextLink } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

import { CandidateCards } from "./CandidateCards";
import { CompareInsights } from "./CompareInsights";
import { EvidencePopup, type Evidence } from "./EvidencePopup";
import { ParetoFrontier } from "./ParetoFrontier";
import { RequirementBars } from "./RequirementBars";
import { TermLabel } from "./terms";
import { VerdictMark } from "./VerdictMark";
import { colourOf, displayName, type SideBySideBody } from "./types";

/** The chosen candidates next to each other: who they are, what stands out, requirement by
 * requirement, where they sit among all candidates, and the words behind every verdict. */
export function SideBySide({ projectId, ids }: { projectId: string; ids: string }) {
  const [shown, setShown] = useState<SideBySideBody | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [open, setOpen] = useState<Evidence | null>(null);
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

  const back = (
    <TextLink href={`/company/projects/${projectId}/candidates`}>Back to candidates</TextLink>
  );
  if (error) {
    return (
      <div className="page-stack">
        <p className="ui-error" role="alert">
          {error.message}
        </p>
        {back}
      </div>
    );
  }
  if (!shown) return null;
  const chosen = Object.fromEntries(
    shown.candidates.map((item, index) => [item.id, colourOf(index)]),
  );
  return (
    <div className="page-stack">
      {back}
      <EvidencePopup projectId={projectId} selection={open} onClose={() => setOpen(null)} />
      <CandidateCards projectId={projectId} candidates={shown.candidates} />
      <CompareInsights
        facts={shown.insights}
        candidates={shown.candidates}
        requirements={shown.requirements}
      />
      {shown.requirements.length > 0 && (
        <ChartCard title="Requirement by requirement">
          <RequirementBars
            requirements={shown.requirements}
            candidates={shown.candidates}
            points={shown.points}
            onOpen={setOpen}
          />
        </ChartCard>
      )}
      <ParetoFrontier projectId={projectId} chosen={chosen} />
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
            <th scope="row">
              <TermLabel term="ai_score">AI score</TermLabel>
            </th>
            {shown.candidates.map((item) => (
              <td key={item.id}>
                {item.score ? `${item.score} (${item.grade})` : "Not scored"}{" "}
                {item.outdated && <Tag variant="warning">Outdated</Tag>}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">
              <TermLabel term="ats_score">ATS score</TermLabel>
            </th>
            {shown.candidates.map((item) => (
              <td key={item.id}>{item.ats_score}</td>
            ))}
          </tr>
          <tr>
            <th scope="row">
              <TermLabel term="recommendation">Recommendation</TermLabel>
            </th>
            {shown.candidates.map((item) => (
              <td key={item.id}>
                {item.label &&
                  {
                    strong_match: "Strong match",
                    possible: "Possible",
                    not_recommended: "Not recommended",
                  }[item.label]}{" "}
                {item.borderline && <Tag variant="neutral">Borderline</Tag>}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">Stage</th>
            {shown.candidates.map((item) => (
              <td key={item.id}>{item.stage}</td>
            ))}
          </tr>
          {shown.requirements.map((requirement, index) => (
            <tr key={requirement.id}>
              <th scope="row">
                {requirement.text}{" "}
                <TermLabel term={requirement.kind}>
                  <Tag variant="neutral">
                    {requirement.kind === "must" ? "Must-have" : "Nice-to-have"}
                  </Tag>
                </TermLabel>
              </th>
              {shown.candidates.map((item) => (
                <td key={item.id}>
                  <button
                    type="button"
                    className="verdict-button"
                    aria-label={`${displayName(item)}: ${requirement.text}`}
                    onClick={() =>
                      setOpen({ candidate: item, requirement, cell: item.results[index] })
                    }
                  >
                    <VerdictMark cell={item.results[index]} />
                  </button>
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
