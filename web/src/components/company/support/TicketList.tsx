"use client";

import { useEffect, useState } from "react";

import { EmptyState, Table, Tag, TextLink } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

import {
  CATEGORY_WORDS,
  STATUS_TAGS,
  STATUS_WORDS,
  ticketNumber,
  when,
  type TicketSummary,
} from "./words";

/** The person's tickets (every ticket of the company, for its owner) with their status. */
export function TicketList() {
  const [tickets, setTickets] = useState<TicketSummary[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    void getJson<{ tickets: TicketSummary[] }>("/api/company/support/tickets/").then((result) => {
      if (result.ok) setTickets(result.data.tickets);
      else setError(result.error);
    });
  }, []);
  if (error) {
    return (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    );
  }
  if (!tickets) return null;
  if (tickets.length === 0) return <EmptyState role="status">No tickets yet.</EmptyState>;
  return (
    <Table label="Tickets">
      <thead>
        <tr>
          <th scope="col">Ticket</th>
          <th scope="col">Title</th>
          <th scope="col">Category</th>
          <th scope="col">Status</th>
          <th scope="col">Last update</th>
        </tr>
      </thead>
      <tbody>
        {tickets.map((ticket) => (
          <tr key={ticket.id}>
            <td>{ticketNumber(ticket.number)}</td>
            <td>
              <TextLink href={`/company/support/${ticket.id}`}>{ticket.title}</TextLink>
            </td>
            <td>{CATEGORY_WORDS[ticket.category]}</td>
            <td>
              <Tag variant={STATUS_TAGS[ticket.status]}>{STATUS_WORDS[ticket.status]}</Tag>
            </td>
            <td>{when(ticket.updated_at)}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
