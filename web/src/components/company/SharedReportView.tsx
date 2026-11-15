"use client";

import { useEffect, useState } from "react";

import { Card, Tag } from "@/components/ui";
import { getJson } from "@/lib/api";

type Entry = {
  rank: number;
  candidate: string;
  score: string;
  grade: string;
  strengths: string[];
  risks: string[];
  contact?: { name: string; email: string; phone: string };
};
type Report = { title: string; expires_at: string; hide_contact: boolean; entries: Entry[] };

const UNAVAILABLE = "This report is no longer available.";
const DATE_LENGTH = 10;

/** The public page of a shared report: only what was chosen to be shared. */
export function SharedReportView({ token }: { token: string }) {
  const [report, setReport] = useState<Report | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    let stopped = false;
    // A link counts a view each time it is opened, so it is asked for once.
    void getJson<Report>(`/api/reports/${encodeURIComponent(token)}/`).then((result) => {
      if (stopped) return;
      if (result.ok) setReport(result.data);
      else setUnavailable(true);
    });
    return () => {
      stopped = true;
    };
  }, [token]);

  if (unavailable) {
    return (
      <div className="site-container page-stack">
        <p role="status">{UNAVAILABLE}</p>
      </div>
    );
  }
  if (!report) return null;
  return (
    <div className="site-container page-stack">
      <h1>{report.title}</h1>
      <p>Available until {report.expires_at.slice(0, DATE_LENGTH)}</p>
      {report.entries.map((entry) => (
        <Card key={entry.rank}>
          <h2>
            {entry.rank}. {entry.contact?.name || entry.candidate}
          </h2>
          <p>
            Score {entry.score} <Tag variant="neutral">Grade {entry.grade}</Tag>
          </p>
          {entry.contact && (
            <p>{[entry.contact.email, entry.contact.phone].filter(Boolean).join(" · ")}</p>
          )}
          <h3>Strengths</h3>
          <ul>
            {entry.strengths.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <h3>Risks</h3>
          <ul>
            {entry.risks.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}
