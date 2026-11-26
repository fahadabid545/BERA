"use client";

import { useEffect, useRef, useState } from "react";

import { NEW_PROJECT_HREF, PROJECTS_HREF } from "@/components/company/links";
import { Button, ButtonLink, Card, Input, Select, Tag } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

const LIST_URL = "/api/company/projects/";

type Row = {
  id: string;
  title: string;
  created_by: string;
  created_at: string;
  cv_count: number;
  cv_capacity: number;
  best_score: number | null;
  status: "active" | "archived";
  updated_at: string;
};
type Page = { results: Row[]; page: number; pages: number; total: number };

const SORTS = [
  { value: "updated", label: "Last updated" },
  { value: "title", label: "Title" },
  { value: "best_score", label: "Best score" },
];
const FILTERS = [
  { value: "active", label: "Active" },
  { value: "archived", label: "Archived" },
  { value: "all", label: "All" },
];

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });

function ProjectCard({ row }: { row: Row }) {
  const full = row.cv_capacity > 0 && row.cv_count >= row.cv_capacity;
  return (
    <Card className="ui-card project-card" aria-label={row.title}>
      <div className="project-card__head">
        <h2 className="project-card__title">{row.title}</h2>
        {row.status === "archived" && <Tag variant="neutral">Archived</Tag>}
      </div>
      <dl className="project-card__facts">
        <dt>Created by</dt>
        <dd>{row.created_by}</dd>
        <dt>Created on</dt>
        <dd>{formatDate(row.created_at)}</dd>
        <dt>CVs</dt>
        <dd>
          {row.cv_capacity > 0 ? `${row.cv_count} of ${row.cv_capacity}` : row.cv_count}
          {full && <Tag variant="danger">Full</Tag>}
        </dd>
        <dt>Best score</dt>
        <dd>{row.best_score === null ? "None" : row.best_score}</dd>
      </dl>
      {row.cv_capacity > 0 && (
        <span
          className="usage-bar project-card__bar"
          role="meter"
          aria-label={`CVs in ${row.title}`}
          aria-valuemin={0}
          aria-valuemax={row.cv_capacity}
          aria-valuenow={Math.min(row.cv_count, row.cv_capacity)}
        >
          <span
            className="usage-bar__fill"
            style={{ width: `${Math.min(100, (row.cv_count / row.cv_capacity) * 100)}%` }}
          />
        </span>
      )}
      <ButtonLink variant="secondary" href={`${PROJECTS_HREF}/${row.id}`}>
        View more
      </ButtonLink>
    </Card>
  );
}

/** The company's projects with search, sort, filter and paging; the server does all of it. */
export function ProjectsList() {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("updated");
  const [status, setStatus] = useState("active");
  const [page, setPage] = useState(1);
  const [loaded, setLoaded] = useState<Page | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const latestRequest = useRef(0);

  useEffect(() => {
    const request = ++latestRequest.current;
    const query = new URLSearchParams({ sort, status, page: String(page) });
    if (search.trim()) query.set("search", search.trim());
    void getJson<Page>(`${LIST_URL}?${query}`).then((result) => {
      if (request !== latestRequest.current) return; // a newer search already replaced this one
      if (result.ok) {
        setLoaded(result.data);
        setError(null);
      } else setError(result.error);
    });
  }, [search, sort, status, page]);

  // Changing what is asked for starts again from the first page.
  const change = (apply: () => void) => {
    apply();
    setPage(1);
  };

  return (
    <div className="page-stack">
      <div className="page-actions">
        <ButtonLink href={NEW_PROJECT_HREF}>New project</ButtonLink>
      </div>
      <div className="page-actions">
        <Input
          label="Search"
          type="search"
          value={search}
          onChange={(event) => change(() => setSearch(event.target.value))}
        />
        <Select
          label="Sort by"
          options={SORTS}
          value={sort}
          onChange={(event) => change(() => setSort(event.target.value))}
        />
        <Select
          label="Show"
          options={FILTERS}
          value={status}
          onChange={(event) => change(() => setStatus(event.target.value))}
        />
      </div>
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      {loaded && loaded.results.length === 0 && <p>No projects found.</p>}
      {loaded && loaded.results.length > 0 && (
        <ul className="project-cards" aria-label="Projects">
          {loaded.results.map((row) => (
            <li key={row.id}>
              <ProjectCard row={row} />
            </li>
          ))}
        </ul>
      )}
      {loaded && loaded.pages > 1 && (
        <div className="page-actions">
          <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </Button>
          <span>
            Page {loaded.page} of {loaded.pages}
          </span>
          <Button
            variant="secondary"
            disabled={page >= loaded.pages}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
