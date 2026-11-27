"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Button, Dialog, Textarea } from "@/components/ui";
import { postJson, type ApiError } from "@/lib/api";

import { TicketFacts } from "./TicketFacts";
import { ticketNumber, type TicketSummary } from "./words";

type Line = { role: "user" | "assistant"; text: string };
type Reply = { chat_id: string; reply: string; ticket: TicketSummary | null };

const MESSAGE_LIMIT = 10_000;

/** Talk to the support agent. It answers or asks; when it cannot solve the problem it sends it
 * to the support team as a ticket, and a popup shows the ticket that was requested. */
export function SupportChat() {
  const [lines, setLines] = useState<Line[]>([]);
  const [chatId, setChatId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [ticket, setTicket] = useState<TicketSummary | null>(null);
  const [closed, setClosed] = useState(false);

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    setError(null);
    const result = await postJson<Reply>("/api/company/support/chat/", {
      text,
      ...(chatId ? { chat_id: chatId } : {}),
    });
    setSending(false);
    if (!result.ok) return void setError(result.error);
    setDraft("");
    setChatId(result.data.chat_id);
    setLines((current) => [
      ...current,
      { role: "user", text },
      { role: "assistant", text: result.data.reply },
    ]);
    if (result.data.ticket) {
      setTicket(result.data.ticket);
      setClosed(true);
    }
  }

  function startAgain() {
    setLines([]);
    setChatId(null);
    setClosed(false);
    setTicket(null);
  }

  return (
    <div className="support-chat">
      <Dialog
        open={ticket !== null && closed}
        onOpenChange={(open) => !open && setTicket(null)}
        title="Support ticket requested"
        actions={
          ticket && (
            <Link className="ui-button ui-button--primary" href={`/company/support/${ticket.id}`}>
              View ticket {ticketNumber(ticket.number)}
            </Link>
          )
        }
      >
        {ticket && <TicketFacts ticket={ticket} />}
      </Dialog>
      <ol className="support-chat__lines" aria-label="Conversation" aria-live="polite">
        {lines.map((line, index) => (
          <li key={index} className={`chat-window__message chat-window__message--${line.role}`}>
            <span className="chat-window__who">{line.role === "user" ? "You" : "Support"}</span>
            <p>{line.text}</p>
          </li>
        ))}
        {sending && <li className="chat-window__status">Thinking</li>}
      </ol>
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      {closed ? (
        <Button variant="secondary" onClick={startAgain}>
          Start a new chat
        </Button>
      ) : (
        <form className="support-chat__form" onSubmit={(event) => void send(event)}>
          <Textarea
            label="Describe your problem"
            value={draft}
            maxLength={MESSAGE_LIMIT}
            onChange={(event) => setDraft(event.target.value)}
          />
          <Button type="submit" disabled={!draft.trim() || sending}>
            Send
          </Button>
        </form>
      )}
    </div>
  );
}
