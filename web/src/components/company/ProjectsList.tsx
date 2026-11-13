"use client";

import { useEffect, useRef, useState } from "react";

import { NEW_PROJECT_HREF, PROJECTS_HREF } from "@/components/company/links";
import { Button, ButtonLink, Input, Select, Table, Tag, TextLink } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

const LIST_URL = "/api/company/projects/";

type Row = {
  id: string;
  title: string;
  cv_count: number;
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
        <Table label="Projects">
          <thead>
            <tr>
              <th scope="col">Title</th>
              <th scope="col">CVs</th>
              <th scope="col">Best score</th>
              <th scope="col">Status</th>
              <th scope="col">Last updated</th>
            </tr>
          </thead>
          <tbody>
            {loaded.results.map((row) => (
              <tr key={row.id}>
                <td>
                  <TextLink href={`${PROJECTS_HREF}/${row.id}`}>{row.title}</TextLink>
                </td>
                <td>{row.cv_count}</td>
                <td>{row.best_score === null ? "None" : row.best_score}</td>
                <td>
                  <Tag variant={row.status === "active" ? "success" : "neutral"}>
                    {row.status === "active" ? "Active" : "Archived"}
                  </Tag>
                </td>
                <td>{formatDate(row.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </Table>
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
