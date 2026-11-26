"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Card, Table, Tag } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

import { STATE_NAMES, STATUS_NAMES, formatDate } from "./companyText";
import { StartTrial } from "./StartTrial";

type Measure = { used: number; limit: number };
type Detail = {
  company: {
    id: string;
    name: string;
    country: string;
    status: string;
    created_at: string;
    deletion_due_at: string | null;
  };
  users: { id: string; name: string; email: string; role: string; status: string }[];
  subscription: {
    plan_name: string | null;
    state: string;
    renewal: boolean;
    grace_ends_at: string | null;
    period_start: string | null;
    period_end: string | null;
  };
  usage: {
    cvs: Measure;
    projects: Measure;
    estimated_cost?: string;
  };
  project_counts: { active: number; archived: number };
  projects: {
    id: string;
    title: string;
    status: string;
    reading_model: string;
    reading_prompt_version: number;
    created_at: string;
  }[];
  history: { id: number; kind: string; actor_kind: string; reason: string; created_at: string }[];
};

const COST_DECIMALS = 2;
const number = (value: number) => value.toLocaleString("en-US");
const capitalised = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);
const plain = (value: string) => capitalised(value.replace(/[._]/g, " "));
const dateOrNone = (iso: string | null) => (iso ? formatDate(iso) : "None");
const measureText = (measure: Measure) => `${number(measure.used)} of ${number(measure.limit)}`;

/** One company for an admin: its people, subscription, usage, projects and history, then the
 * actions an admin has. It holds no candidate or CV content; the server never sends any. */
export function CompanyDetail({ companyId }: { companyId: string }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    const result = await getJson<Detail>(`/api/admin/companies/${companyId}/`);
    if (result.ok) setDetail(result.data);
    else setError(result.error);
  }, [companyId]);
  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    );
  }
  if (!detail) return null;
  const { company, users, subscription, usage, project_counts: counts, projects, history } = detail;

  return (
    <div className="page-stack">
      <Card className="ui-card">
        <h2>{company.name}</h2>
        <dl>
          <dt>Status</dt>
          <dd>
            <Tag variant={company.status === "active" ? "success" : "warning"}>
              {STATUS_NAMES[company.status] ?? company.status}
            </Tag>
          </dd>
          <dt>Country</dt>
          <dd>{company.country}</dd>
          <dt>Created</dt>
          <dd>{formatDate(company.created_at)}</dd>
          {company.deletion_due_at && (
            <>
              <dt>Deleted on</dt>
              <dd>{formatDate(company.deletion_due_at)}</dd>
            </>
          )}
        </dl>
        <div className="page-actions">
          <Button variant="danger">Suspend</Button>
          <Button variant="danger">Terminate subscription</Button>
          <Button variant="secondary">Grant free subscription</Button>
          <StartTrial
            companyId={companyId}
            state={subscription.state}
            onStarted={() => void load()}
          />
          <Button variant="secondary">Change limits</Button>
          <Button variant="danger">Block member</Button>
        </div>
      </Card>
      <Card className="ui-card">
        <h2>Users</h2>
        <Table label="Users">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Email</th>
              <th scope="col">Role</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {users.map((person) => (
              <tr key={person.id}>
                <td>{person.name}</td>
                <td>{person.email}</td>
                <td>{capitalised(person.role)}</td>
                <td>{capitalised(person.status)}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
      <Card className="ui-card">
        <h2>Subscription</h2>
        <dl>
          <dt>Plan</dt>
          <dd>{subscription.plan_name ?? "None"}</dd>
          <dt>State</dt>
          <dd>{STATE_NAMES[subscription.state] ?? subscription.state}</dd>
          <dt>Renews</dt>
          <dd>{subscription.renewal ? "Yes" : "No"}</dd>
          <dt>Period start</dt>
          <dd>{dateOrNone(subscription.period_start)}</dd>
          <dt>Period end</dt>
          <dd>{dateOrNone(subscription.period_end)}</dd>
          {subscription.grace_ends_at && (
            <>
              <dt>Grace period ends</dt>
              <dd>{formatDate(subscription.grace_ends_at)}</dd>
            </>
          )}
        </dl>
      </Card>
      <Card className="ui-card">
        <h2>Usage this period</h2>
        <dl>
          <dt>CVs</dt>
          <dd>{measureText(usage.cvs)}</dd>
          <dt>Projects</dt>
          <dd>{measureText(usage.projects)}</dd>
          {usage.estimated_cost !== undefined && (
            <>
              <dt>AI cost</dt>
              <dd>{`$${Number(usage.estimated_cost).toFixed(COST_DECIMALS)}`}</dd>
            </>
          )}
        </dl>
      </Card>
      <Card className="ui-card">
        <h2>Projects</h2>
        <p>{`${counts.active} active, ${counts.archived} archived`}</p>
        {projects.length > 0 && (
          <Table label="Projects">
            <thead>
              <tr>
                <th scope="col">Title</th>
                <th scope="col">Status</th>
                <th scope="col">Reading model</th>
                <th scope="col">Prompt version</th>
                <th scope="col">Created</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((project) => (
                <tr key={project.id}>
                  <td>{project.title}</td>
                  <td>{capitalised(project.status)}</td>
                  <td>{project.reading_model}</td>
                  <td>{project.reading_prompt_version}</td>
                  <td>{formatDate(project.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      <Card className="ui-card">
        <h2>History</h2>
        {history.length === 0 ? (
          <p>No history yet.</p>
        ) : (
          <Table label="History">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">What</th>
                <th scope="col">By</th>
                <th scope="col">Reason</th>
              </tr>
            </thead>
            <tbody>
              {history.map((entry) => (
                <tr key={entry.id}>
                  <td>{formatDate(entry.created_at)}</td>
                  <td>{plain(entry.kind)}</td>
                  <td>{entry.actor_kind === "none" ? "System" : capitalised(entry.actor_kind)}</td>
                  <td>{entry.reason}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
