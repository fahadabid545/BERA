"use client";

import { useEffect, useRef, useState } from "react";

import { Button, Input, Select, Table, Tag, TextLink } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";
import { countryOptions } from "@/lib/countries";

import { STATUS_NAMES, STATE_NAMES, formatDate } from "./companyText";

const LIST_URL = "/api/admin/companies/";

type Row = {
  id: string;
  name: string;
  country: string;
  status: string;
  plan_name: string | null;
  subscription_state: string;
  cvs_used: number;
  cvs_limit: number;
  users: number;
  created_at: string;
};
type Page = {
  results: Row[];
  page: number;
  pages: number;
  total: number;
  plans: { id: string; name: string }[];
};

const ANY = "";
const STATUS_OPTIONS = [
  { value: ANY, label: "Any status" },
  ...Object.entries(STATUS_NAMES).map(([value, label]) => ({ value, label })),
];
const USAGE_OPTIONS = [
  { value: ANY, label: "Any usage" },
  { value: "under", label: "Under 80%" },
  { value: "between", label: "80 to 99%" },
  { value: "reached", label: "100% reached" },
];
const COUNTRY_OPTIONS = [{ value: ANY, label: "Any country" }, ...countryOptions()];

/** Every company with search and filters; the server does all of the filtering and paging. */
export function CompaniesList() {
  const [filters, setFilters] = useState({
    search: "",
    status: ANY,
    plan: ANY,
    country: ANY,
    usage: ANY,
  });
  const [page, setPage] = useState(1);
  const [loaded, setLoaded] = useState<Page | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const latestRequest = useRef(0);

  useEffect(() => {
    const request = ++latestRequest.current;
    const query = new URLSearchParams({ page: String(page) });
    for (const [name, value] of Object.entries(filters)) {
      if (value.trim()) query.set(name, value.trim());
    }
    void getJson<Page>(`${LIST_URL}?${query}`).then((result) => {
      if (request !== latestRequest.current) return; // a newer search already replaced this one
      if (result.ok) {
        setLoaded(result.data);
        setError(null);
      } else setError(result.error);
    });
  }, [filters, page]);

  // Changing what is asked for starts again from the first page.
  const change = (name: keyof typeof filters, value: string) => {
    setFilters({ ...filters, [name]: value });
    setPage(1);
  };
  const planOptions = [
    { value: ANY, label: "Any plan" },
    { value: "none", label: "No plan" },
    ...(loaded?.plans ?? []).map((plan) => ({ value: plan.id, label: plan.name })),
  ];

  return (
    <div className="page-stack">
      <div className="page-actions">
        <Input
          label="Search"
          type="search"
          value={filters.search}
          onChange={(event) => change("search", event.target.value)}
        />
        <Select
          label="Status"
          options={STATUS_OPTIONS}
          value={filters.status}
          onChange={(event) => change("status", event.target.value)}
        />
        <Select
          label="Plan"
          options={planOptions}
          value={filters.plan}
          onChange={(event) => change("plan", event.target.value)}
        />
        <Select
          label="Country"
          options={COUNTRY_OPTIONS}
          value={filters.country}
          onChange={(event) => change("country", event.target.value)}
        />
        <Select
          label="Usage"
          options={USAGE_OPTIONS}
          value={filters.usage}
          onChange={(event) => change("usage", event.target.value)}
        />
      </div>
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      {loaded && loaded.results.length === 0 && <p>No companies found.</p>}
      {loaded && loaded.results.length > 0 && (
        <Table label="Companies">
          <thead>
            <tr>
              <th scope="col">Company</th>
              <th scope="col">Status</th>
              <th scope="col">Plan</th>
              <th scope="col">Subscription</th>
              <th scope="col">Country</th>
              <th scope="col">CVs this month</th>
              <th scope="col">Users</th>
              <th scope="col">Created</th>
            </tr>
          </thead>
          <tbody>
            {loaded.results.map((row) => (
              <tr key={row.id}>
                <td>
                  <TextLink href={`/admin/companies/${row.id}`}>{row.name}</TextLink>
                </td>
                <td>
                  <Tag variant={row.status === "active" ? "success" : "warning"}>
                    {STATUS_NAMES[row.status] ?? row.status}
                  </Tag>
                </td>
                <td>{row.plan_name ?? "None"}</td>
                <td>{STATE_NAMES[row.subscription_state] ?? row.subscription_state}</td>
                <td>{row.country}</td>
                <td>{row.cvs_limit ? `${row.cvs_used} of ${row.cvs_limit}` : row.cvs_used}</td>
                <td>{row.users}</td>
                <td>{formatDate(row.created_at)}</td>
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
