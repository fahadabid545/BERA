import { Table, Tag, TextLink } from "@/components/ui";

import { stageLabel } from "../stages";
import type { TopCandidate } from "./types";

/** The ten best candidates of the whole company: who, in which project, and both scores. */
export function TopCandidatesTable({ candidates }: { candidates: TopCandidate[] }) {
  if (candidates.length === 0) return <p role="status">No scored candidates yet.</p>;
  return (
    <Table label="Top candidates">
      <thead>
        <tr>
          <th scope="col">Rank</th>
          <th scope="col">Name</th>
          <th scope="col">Project</th>
          <th scope="col">AI score</th>
          <th scope="col">ATS score</th>
          <th scope="col">Flag</th>
        </tr>
      </thead>
      <tbody>
        {candidates.map((candidate) => (
          <tr key={candidate.id}>
            <td>{candidate.rank}</td>
            <td>
              <TextLink
                href={`/company/projects/${candidate.project_id}/candidates/${candidate.id}`}
              >
                {candidate.name || candidate.file_name}
              </TextLink>
            </td>
            <td>
              <TextLink href={`/company/projects/${candidate.project_id}`}>
                {candidate.project_title}
              </TextLink>
            </td>
            <td className="score-cell">{candidate.score}</td>
            <td className="score-cell">{candidate.ats_score ?? "None"}</td>
            <td>
              <Tag variant="neutral">{stageLabel(candidate.stage)}</Tag>
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
