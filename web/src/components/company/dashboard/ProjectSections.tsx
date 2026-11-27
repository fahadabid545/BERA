import { DailyBars } from "@/components/admin/access/DailyBars";
import { Card, Table, Tag, TextLink } from "@/components/ui";

import type { AttentionItem, DashboardData, MissedRequirement, ProjectRow } from "./types";

const PERCENT = 100;
const DAY_MS = 86_400_000;
const none = (value: number | null) => (value === null ? "None" : value);

const ATTENTION_WORDS: Record<AttentionItem["reason"], (item: AttentionItem) => string> = {
  failed: (item) => `${item.count} CVs failed to process`,
  almost_full: (item) => `${item.count} of ${item.capacity} CVs held, nearly full`,
  none_scored: (item) => `${item.count} CVs uploaded, none scored yet`,
};

const projectHref = (id: string) => `/company/projects/${id}`;

/** One row for each project: CVs held against what it can hold, scores and how far candidates got. */
export function ProjectTable({ rows }: { rows: ProjectRow[] }) {
  return (
    <Card className="ui-card">
      <div className="chart-card__header">
        <h2>All projects</h2>
      </div>
      {rows.length === 0 ? (
        <p role="status">No projects yet.</p>
      ) : (
        <Table label="All projects">
          <thead>
            <tr>
              <th scope="col">Project</th>
              <th scope="col">CVs</th>
              <th scope="col">Scored</th>
              <th scope="col">Best score</th>
              <th scope="col">Shortlisted</th>
              <th scope="col">Interviewed</th>
              <th scope="col">Selected</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <TextLink href={projectHref(row.id)}>{row.title}</TextLink>
                </td>
                <td className="score-cell">
                  {row.capacity > 0 ? `${row.cvs} of ${row.capacity}` : row.cvs}
                </td>
                <td className="score-cell">{row.scored}</td>
                <td className="score-cell">{none(row.best_score)}</td>
                <td className="score-cell">{row.shortlisted}</td>
                <td className="score-cell">{row.interviewed}</td>
                <td className="score-cell">{row.selected}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}

/** The projects that need a look, each with the reason in words. */
export function NeedsAttention({ items }: { items: AttentionItem[] }) {
  return (
    <Card className="ui-card">
      <div className="chart-card__header">
        <h2>Needs attention</h2>
      </div>
      {items.length === 0 ? (
        <p role="status">Nothing needs attention.</p>
      ) : (
        <ul className="detail-list">
          {items.map((item) => (
            <li key={`${item.id}-${item.reason}`} className="detail-list__item">
              <TextLink href={projectHref(item.id)}>{item.title}</TextLink>
              <span className="detail-list__facts">{ATTENTION_WORDS[item.reason](item)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** The CVs added on each day of the chosen period. */
export function UploadsPerDay({ uploads }: { uploads: DashboardData["uploads_per_day"] }) {
  const first = new Date(`${uploads.start}T00:00:00Z`).getTime();
  const days = uploads.values.map((cvs, offset) => ({
    day: new Date(first + offset * DAY_MS).toISOString(),
    cvs,
  }));
  return (
    <Card className="ui-card">
      <div className="chart-card__header">
        <h2>CVs added each day</h2>
      </div>
      <DailyBars days={days} label="CVs added each day" />
    </Card>
  );
}

function ScoreBar({ label, value }: { label: string; value: number | null }) {
  return (
    <span className="average-score">
      <span
        className="usage-bar"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={PERCENT}
        aria-valuenow={value ?? 0}
      >
        <span className="usage-bar__fill" style={{ width: `${value ?? 0}%` }} />
      </span>
      <span className="score-cell">{none(value)}</span>
    </span>
  );
}

/** The average AI score and ATS score of each project, side by side. */
export function AverageScores({ rows }: { rows: ProjectRow[] }) {
  return (
    <Card className="ui-card">
      <div className="chart-card__header">
        <h2>Average score per project</h2>
      </div>
      {rows.length === 0 ? (
        <p role="status">No projects yet.</p>
      ) : (
        <Table label="Average score per project">
          <thead>
            <tr>
              <th scope="col">Project</th>
              <th scope="col">AI score</th>
              <th scope="col">ATS score</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <TextLink href={projectHref(row.id)}>{row.title}</TextLink>
                </td>
                <td>
                  <ScoreBar label={`AI score of ${row.title}`} value={row.average_score} />
                </td>
                <td>
                  <ScoreBar label={`ATS score of ${row.title}`} value={row.ats_average} />
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}

/** The requirements missing for the most candidates, with the project they belong to. */
export function MissedRequirements({ items }: { items: MissedRequirement[] }) {
  return (
    <Card className="ui-card">
      <div className="chart-card__header">
        <h2>Most missed requirements</h2>
      </div>
      {items.length === 0 ? (
        <p role="status">No requirement is missing yet.</p>
      ) : (
        <Table label="Most missed requirements">
          <thead>
            <tr>
              <th scope="col">Requirement</th>
              <th scope="col">Type</th>
              <th scope="col">Project</th>
              <th scope="col">Missing</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={`${item.project_id}-${item.requirement}`}>
                <td>{item.requirement}</td>
                <td>
                  <Tag variant="neutral">{item.kind === "must" ? "Must-have" : "Nice-to-have"}</Tag>
                </td>
                <td>
                  <TextLink href={projectHref(item.project_id)}>{item.project_title}</TextLink>
                </td>
                <td className="score-cell">
                  {item.missing} of {item.judged}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}
