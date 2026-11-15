"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ChartMark, TipLines } from "@/components/charts/ChartTip";
import { Button, ButtonLink, Card, Checkbox, Select, Tag, TextLink } from "@/components/ui";

import { stageLabel } from "../stages";
import type { DashboardData, TopCandidate } from "./types";

function Person({
  candidate,
  chosen,
  onToggle,
}: {
  candidate: TopCandidate;
  chosen: boolean;
  onToggle: () => void;
}) {
  const label = candidate.name || candidate.file_name;
  return (
    <li className="top-card">
      <ChartMark
        className="top-card__body"
        tip={
          <TipLines
            title={label}
            lines={[
              `Rank ${candidate.rank} in ${candidate.project_title}`,
              `AI score ${candidate.score}, grade ${candidate.grade}`,
              candidate.ats_score === null ? "No ATS score" : `ATS score ${candidate.ats_score}`,
              stageLabel(candidate.stage),
            ]}
          />
        }
      >
        <span className="top-card__rank">{candidate.rank}</span>
        <span className="top-card__name">
          <TextLink href={`/company/projects/${candidate.project_id}/candidates/${candidate.id}`}>
            {label}
          </TextLink>
        </span>
        <span className="top-card__score">
          {candidate.score} <Tag variant="neutral">Grade {candidate.grade}</Tag>
        </span>
        <span className="top-card__bar">
          <span style={{ width: `${Number(candidate.score)}%` }} />
        </span>
        <ul className="top-card__strengths">
          {candidate.strengths.map((strength) => (
            <li key={strength}>{strength}</li>
          ))}
        </ul>
        <Tag variant="neutral">{stageLabel(candidate.stage)}</Tag>
      </ChartMark>
      <Checkbox label="Compare" checked={chosen} onChange={onToggle} />
    </li>
  );
}

/** The best candidates of one project, side by side. Names open the candidate; the checkboxes
 * pick two to four of them for the comparison page, within the limits the server names. */
export function TopCandidates({
  top,
  onProject,
}: {
  top: DashboardData["top"];
  onProject: (id: string) => void;
}) {
  const router = useRouter();
  const [chosen, setChosen] = useState<string[]>([]);
  const { min, max } = top.compare_limits;
  const toggle = (id: string) =>
    setChosen((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  const ready = chosen.length >= min && chosen.length <= max;
  return (
    <Card className="ui-card top-candidates">
      <div className="chart-card__header">
        <h2>Top candidates</h2>
        <div className="chart-card__controls">
          {top.projects.length > 0 && (
            <Select
              label="Project"
              value={top.project_id ?? ""}
              onChange={(event) => {
                setChosen([]);
                onProject(event.target.value);
              }}
              options={top.projects.map((project) => ({ value: project.id, label: project.title }))}
            />
          )}
          <Button
            disabled={!ready}
            onClick={() =>
              router.push(`/company/projects/${top.project_id}/compare?ids=${chosen.join(",")}`)
            }
          >
            {`Compare selected (${chosen.length})`}
          </Button>
          {top.project_id && (
            <ButtonLink variant="secondary" href={`/company/projects/${top.project_id}/candidates`}>
              View all
            </ButtonLink>
          )}
        </div>
      </div>
      {top.candidates.length === 0 ? (
        <p role="status">No scored candidates yet.</p>
      ) : (
        <ul className="top-candidates__list">
          {top.candidates.map((candidate) => (
            <Person
              key={candidate.id}
              candidate={candidate}
              chosen={chosen.includes(candidate.id)}
              onToggle={() => toggle(candidate.id)}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}
