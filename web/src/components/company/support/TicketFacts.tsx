import { Tag } from "@/components/ui";

import {
  CATEGORY_WORDS,
  STATUS_TAGS,
  STATUS_WORDS,
  ticketNumber,
  when,
  type TicketDetail,
  type TicketSummary,
} from "./words";

/** The ticket as the support agent wrote it: number, status and the parts, in the same order
 * every time, so the team and the person read the same thing. */
export function TicketFacts({ ticket }: { ticket: TicketSummary | TicketDetail }) {
  const parts: [string, string][] =
    "summary" in ticket
      ? [
          ["Summary", ticket.summary],
          ["What happened", ticket.what_happened],
          ["What you expected", ticket.expected],
          ["Steps to repeat it", ticket.steps],
        ]
      : [];
  return (
    <div className="ticket-facts">
      <p className="ticket-facts__head">
        <strong>{ticketNumber(ticket.number)}</strong>
        <Tag variant={STATUS_TAGS[ticket.status]}>{STATUS_WORDS[ticket.status]}</Tag>
        <Tag variant="neutral">{CATEGORY_WORDS[ticket.category]}</Tag>
      </p>
      <h3 className="ticket-facts__title">{ticket.title}</h3>
      <p className="ticket-facts__when">Opened {when(ticket.created_at)}</p>
      <dl className="ticket-facts__parts">
        {parts
          .filter(([, text]) => text)
          .map(([label, text]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{text}</dd>
            </div>
          ))}
      </dl>
    </div>
  );
}
