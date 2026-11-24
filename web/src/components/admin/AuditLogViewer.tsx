"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Button, Input, Select, Table } from "@/components/ui";
import { getFile, getJson, type ApiError } from "@/lib/api";

type Entry = {
  id: number;
  at: string;
  action: string;
  person: { kind: string; id: number | null; name: string };
  company_id: number | null;
  company: string;
  target_kind: string;
  target_id: string;
  reason: string;
  details: Record<string, unknown>;
};
type Page = { items: Entry[]; next: string | null; actions: string[] };
type Filters = {
  person: string;
  company: string;
  action: string;
  from_date: string;
  to_date: string;
};

const BASE = "/api/admin/audit-log/";
const NONE: Filters = { person: "", company: "", action: "", from_date: "", to_date: "" };
const MINUTE_LENGTH = "YYYY-MM-DD HH:MM".length;

/** The query string of the filters that are filled in; the same for the page and the export. */
function queryOf(filters: Filters, cursor?: string) {
  const query = new URLSearchParams();
  for (const [name, value] of Object.entries(filters)) {
    if (value.trim()) query.set(name, value.trim());
  }
  if (cursor) query.set("cursor", cursor);
  const text = query.toString();
  return text ? `?${text}` : "";
}

const moment = (iso: string) => iso.replace("T", " ").slice(0, MINUTE_LENGTH);
const detailText = (details: Entry["details"]) =>
  Object.entries(details)
    .map(([name, value]) => `${name}: ${typeof value === "object" ? JSON.stringify(value) : value}`)
    .join("; ");

/** The audit log, newest first, with filters by person, company, action and dates, a Load more
 * for the next page and an export of what the filters show. The export is recorded in the log. */
export function AuditLogViewer() {
  const [form, setForm] = useState<Filters>(NONE);
  const [applied, setApplied] = useState<Filters>(NONE);
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [actions, setActions] = useState<string[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async (filters: Filters, cursor?: string) => {
    setError(null);
    const result = await getJson<Page>(`${BASE}${queryOf(filters, cursor)}`);
    if (!result.ok) return setError(result.error);
    setEntries((before) =>
      cursor && before ? [...before, ...result.data.items] : result.data.items,
    );
    setNext(result.data.next);
    setActions(result.data.actions);
  }, []);
  useEffect(() => {
    void load(applied);
  }, [applied, load]);

  function apply(event: FormEvent) {
    event.preventDefault();
    // A new object every time, so Filter also reloads when nothing was changed.
    setApplied({ ...form });
  }

  async function exportFile() {
    setError(null);
    const result = await getFile(`${BASE}export/${queryOf(applied)}`);
    if (!result.ok) return setError(result.error);
    const link = document.createElement("a");
    link.href = URL.createObjectURL(result.data);
    link.download = "audit-log.csv";
    link.click();
    URL.revokeObjectURL(link.href);
  }

  const fields = error?.fields ?? {};
  const generalError = error && Object.keys(fields).length === 0 ? error.message : null;
  if (!entries) {
    return generalError ? (
      <p className="ui-error" role="alert">
        {generalError}
      </p>
    ) : null;
  }
  return (
    <div className="page-stack">
      <form className="page-actions" onSubmit={apply} noValidate>
        <Input
          label="Person"
          value={form.person}
          error={fields.person}
          onChange={(event) => setForm({ ...form, person: event.target.value })}
        />
        <Input
          label="Company ID"
          inputMode="numeric"
          value={form.company}
          error={fields.company}
          onChange={(event) => setForm({ ...form, company: event.target.value })}
        />
        <Select
          label="Action"
          value={form.action}
          error={fields.action}
          onChange={(event) => setForm({ ...form, action: event.target.value })}
          options={[
            { value: "", label: "All actions" },
            ...actions.map((each) => ({ value: each, label: each })),
          ]}
        />
        <Input
          label="From"
          type="date"
          value={form.from_date}
          error={fields.from_date}
          onChange={(event) => setForm({ ...form, from_date: event.target.value })}
        />
        <Input
          label="To"
          type="date"
          value={form.to_date}
          error={fields.to_date}
          onChange={(event) => setForm({ ...form, to_date: event.target.value })}
        />
        <Button type="submit">Filter</Button>
        <Button variant="secondary" onClick={() => void exportFile()}>
          Export
        </Button>
      </form>
      {generalError && (
        <p className="ui-error" role="alert">
          {generalError}
        </p>
      )}
      {entries.length === 0 ? (
        <p role="status">No entries.</p>
      ) : (
        <Table label="Audit log">
          <thead>
            <tr>
              <th scope="col">Time (UTC)</th>
              <th scope="col">Action</th>
              <th scope="col">Person</th>
              <th scope="col">Company</th>
              <th scope="col">Target</th>
              <th scope="col">Reason</th>
              <th scope="col">Details</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id}>
                <th scope="row">{moment(entry.at)}</th>
                <td>{entry.action}</td>
                <td>
                  {entry.person.name ||
                    (entry.person.id ? `${entry.person.kind} ${entry.person.id}` : "System")}
                </td>
                <td>{entry.company || (entry.company_id ?? "")}</td>
                <td>{entry.target_kind && `${entry.target_kind} ${entry.target_id}`}</td>
                <td>{entry.reason}</td>
                <td>{detailText(entry.details)}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {next && (
        <div className="page-actions">
          <Button variant="secondary" onClick={() => void load(applied, next)}>
            Load more
          </Button>
        </div>
      )}
    </div>
  );
}
