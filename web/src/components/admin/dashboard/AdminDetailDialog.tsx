"use client";

import { useEffect, useState } from "react";

import { Dialog, Tag, TextLink } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

import { PURPOSE_WORDS, STATE_WORDS, usd, whole, type CompanyRow } from "./types";

export type AdminDetail = { kind: string; key: string; title: string };

type CallRow = {
  type: "ai_call";
  id: string;
  company_id: string;
  model: string;
  purpose: string;
  result: string;
  failure: string;
  tokens: number;
  cost: number;
  at: string;
};
type Body = { total: number; items: (CompanyRow | CallRow)[] };

const DATE_LENGTH = 10;

function Row({ item }: { item: CompanyRow | CallRow }) {
  if (item.type === "company") {
    return (
      <>
        <TextLink href={`/admin/companies/${item.id}`}>{item.name}</TextLink>
        <span className="detail-list__facts">
          <Tag variant="neutral">{STATE_WORDS[item.state] ?? item.state}</Tag>
          {item.plan && <span>{item.plan}</span>}
          {item.status === "suspended" && <Tag variant="danger">Suspended</Tag>}
          {item.cvs_scored !== undefined && <span>CVs scored {whole(item.cvs_scored)}</span>}
          {item.tokens !== undefined && <span>Tokens {whole(item.tokens)}</span>}
          {item.cost !== undefined && <span>AI cost {usd(item.cost)}</span>}
        </span>
      </>
    );
  }
  return (
    <>
      <TextLink href={`/admin/companies/${item.company_id}`}>Company</TextLink>
      <span className="detail-list__facts">
        <Tag variant={item.result === "failed" ? "danger" : "neutral"}>
          {item.result === "failed" ? "Failed" : "Done"}
        </Tag>
        <span>{PURPOSE_WORDS[item.purpose] ?? item.purpose}</span>
        <span>{item.model}</span>
        <span>Tokens {whole(item.tokens)}</span>
        <span>{usd(item.cost)}</span>
        <span>{item.at.slice(0, DATE_LENGTH)}</span>
        {item.failure && <span>{item.failure}</span>}
      </span>
    </>
  );
}

/** The popup behind a card or a mark of the admin overview: the companies (or AI calls) it is
 * made of, each a link to where it can be looked at. It asks the server when it opens. */
export function AdminDetailDialog({
  detail,
  days,
  onClose,
}: {
  detail: AdminDetail | null;
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
    setBody(null);
    setError(null);
    void getJson<Body>(`/api/admin/dashboard/detail/?${query}`).then((result) => {
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
