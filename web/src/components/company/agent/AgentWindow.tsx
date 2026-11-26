"use client";

import { Fragment, useState } from "react";

import { ChatShell } from "@/components/chat/ChatShell";
import { Button, Dialog, TextLink } from "@/components/ui";
import { referenceOf, type AgentMessage, type CandidateCard } from "@/lib/agentChat";

import { AGENT } from "./labels";
import type { AgentSession } from "./AgentProvider";

/** The longest question the window allows; the server's own limit is the one that counts. */
const QUESTION_FIELD_LIMIT = 5000;
const REFERENCE = /\[(c_[0-9a-f]{8})\]/g;

function candidatePage(card: CandidateCard) {
  return `/company/projects/${card.project_id}/candidates/${card.candidate_id}`;
}

/** The answer as plain text, with each candidate it names shown by name and linked to their page.
 * A candidate who no longer exists is shown as removed. */
function AnswerText({ message }: { message: AgentMessage }) {
  const byReference = new Map(
    message.candidates.map((card) => [referenceOf(card.candidate_id), card]),
  );
  const parts = message.text.split(REFERENCE);
  return (
    <p>
      {parts.map((part, index) => {
        if (index % 2 === 0) return <Fragment key={index}>{part}</Fragment>;
        const card = byReference.get(part);
        return card ? (
          <TextLink key={index} href={candidatePage(card)}>
            {card.name || AGENT.unnamed}
          </TextLink>
        ) : (
          <Fragment key={index}>{AGENT.removedCandidate}</Fragment>
        );
      })}
    </p>
  );
}

function CandidateDetails({ card }: { card: CandidateCard }) {
  const facts: [string, string | number | null][] = [
    [AGENT.email, card.email || null],
    [AGENT.phone, card.phone || null],
    [AGENT.experience, card.years_of_experience],
    [AGENT.score, card.score ? `${card.score}${card.grade ? ` (${card.grade})` : ""}` : null],
    [AGENT.ats, card.ats_score],
    [AGENT.stage, card.stage],
    [AGENT.project, card.project_title],
  ];
  return (
    <section className="agent-card" aria-label={card.name || AGENT.unnamed}>
      <TextLink className="agent-card__name" href={candidatePage(card)}>
        {card.name || AGENT.unnamed}
      </TextLink>
      <dl className="agent-card__facts">
        {facts.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value ?? AGENT.notAvailable}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** The company agent's window: the shared chat window with the saved chats of the company,
 * candidate details beside each answer, follow-up suggestions, an incognito switch and delete. */
export function AgentWindow({ session, onClose }: { session: AgentSession; onClose: () => void }) {
  const [deleting, setDeleting] = useState<{ id: string; title: string } | null>(null);
  const last = session.messages.length - 1;
  return (
    <>
      <ChatShell
        labels={AGENT}
        items={session.chats.map((chat) => ({
          id: chat.id,
          title: chat.title,
          current: chat.id === session.activeId && !session.incognito,
          onDelete: () => setDeleting({ id: chat.id, title: chat.title }),
        }))}
        deleteLabel={AGENT.delete}
        onNewChat={() => session.startNew()}
        onSelect={(id) => void session.select(id)}
        onClose={onClose}
        onSend={(text) => session.send(text)}
        asking={session.asking}
        maxLength={QUESTION_FIELD_LIMIT}
        scrollKey={session.messages.length}
        toolbar={
          <Button
            variant="secondary"
            aria-pressed={session.incognito}
            onClick={() => session.startNew(!session.incognito)}
          >
            {session.incognito ? AGENT.incognitoOn : AGENT.incognito}
          </Button>
        }
      >
        {session.messages.map((message, index) => (
          <div
            key={index}
            className={`chat-window__message chat-window__message--${message.role}`}
            data-problem={message.problem ? "true" : undefined}
          >
            <span className="chat-window__who">
              {message.role === "user" ? AGENT.you : AGENT.assistant}
            </span>
            {message.role === "assistant" && !message.problem ? (
              <AnswerText message={message} />
            ) : (
              <p>{message.text}</p>
            )}
            {message.candidates.map((card) => (
              <CandidateDetails key={card.candidate_id} card={card} />
            ))}
            {index === last && !session.asking && message.suggestions.length > 0 ? (
              <div className="agent-suggestions">
                {message.suggestions.map((suggestion) => (
                  <Button
                    key={suggestion}
                    variant="secondary"
                    onClick={() => void session.send(suggestion)}
                  >
                    {suggestion}
                  </Button>
                ))}
              </div>
            ) : null}
          </div>
        ))}
        {session.asking ? <p className="chat-window__status">{AGENT.thinking}</p> : null}
        {session.error ? (
          <p className="chat-window__error" role="alert">
            {session.error}
          </p>
        ) : null}
      </ChatShell>
      <Dialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={AGENT.deleteTitle}
        confirmLabel={AGENT.deleteConfirm}
        destructive
        onConfirm={() => {
          if (deleting) void session.remove(deleting.id);
        }}
      >
        <p>{deleting?.title}</p>
      </Dialog>
    </>
  );
}
