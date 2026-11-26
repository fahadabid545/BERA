"use client";

import { useEffect, useState } from "react";

import { Input, Table, Tag, TextLink } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

import { Pager } from "./Pager";
import { BASE, day, KIND_TEXT, type Page, type PaidRow } from "./types";

/** Companies that pay by card, a page at a time; each opens its company page. A free access it
 * also holds is named, because that one is revoked on its own. */
export function PaidSection() {
  const [listing, setListing] = useState<Page<PaidRow> | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    const query = new URLSearchParams({ page: String(page) });
    if (search) query.set("search", search);
    void getJson<Page<PaidRow>>(`${BASE}paid/?${query}`).then((result) => {
      if (result.ok) setListing(result.data);
      else setError(result.error);
    });
  }, [page, search]);

  return (
    <div className="page-stack">
      <div className="page-actions">
        <Input
          label="Search"
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
        />
      </div>
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      {listing && (
        <>
          <Table label="Paid users">
            <thead>
              <tr>
                <th>Company</th>
                <th>Plan</th>
                <th>State</th>
                <th>Renews</th>
                <th>CVs</th>
                <th>Users</th>
                <th>Also</th>
              </tr>
            </thead>
            <tbody>
              {listing.items.map((row) => (
                <tr key={row.id}>
                  <td>
                    <TextLink href={`/admin/companies/${row.id}`}>{row.name}</TextLink>
                  </td>
                  <td>{row.plan_name ?? ""}</td>
                  <td>
                    <Tag variant={row.state === "active" ? "success" : "warning"}>
                      {row.state.replaceAll("_", " ")}
                    </Tag>
                  </td>
                  <td>{day(row.period_end)}</td>
                  <td>
                    {row.cvs_used} of {row.cvs_limit}
                  </td>
                  <td>{row.users}</td>
                  <td>{row.also_free_access.map((kind) => KIND_TEXT[kind]).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pager listing={listing} onPage={setPage} />
        </>
      )}
    </div>
  );
}
