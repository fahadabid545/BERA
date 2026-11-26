"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { Button } from "@/components/ui";
import { chatTitle } from "@/lib/publicChat";

import { CHAT } from "../content";
import type { ChatSession } from "./ChatProvider";

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

/** The full-screen chat: previous chats on the left (behind a button on a phone), the
 * conversation on the right and the message box at the bottom. Answers are shown as plain text. */
export function ChatWindow({ session, onClose }: { session: ChatSession; onClose: () => void }) {
  const [draft, setDraft] = useState("");
  const [listOpen, setListOpen] = useState(false);
  const windowRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const active = session.chats.find((chat) => chat.id === session.activeId);

  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    inputRef.current?.focus();
    return () => before?.focus?.();
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [active?.messages.length, session.asking]);

  function keep(event: KeyboardEvent) {
    if (event.key === "Escape") {
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const items = [...(windowRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])];
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const question = draft;
    if (!question.trim() || session.asking) return;
    setDraft("");
    await session.send(question);
    inputRef.current?.focus();
  }

  function choose(action: () => void) {
    action();
    setListOpen(false);
    inputRef.current?.focus();
  }

  return (
    <div className="public-chat__backdrop">
      <div
        ref={windowRef}
        className="public-chat"
        role="dialog"
        aria-modal="true"
        aria-label={CHAT.windowLabel}
        onKeyDown={keep}
      >
        <aside className="public-chat__sidebar" data-open={listOpen}>
          <Button onClick={() => choose(session.startNew)}>{CHAT.newChat}</Button>
          <h2 className="public-chat__heading">{CHAT.chatsHeading}</h2>
          <ul className="public-chat__list">
            {session.chats.map((chat) => (
              <li key={chat.id}>
                <button
                  type="button"
                  className="public-chat__item"
                  aria-current={chat.id === session.activeId ? "true" : undefined}
                  onClick={() => choose(() => session.select(chat.id))}
                >
                  {chatTitle(chat)}
                </button>
              </li>
            ))}
          </ul>
        </aside>
        <section className="public-chat__main">
          <header className="public-chat__bar">
            <Button
              variant="secondary"
              className="public-chat__toggle"
              aria-expanded={listOpen}
              onClick={() => setListOpen((current) => !current)}
            >
              {CHAT.chatsToggle}
            </Button>
            <Button variant="secondary" onClick={onClose}>
              {CHAT.close}
            </Button>
          </header>
          <div className="public-chat__messages" role="log" aria-live="polite">
            {active?.messages.map((message, index) => (
              <div
                key={index}
                className={`public-chat__message public-chat__message--${message.role}`}
              >
                <span className="public-chat__who">
                  {message.role === "user" ? CHAT.you : CHAT.assistant}
                </span>
                <p>{message.text}</p>
              </div>
            ))}
            {session.asking ? <p className="public-chat__status">{CHAT.thinking}</p> : null}
            {session.error ? (
              <p className="public-chat__error" role="alert">
                {session.error}
              </p>
            ) : null}
            <div ref={endRef} />
          </div>
          <form className="public-chat__form" onSubmit={submit}>
            <input
              ref={inputRef}
              className="ui-input"
              aria-label={CHAT.message}
              value={draft}
              maxLength={session.maxQuestionLength}
              autoComplete="off"
              onChange={(event) => setDraft(event.target.value)}
            />
            <Button type="submit" disabled={session.asking || !draft.trim()}>
              {CHAT.send}
            </Button>
          </form>
        </section>
      </div>
    </div>
  );
}
