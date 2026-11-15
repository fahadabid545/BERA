"use client";

import { useEffect, useState } from "react";

import { stageLabel } from "@/components/company/stages";
import { Dialog, Tag, TextLink } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

/** What the popup lists: the card or mark that was clicked, as the server names it. */
export type Detail = { kind: string; key: string; title: string; project?: string | null };

type Item =
  | {
      type: "candidate";
      id: string;
      project_id: string;
      project_title: string;
      name: string;
      file_name: string;
      score: string | null;
      grade: string | null;
      stage: string;
    }
  | {
      type: "cv";
      id: string;
      project_id: string;
      project_title: string;
      file_name: string;
      status: string;
    }
  | {
      type: "project";
      id: string;
      title: string;
      cvs: number;
      scored: number;
      pending: number;
      failed: number;
    }
  | {
      type: "report";
      id: string;
      project_id: string;
      project_title: string;
      expires_at: string;
      views: number;
    };
type Body = { total: number; items: Item[] };

const CV_STATUSES: Record<string, string> = {
  awaiting_confirmation: "Awaiting confirmation",
  waiting: "Waiting",
  reading: "Reading",
  scoring: "Scoring",
  done: "Done",
  failed: "Failed",
};
const DATE_LENGTH = 10;
const projectHref = (id: string) => `/company/projects/${id}`;

function Row({ item }: { item: Item }) {
  if (item.type === "candidate") {
    return (
      <>
        <TextLink href={`${projectHref(item.project_id)}/candidates/${item.id}`}>
          {item.name || item.file_name}
        </TextLink>
        <span className="detail-list__facts">
          {item.score !== null && <span>AI score {item.score}</span>}
          {item.grade && <Tag variant="neutral">Grade {item.grade}</Tag>}
          <Tag variant="neutral">{stageLabel(item.stage)}</Tag>
          <TextLink href={projectHref(item.project_id)}>{item.project_title}</TextLink>
        </span>
      </>
    );
  }
  if (item.type === "cv") {
    return (
      <>
        <span>{item.file_name}</span>
        <span className="detail-list__facts">
          <Tag variant={item.status === "failed" ? "danger" : "neutral"}>
            {CV_STATUSES[item.status] ?? item.status}
          </Tag>
          <TextLink href={projectHref(item.project_id)}>{item.project_title}</TextLink>
        </span>
      </>
    );
  }
  if (item.type === "project") {
    return (
      <>
        <TextLink href={projectHref(item.id)}>{item.title}</TextLink>
        <span className="detail-list__facts">
          <span>CVs {item.cvs}</span>
          <span>Scored {item.scored}</span>
          <span>Pending {item.pending}</span>
          <span>Failed {item.failed}</span>
        </span>
      </>
    );
  }
  return (
    <>
      <TextLink href={`${projectHref(item.project_id)}/candidates`}>{item.project_title}</TextLink>
      <span className="detail-list__facts">
        <span>Ends {item.expires_at.slice(0, DATE_LENGTH)}</span>
        <span>Views {item.views}</span>
      </span>
    </>
  );
}

/** The popup behind a card or a mark: a short list of what was counted, each name a link to
 * the page where it can be worked on. It asks the server when it opens. */
export function DetailDialog({
  detail,
  days,
  onClose,
}: {
  detail: Detail | null;
  days?: number;
  onClose: () => void;
}) {
  const [body, setBody] = useState<Body | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    if (!detail) return;
    let current = true;
    const query = new URLSearchParams({ kind: detail.kind, key: detail.key });
    if (days) query.set("days", String(days));
    if (detail.project) query.set("project", detail.project);
    setBody(null);
    setError(null);
    void getJson<Body>(`/api/company/dashboard/detail/?${query}`).then((result) => {
      if (!current) return;
      if (result.ok) setBody(result.data);
      else setError(result.error);
    });
    return () => {
      current = false;
    };
  }, [detail, days]);

  return (
    <Dialog
      open={detail !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={detail?.title ?? ""}
    >
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      {body && body.items.length === 0 && <p role="status">Nothing here yet.</p>}
      {body && body.items.length > 0 && (
        <>
          <ul className="detail-list">
            {body.items.map((item) => (
              <li key={`${item.type}-${item.id}`} className="detail-list__item">
                <Row item={item} />
              </li>
            ))}
          </ul>
          <p role="status">
            Showing {body.items.length} of {body.total}
          </p>
        </>
      )}
    </Dialog>
  );
}
