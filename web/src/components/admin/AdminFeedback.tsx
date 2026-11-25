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
import { getJson, patchJson, type ApiError } from "@/lib/api";

type Kind = "bug" | "idea" | "question";
type Status = "new" | "reviewing" | "fixed" | "wont_fix";
type Item = {
  id: string;
  company_id: number;
  company: string;
  user: string;
  kind: Kind;
  message: string;
  page: string;
  status: Status;
  note: string;
  created_at: string;
};
type Listing = { total: number; items: Item[] };
type Filters = { status: string; kind: string; since: string; until: string };

const BASE = "/api/admin/feedback/";
const ALL = "";
const DATE_LENGTH = 10;
const NO_FILTERS: Filters = { status: ALL, kind: ALL, since: "", until: "" };
const KIND_WORDS: Record<Kind, string> = { bug: "Bug", idea: "Idea", question: "Question" };
const STATUS_WORDS: Record<Status, string> = {
  new: "New",
  reviewing: "Reviewing",
  fixed: "Fixed",
  wont_fix: "Won't fix",
};
const STATUS_TAGS: Record<Status, TagVariant> = {
  new: "warning",
  reviewing: "live",
  fixed: "success",
  wont_fix: "neutral",
};
const STATUSES = Object.keys(STATUS_WORDS) as Status[];
const KINDS = Object.keys(KIND_WORDS) as Kind[];

/** What the companies' people sent through "Send feedback", with a status and a short internal
 * note for each. Both admin roles may read and change it; a status change is audited. */
export function AdminFeedback() {
  const [listing, setListing] = useState<Listing | null>(null);
  const [filters, setFilters] = useState(NO_FILTERS);
  const [open, setOpen] = useState<Item | null>(null);
  const [status, setStatus] = useState<Status>("new");
  const [note, setNote] = useState("");
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    const query = new URLSearchParams(
      Object.entries(filters).filter(([, value]) => value !== ""),
    ).toString();
    const result = await getJson<Listing>(query ? `${BASE}?${query}` : BASE);
    if (result.ok) {
      setListing(result.data);
      setError(null);
    } else setError(result.error);
  }, [filters]);
  useEffect(() => {
    void load();
  }, [load]);

  function show(item: Item) {
    setError(null);
    setStatus(item.status);
    setNote(item.note);
    setOpen(item);
  }

  async function save() {
    if (!open) return;
    setError(null);
    const result = await patchJson<Item>(`${BASE}${open.id}/`, { status, note });
    if (result.ok) return void (await load());
    setError(result.error);
    // The popup closes when confirmed; a refused form comes back with what was typed.
    setOpen(open);
  }

  const fields = error?.fields ?? {};
  const alertText = error && Object.keys(fields).length === 0 ? error.message : null;
  const change = (name: keyof Filters, value: string) => setFilters({ ...filters, [name]: value });

  if (!listing) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  return (
    <div className="page-stack">
      {alertText && (
        <p className="ui-error" role="alert">
          {alertText}
        </p>
      )}
      <div className="page-actions">
        <Select
          label="Status"
          value={filters.status}
          onChange={(event) => change("status", event.target.value)}
          options={[
            { value: ALL, label: "All statuses" },
            ...STATUSES.map((each) => ({ value: each, label: STATUS_WORDS[each] })),
          ]}
        />
        <Select
          label="Kind"
          value={filters.kind}
          onChange={(event) => change("kind", event.target.value)}
          options={[
            { value: ALL, label: "All kinds" },
            ...KINDS.map((each) => ({ value: each, label: KIND_WORDS[each] })),
          ]}
        />
        <Input
          label="From"
          type="date"
          value={filters.since}
          onChange={(event) => change("since", event.target.value)}
        />
        <Input
          label="Until"
          type="date"
          value={filters.until}
          onChange={(event) => change("until", event.target.value)}
        />
      </div>
      {listing.items.length === 0 ? (
        <p role="status">No feedback.</p>
      ) : (
        <>
          <Table label="Feedback">
            <thead>
              <tr>
                <th scope="col">Company</th>
                <th scope="col">User</th>
                <th scope="col">Kind</th>
                <th scope="col">Message</th>
                <th scope="col">Date</th>
                <th scope="col">Status</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {listing.items.map((item) => (
                <tr key={item.id}>
                  <th scope="row">
                    <TextLink href={`/admin/companies/${item.company_id}`}>{item.company}</TextLink>
                  </th>
                  <td>{item.user}</td>
                  <td>{KIND_WORDS[item.kind]}</td>
                  <td>{item.message}</td>
                  <td>{item.created_at.slice(0, DATE_LENGTH)}</td>
                  <td>
                    <Tag variant={STATUS_TAGS[item.status]}>{STATUS_WORDS[item.status]}</Tag>
                  </td>
                  <td>
                    <Button variant="secondary" onClick={() => show(item)}>
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
        title="Update feedback"
        confirmLabel="Save"
        onConfirm={() => void save()}
      >
        <div className="page-stack">
          <Select
            label="Status"
            value={status}
            error={fields.status}
            onChange={(event) => setStatus(event.target.value as Status)}
            options={STATUSES.map((each) => ({ value: each, label: STATUS_WORDS[each] }))}
          />
          <Textarea
            label="Note"
            value={note}
            error={fields.note}
            onChange={(event) => setNote(event.target.value)}
          />
        </div>
      </Dialog>
    </div>
  );
}
