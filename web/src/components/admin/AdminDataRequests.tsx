"use client";

import { useCallback, useEffect, useState } from "react";

import {
  Button,
  Dialog,
  Input,
  Select,
  Table,
  Tag,
  Textarea,
  TextLink,
  type TagVariant,
} from "@/components/ui";
import { getJson, patchJson, postJson, type ApiError, type ApiResult } from "@/lib/api";

type Kind = "export" | "deletion";
type Status = "open" | "in_progress" | "completed";
type Item = {
  id: number;
  company_id: number;
  company: string;
  company_exists: boolean;
  kind: Kind;
  requested_by: string;
  received_on: string;
  due_on: string;
  status: Status;
  completed_on: string | null;
  note: string;
  overdue: boolean;
};
type Listing = { total: number; items: Item[]; companies: { id: number; name: string }[] };
type Open = { kind: "create" } | { kind: "change"; item: Item };

const BASE = "/api/admin/data-requests/";
const ALL = "";
const KIND_WORDS: Record<Kind, string> = { export: "Export", deletion: "Deletion" };
const STATUS_WORDS: Record<Status, string> = {
  open: "Open",
  in_progress: "In progress",
  completed: "Completed",
};
const STATUS_TAGS: Record<Status, TagVariant> = {
  open: "warning",
  in_progress: "live",
  completed: "success",
};
const STATUSES = Object.keys(STATUS_WORDS) as Status[];
const KINDS = Object.keys(KIND_WORDS) as Kind[];
const NEW_FORM = { company: "", kind: "export" as Kind, requestedBy: "", receivedOn: "", note: "" };

const today = () => new Date().toISOString().slice(0, "YYYY-MM-DD".length);

/** Deletion and export requests that arrive from companies, tracked until they are completed.
 * A request only moves forward; the due date is fixed when it is logged. */
export function AdminDataRequests() {
  const [listing, setListing] = useState<Listing | null>(null);
  const [filter, setFilter] = useState(ALL);
  const [open, setOpen] = useState<Open | null>(null);
  const [form, setForm] = useState(NEW_FORM);
  const [status, setStatus] = useState<Status>("open");
  const [note, setNote] = useState("");
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    const result = await getJson<Listing>(filter ? `${BASE}?status=${filter}` : BASE);
    if (result.ok) setListing(result.data);
    else setError(result.error);
  }, [filter]);
  useEffect(() => {
    void load();
  }, [load]);

  function show(next: Open) {
    setError(null);
    if (next.kind === "create") setForm({ ...NEW_FORM, receivedOn: today() });
    else {
      setStatus(next.item.status);
      setNote(next.item.note);
    }
    setOpen(next);
  }

  async function finish(result: ApiResult<Listing>, reopen: Open | null) {
    if (result.ok) return void (await load());
    setError(result.error);
    // The popup closes when confirmed; a refused form comes back with what was typed.
    setOpen(reopen);
  }

  async function save() {
    if (!open) return;
    setError(null);
    if (open.kind === "create") {
      await finish(
        await postJson<Listing>(BASE, {
          company: Number(form.company),
          kind: form.kind,
          requested_by: form.requestedBy,
          received_on: form.receivedOn,
          ...(form.note ? { note: form.note } : {}),
        }),
        open,
      );
    } else {
      await finish(await patchJson<Listing>(`${BASE}${open.item.id}/`, { status, note }), open);
    }
  }

  if (!listing) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const fields = error?.fields ?? {};
  const alertText = error && (Object.keys(fields).length === 0 ? error.message : null);
  const forward =
    open?.kind === "change" ? STATUSES.slice(STATUSES.indexOf(open.item.status)) : STATUSES;

  return (
    <div className="page-stack">
      {alertText && (
        <p className="ui-error" role="alert">
          {alertText}
        </p>
      )}
      <div className="page-actions">
        <Button onClick={() => show({ kind: "create" })}>New request</Button>
        <Select
          label="Status"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          options={[
            { value: ALL, label: "All statuses" },
            ...STATUSES.map((each) => ({ value: each, label: STATUS_WORDS[each] })),
          ]}
        />
      </div>
      {listing.items.length === 0 ? (
        <p role="status">No data requests.</p>
      ) : (
        <>
          <Table label="Data requests">
            <thead>
              <tr>
                <th scope="col">Company</th>
                <th scope="col">Type</th>
                <th scope="col">Requested by</th>
                <th scope="col">Received</th>
                <th scope="col">Due</th>
                <th scope="col">Status</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {listing.items.map((item) => (
                <tr key={item.id}>
                  <th scope="row">
                    {item.company_exists ? (
                      <TextLink href={`/admin/companies/${item.company_id}`}>
                        {item.company}
                      </TextLink>
                    ) : (
                      item.company
                    )}
                  </th>
                  <td>{KIND_WORDS[item.kind]}</td>
                  <td>{item.requested_by}</td>
                  <td>{item.received_on}</td>
                  <td>
                    {item.due_on} {item.overdue && <Tag variant="danger">Overdue</Tag>}
                  </td>
                  <td>
                    <Tag variant={STATUS_TAGS[item.status]}>{STATUS_WORDS[item.status]}</Tag>
                  </td>
                  <td>
                    <Button variant="secondary" onClick={() => show({ kind: "change", item })}>
                      Update
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
          <p role="status">
            Showing {listing.items.length} of {listing.total}
          </p>
        </>
      )}
      <Dialog
        open={open !== null}
        onOpenChange={(next) => {
          if (!next) setOpen(null);
        }}
        title={open?.kind === "change" ? "Update request" : "New request"}
        confirmLabel="Save"
        onConfirm={() => void save()}
      >
        <div className="page-stack">
          {open?.kind === "create" ? (
            <>
              <Select
                label="Company"
                value={form.company}
                error={fields.company}
                onChange={(event) => setForm({ ...form, company: event.target.value })}
                options={[
                  { value: "", label: "Choose a company" },
                  ...listing.companies.map((each) => ({
                    value: String(each.id),
                    label: each.name,
                  })),
                ]}
              />
              <Select
                label="Type"
                value={form.kind}
                error={fields.kind}
                onChange={(event) => setForm({ ...form, kind: event.target.value as Kind })}
                options={KINDS.map((each) => ({ value: each, label: KIND_WORDS[each] }))}
              />
              <Input
                label="Requested by"
                value={form.requestedBy}
                error={fields.requested_by}
                onChange={(event) => setForm({ ...form, requestedBy: event.target.value })}
              />
              <Input
                label="Received on"
                type="date"
                value={form.receivedOn}
                error={fields.received_on}
                onChange={(event) => setForm({ ...form, receivedOn: event.target.value })}
              />
              <Textarea
                label="Note"
                value={form.note}
                error={fields.note}
                onChange={(event) => setForm({ ...form, note: event.target.value })}
              />
            </>
          ) : (
            <>
              <Select
                label="Status"
                value={status}
                error={fields.status}
                onChange={(event) => setStatus(event.target.value as Status)}
                options={forward.map((each) => ({ value: each, label: STATUS_WORDS[each] }))}
              />
              <Textarea
                label="Note"
                value={note}
                error={fields.note}
                onChange={(event) => setNote(event.target.value)}
              />
            </>
          )}
        </div>
      </Dialog>
    </div>
  );
}
