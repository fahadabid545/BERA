"use client";

import { useEffect, useRef, useState } from "react";

import { Button, ButtonLink, Input, Select, Table, Tabs, Tag, TextLink } from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";
import { useTabParam } from "@/lib/useTabParam";

import { STAGES } from "./stages";

type Row = {
  id: string;
  project_id: string;
  project_title: string;
  file_name: string;
  name: string;
  score: string | null;
  grade: string | null;
  ats_score: number | null;
  label: string | null;
  stage: string;
  missing_must: number;
  missing_nice: number;
};
type Listing = {
  flag: string;
  page: number;
  pages: number;
  count: number;
  flags: Record<string, number>;
  projects: { id: string; title: string }[];
  rows: Row[];
};
type Filters = {
  q: string;
  project: string;
  score_min: string;
  ats_min: string;
  missing: string;
  grade: string;
  label: string;
};

const FLAG_TABS = [{ value: "all", label: "All" }, ...STAGES] as const;
const TAB_VALUES = FLAG_TABS.map((tab) => tab.value);
const STRICT_STEP: Record<string, number> = { score_min: 0.1, ats_min: 1 };
const ANY = { value: "", label: "Any" };
const ABOVE = [90, 80, 70, 60, 50].map((value) => ({
  value: String(value),
  label: `>${value}`,
}));
const MISSING = [
  ANY,
  { value: "must", label: "Missing a must-have" },
  { value: "nice", label: "Missing a nice-to-have" },
  { value: "none", label: "Nothing missing" },
];
const GRADES = [ANY, ...["A", "B", "C", "D", "E"].map((value) => ({ value, label: value }))];
const LABELS = [
  ANY,
  { value: "strong_match", label: "Strong match" },
  { value: "possible", label: "Possible" },
  { value: "not_recommended", label: "Not recommended" },
];
const SORTS = [
  { value: "score", label: "AI score" },
  { value: "ats", label: "ATS score" },
  { value: "added", label: "Date added" },
  { value: "candidate", label: "File name" },
];
const NO_FILTERS: Filters = {
  q: "",
  project: "",
  score_min: "",
  ats_min: "",
  missing: "",
  grade: "",
  label: "",
};

const LABEL_NAMES = Object.fromEntries(LABELS.map((item) => [item.value, item.label]));
const missingWords = (row: Row) =>
  [
    row.missing_must > 0 && `${row.missing_must} must-have`,
    row.missing_nice > 0 && `${row.missing_nice} nice-to-have`,
  ]
    .filter(Boolean)
    .join(", ") || "None";

/** Every candidate of the company in one place: a tab for each flag, filters on top, and the
 * flag changeable in the row. The server filters, sorts and pages; the address keeps the tab. */
export function CompanyCandidates() {
  const [tab, chooseTab] = useTabParam(TAB_VALUES);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [sort, setSort] = useState("score");
  const [page, setPage] = useState(1);
  const [listing, setListing] = useState<Listing | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [round, setRound] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    const request = ++latest.current;
    const query = new URLSearchParams({ flag: tab, sort, page: String(page) });
    for (const [key, value] of Object.entries(filters)) {
      if (!value.trim()) continue;
      // ">90" means above 90: the server takes a lowest value, and AI scores have one decimal.
      const step = STRICT_STEP[key];
      query.set(key, step ? String(Math.round((Number(value) + step) * 10) / 10) : value.trim());
    }
    void getJson<Listing>(`/api/company/candidates/?${query}`).then((result) => {
      if (request !== latest.current) return; // a newer question already replaced this one
      if (result.ok) {
        setListing(result.data);
        setError(null);
      } else setError(result.error);
    });
  }, [tab, filters, sort, page, round]);

  const change = (apply: () => void) => {
    apply();
    setPage(1);
  };
  const filter = (name: keyof Filters) => ({
    value: filters[name],
    onChange: (event: { target: { value: string } }) =>
      change(() => setFilters((current) => ({ ...current, [name]: event.target.value }))),
  });

  async function changeFlag(row: Row, stage: string) {
    const result = await postJson(`/api/company/projects/${row.project_id}/candidates/stage/`, {
      candidate_ids: [row.id],
      stage,
    });
    if (result.ok) setRound((value) => value + 1);
    else setError(result.error);
  }

  const table = (
    <>
      {listing && listing.rows.length === 0 && <p role="status">No candidates found.</p>}
      {listing && listing.rows.length > 0 && (
        <Table label="Candidates">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Project</th>
              <th scope="col">AI score</th>
              <th scope="col">ATS score</th>
              <th scope="col">Recommendation</th>
              <th scope="col">Missing</th>
              <th scope="col">Flag</th>
            </tr>
          </thead>
          <tbody>
            {listing.rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <TextLink href={`/company/projects/${row.project_id}/candidates/${row.id}`}>
                    {row.name || row.file_name}
                  </TextLink>
                </td>
                <td>
                  <TextLink href={`/company/projects/${row.project_id}`}>
                    {row.project_title}
                  </TextLink>
                </td>
                <td className="score-cell">
                  {row.score === null ? "None" : `${row.score} (${row.grade})`}
                </td>
                <td className="score-cell">{row.ats_score ?? "None"}</td>
                <td>
                  {row.label ? <Tag variant="neutral">{LABEL_NAMES[row.label]}</Tag> : "None"}
                </td>
                <td>{missingWords(row)}</td>
                <td>
                  <Select
                    label={`Flag for ${row.name || row.file_name}`}
                    value={row.stage}
                    options={STAGES}
                    onChange={(event) => void changeFlag(row, event.target.value)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {listing && listing.pages > 1 && (
        <div className="page-actions">
          <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </Button>
          <span>
            Page {listing.page} of {listing.pages}
          </span>
          <Button
            variant="secondary"
            disabled={page >= listing.pages}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </>
  );

  return (
    <div className="page-stack">
      <div className="page-actions candidate-filters">
        <Input label="Search" type="search" {...filter("q")} />
        <Select
          label="Project"
          options={[
            { value: "", label: "All projects" },
            ...(listing?.projects.map((item) => ({ value: item.id, label: item.title })) ?? []),
          ]}
          {...filter("project")}
        />
        <Select label="AI score" options={[ANY, ...ABOVE]} {...filter("score_min")} />
        <Select label="ATS score" options={[ANY, ...ABOVE]} {...filter("ats_min")} />
        <Select label="Missing" options={MISSING} {...filter("missing")} />
        <Select label="Grade" options={GRADES} {...filter("grade")} />
        <Select label="Recommendation" options={LABELS} {...filter("label")} />
        <Select
          label="Sort by"
          options={SORTS}
          value={sort}
          onChange={(event) => change(() => setSort(event.target.value))}
        />
        <Button variant="secondary" onClick={() => change(() => setFilters(NO_FILTERS))}>
          Clear filters
        </Button>
        {filters.project && (
          <ButtonLink variant="secondary" href={`/company/projects/${filters.project}/compare`}>
            Compare in this project
          </ButtonLink>
        )}
      </div>
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      <Tabs
        label="Flags"
        value={tab}
        onValueChange={(next) => {
          setPage(1);
          chooseTab(next);
        }}
        tabs={FLAG_TABS.map((item) => ({
          value: item.value,
          label: listing ? `${item.label} (${listing.flags[item.value] ?? 0})` : item.label,
          content: item.value === tab ? table : null,
        }))}
      />
    </div>
  );
}
