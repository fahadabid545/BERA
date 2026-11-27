"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { TicketFacts } from "@/components/company/support/TicketFacts";
import {
  CATEGORY_WORDS,
  STATUS_TAGS,
  STATUS_WORDS,
  ticketNumber,
  when,
  type TicketCategory,
  type TicketDetail,
  type TicketStatus,
  type TicketSummary,
} from "@/components/company/support/words";
import { Button, Dialog, Select, Table, Tag, Textarea, TextLink } from "@/components/ui";
import { getJson, patchJson, type ApiError } from "@/lib/api";

type Item = TicketSummary & { company_id: number; company: string; user: string };
type Listing = { total: number; open_count: number; items: Item[] };
type AdminDetail = TicketDetail & {
  company_id: number;
  company: string;
  user: string;
  handled_by: string | null;
};

const BASE = "/api/admin/support/tickets/";
const ALL = "";
const STATUSES = Object.keys(STATUS_WORDS) as TicketStatus[];
const CATEGORIES = Object.keys(CATEGORY_WORDS) as TicketCategory[];
const MESSAGE_LIMIT = 10_000;
const AUTHORS = { user: "Person", admin: "Support team", system: "Status" } as const;
// The statuses an admin may set; the person's reply and the team's question move "needs reply".
const KEEP = "keep";

/** The tickets the support agent handed over. Without a status chosen the list is every ticket
 * still in hand; an admin reads one, asks the person something, works on it and sets its status. */
export function AdminSupport() {
  const [listing, setListing] = useState<Listing | null>(null);
  const [status, setStatus] = useState(ALL);
  const [category, setCategory] = useState(ALL);
  const [error, setError] = useState<ApiError | null>(null);
  const [ticket, setTicket] = useState<AdminDetail | null>(null);
  const [message, setMessage] = useState("");
  const [next, setNext] = useState<string>(KEEP);

  const load = useCallback(async () => {
    const query = new URLSearchParams();
    if (status) query.set("status", status);
    if (category) query.set("category", category);
    const result = await getJson<Listing>(query.size ? `${BASE}?${query}` : BASE);
    if (result.ok) {
      setListing(result.data);
      setError(null);
    } else setError(result.error);
  }, [status, category]);
  useEffect(() => {
    void load();
  }, [load]);

  async function read(item: Item) {
    const result = await getJson<AdminDetail>(`${BASE}${item.id}/`);
    if (!result.ok) return void setError(result.error);
    setError(null);
    setMessage("");
    setNext(KEEP);
    setTicket(result.data);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!ticket) return;
    const body: Record<string, string> = {};
    if (message.trim()) body.message = message.trim();
    if (next !== KEEP) body.status = next;
    const result = await patchJson<AdminDetail>(`${BASE}${ticket.id}/`, body);
    if (!result.ok) return void setError(result.error);
    setError(null);
    setTicket(result.data);
    setMessage("");
    setNext(KEEP);
    await load();
  }

  const fields = error?.fields ?? {};
  const alertText = error && Object.keys(fields).length === 0 ? error.message : null;
  if (!listing) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  return (
    <div className="page-stack">
      {alertText && !ticket && (
        <p className="ui-error" role="alert">
          {alertText}
        </p>
      )}
      <div className="page-actions">
        <Select
          label="Status"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          options={[
            { value: ALL, label: "In hand" },
            ...STATUSES.map((each) => ({ value: each, label: STATUS_WORDS[each] })),
          ]}
        />
        <Select
          label="Category"
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          options={[
            { value: ALL, label: "All categories" },
            ...CATEGORIES.map((each) => ({ value: each, label: CATEGORY_WORDS[each] })),
          ]}
        />
      </div>
      {listing.items.length === 0 ? (
        <p role="status">No tickets.</p>
      ) : (
        <>
          <Table label="Support tickets">
            <thead>
              <tr>
                <th scope="col">Ticket</th>
                <th scope="col">Title</th>
                <th scope="col">Company</th>
                <th scope="col">User</th>
                <th scope="col">Category</th>
                <th scope="col">Status</th>
                <th scope="col">Last update</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {listing.items.map((item) => (
                <tr key={item.id}>
                  <th scope="row">{ticketNumber(item.number)}</th>
                  <td>{item.title}</td>
                  <td>
                    <TextLink href={`/admin/companies/${item.company_id}`}>{item.company}</TextLink>
                  </td>
                  <td>{item.user}</td>
                  <td>{CATEGORY_WORDS[item.category]}</td>
                  <td>
                    <Tag variant={STATUS_TAGS[item.status]}>{STATUS_WORDS[item.status]}</Tag>
                  </td>
                  <td>{when(item.updated_at)}</td>
                  <td>
                    <Button variant="secondary" onClick={() => void read(item)}>
                      Open
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
          <p role="status">
            Showing {listing.items.length} of {listing.total}. {listing.open_count} not yet picked
            up.
          </p>
        </>
      )}
      <Dialog
        open={ticket !== null}
        onOpenChange={(open) => {
          if (!open) setTicket(null);
        }}
        title={ticket ? `Ticket ${ticketNumber(ticket.number)}` : "Ticket"}
      >
        {ticket && (
          <div className="page-stack">
            <p>
              {ticket.company} · {ticket.user}
              {ticket.handled_by ? ` · Handled by ${ticket.handled_by}` : ""}
            </p>
            <TicketFacts ticket={ticket} />
            <ol className="ticket-messages" aria-label="Conversation">
              {ticket.messages.map((item) => (
                <li
                  key={item.id}
                  className={`ticket-messages__item ticket-messages__item--${item.author}`}
                >
                  <span className="ticket-messages__who">
                    {AUTHORS[item.author]} · {when(item.created_at)}
                  </span>
                  <p>{item.text}</p>
                </li>
              ))}
            </ol>
            {alertText && (
              <p className="ui-error" role="alert">
                {alertText}
              </p>
            )}
            <form className="support-chat__form" onSubmit={(event) => void save(event)}>
              <Textarea
                label="Message to the person"
                value={message}
                maxLength={MESSAGE_LIMIT}
                error={fields.message}
                onChange={(event) => setMessage(event.target.value)}
              />
              <Select
                label="Set status"
                value={next}
                error={fields.status}
                onChange={(event) => setNext(event.target.value)}
                options={[
                  { value: KEEP, label: message.trim() ? "Waiting for a reply" : "Keep as it is" },
                  ...STATUSES.filter((each) => each !== ticket.status).map((each) => ({
                    value: each,
                    label: STATUS_WORDS[each],
                  })),
                ]}
              />
              <Button type="submit" disabled={!message.trim() && next === KEEP}>
                Save
              </Button>
            </form>
          </div>
        )}
      </Dialog>
    </div>
  );
}
