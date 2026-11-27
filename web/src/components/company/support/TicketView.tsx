"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Button, TextLink, Textarea } from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";

import { TicketFacts } from "./TicketFacts";
import { when, type TicketDetail } from "./words";

const AUTHORS = { user: "You", admin: "Support team", system: "Status" } as const;
const MESSAGE_LIMIT = 10_000;

/** One ticket: what the agent wrote, the conversation with the team and a box to answer. A
 * closed ticket takes no more answers. */
export function TicketView({ id }: { id: string }) {
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    const result = await getJson<TicketDetail>(`/api/company/support/tickets/${id}/`);
    if (result.ok) {
      setTicket(result.data);
      setError(null);
    } else setError(result.error);
  }, [id]);
  useEffect(() => {
    void load();
  }, [load]);

  async function reply(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim() || sending) return;
    setSending(true);
    const result = await postJson<TicketDetail>(`/api/company/support/tickets/${id}/`, {
      text: draft.trim(),
    });
    setSending(false);
    if (result.ok) {
      setTicket(result.data);
      setDraft("");
      setError(null);
    } else setError(result.error);
  }

  if (!ticket) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  return (
    <div className="page-stack">
      <TextLink href="/company/support?tab=tickets">Back to tickets</TextLink>
      <TicketFacts ticket={ticket} />
      <ol className="ticket-messages" aria-label="Conversation">
        {ticket.messages.map((message) => (
          <li
            key={message.id}
            className={`ticket-messages__item ticket-messages__item--${message.author}`}
          >
            <span className="ticket-messages__who">
              {AUTHORS[message.author]} · {when(message.created_at)}
            </span>
            <p>{message.text}</p>
          </li>
        ))}
      </ol>
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      {ticket.status !== "closed" && (
        <form className="support-chat__form" onSubmit={(event) => void reply(event)}>
          <Textarea
            label="Your reply"
            value={draft}
            maxLength={MESSAGE_LIMIT}
            onChange={(event) => setDraft(event.target.value)}
          />
          <Button type="submit" disabled={!draft.trim() || sending}>
            Send reply
          </Button>
        </form>
      )}
    </div>
  );
}
