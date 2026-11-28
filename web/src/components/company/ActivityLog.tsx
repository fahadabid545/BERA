"use client";

import { useEffect, useState } from "react";

import { Button, Card, Input, Select, Table, TextLink } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

type Entry = {
  id: string;
  kind: string;
  actor_name: string;
  target_kind: string;
  target_id: string;
  details: Record<string, string | number | boolean | null>;
  created_at: string;
};
type Person = { id: number; name: string };
type Answer = { entries: Entry[]; next_before: string | null; people: Person[] };
type Filters = { actor: string; since: string; until: string };

const NO_FILTERS: Filters = { actor: "", since: "", until: "" };
const MINUTE_LENGTH = 16;

const when = (iso: string) => iso.slice(0, MINUTE_LENGTH).replace("T", " ");
const count = (value: unknown, one: string, many: string) => `${value} ${value === 1 ? one : many}`;

/** The sentence for an entry. The log keeps short facts only, so each kind says what it can. */
export function sentence(entry: Entry): string {
  const { details } = entry;
  switch (entry.kind) {
    case "upload":
      return "Uploaded CVs";
    case "stage_change":
      return "Changed a candidate's stage";
    case "download":
      if (details.scope === "package")
        return `Downloaded a zip of ${count(details.files, "CV", "CVs")}`;
      if (details.scope === "list")
        return `Downloaded the ranked list as ${details.format === "pdf" ? "a PDF" : "a spreadsheet"}`;
      return "Downloaded a CV";
    case "share":
      return details.action === "revoked" ? "Revoked a report link" : "Made a report link";
    case "invite_sent":
      return "Invited a member";
    case "invite_resent":
      return "Sent an invitation again";
    case "invite_revoked":
      return "Revoked an invitation";
    case "invite_accepted":
      return "Accepted an invitation";
    case "project_deleted":
      return "Deleted a project";
    case "member_removed":
      return `Removed ${details.removed_name ?? "a member"} from the team`;
    case "ownership_transferred":
      return `Handed ownership to ${details.new_owner_name ?? "another member"}`;
    case "project_owner_changed":
      return `Handed a project to ${details.new_owner_name ?? "another member"}`;
    case "setting_changed":
      return "Changed a setting";
    case "candidate_deleted":
      return "Deleted a candidate";
    case "data_expired":
      return `Deleted ${count(details.files, "CV", "CVs")} past the retention period`;
    default:
      return entry.kind.replace(/_/g, " ");
  }
}

function query(filters: Filters, before: string | null) {
  const params = new URLSearchParams();
  if (filters.actor) params.set("actor", filters.actor);
  if (filters.since) params.set("since", filters.since);
  if (filters.until) params.set("until", filters.until);
  if (before) params.set("before", before);
  const text = params.toString();
  return `/api/company/activity/${text ? `?${text}` : ""}`;
}

/** The company's activity log, newest first, a page at a time, with filters by person and day.
 * Only the owner may read it: for anyone else the server refuses and nothing is shown. */
export function ActivityLog() {
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [refused, setRefused] = useState(false);

  useEffect(() => {
    let current = true;
    void getJson<Answer>(query(filters, null)).then((result) => {
      if (!current) return;
      if (result.ok) {
        setEntries(result.data.entries);
        setNext(result.data.next_before);
        setPeople(result.data.people);
        setError(null);
      } else if (result.error.code === "not_allowed") {
        setRefused(true);
      } else setError(result.error);
    });
    return () => {
      current = false;
    };
  }, [filters]);

  async function older() {
    const result = await getJson<Answer>(query(filters, next));
    if (!result.ok) return setError(result.error);
    setEntries((shown) => [...(shown ?? []), ...result.data.entries]);
    setNext(result.data.next_before);
  }

  if (refused || (entries === null && !error)) return null;
  const change = (patch: Partial<Filters>) => setFilters((current) => ({ ...current, ...patch }));
  return (
    <Card className="ui-card">
      <h2>Activity log</h2>
      <div className="page-actions">
        <Select
          label="Person"
          value={filters.actor}
          onChange={(event) => change({ actor: event.target.value })}
          options={[
            { value: "", label: "Everyone" },
            ...people.map((person) => ({ value: String(person.id), label: person.name })),
          ]}
        />
        <Input
          label="From"
          type="date"
          value={filters.since}
          onChange={(event) => change({ since: event.target.value })}
        />
        <Input
          label="To"
          type="date"
          value={filters.until}
          onChange={(event) => change({ until: event.target.value })}
        />
        <Button variant="secondary" onClick={() => setFilters(NO_FILTERS)}>
          Clear filters
        </Button>
      </div>
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      {entries && entries.length === 0 ? (
        <p role="status">No activity matches these filters.</p>
      ) : (
        entries && (
          <Table label="Activity log">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Person</th>
                <th scope="col">Activity</th>
                <th scope="col">
                  <span className="visually-hidden">Link</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id}>
                  <td>{when(entry.created_at)}</td>
                  <td>{entry.actor_name || "System"}</td>
                  <td>{sentence(entry)}</td>
                  <td>
                    {entry.target_kind === "project" && entry.kind !== "project_deleted" && (
                      <TextLink href={`/company/projects/${entry.target_id}`}>
                        Open project
                      </TextLink>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )
      )}
      {next && (
        <Button variant="secondary" onClick={() => void older()}>
          Older
        </Button>
      )}
    </Card>
  );
}
