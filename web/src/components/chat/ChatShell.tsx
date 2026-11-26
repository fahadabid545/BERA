"use client";

import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import { Button } from "@/components/ui";

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

export type ShellLabels = {
  windowLabel: string;
  newChat: string;
  chatsHeading: string;
  chatsToggle: string;
  message: string;
  send: string;
  close: string;
};

export type ShellItem = { id: string; title: string; current: boolean; onDelete?: () => void };

/** The full-screen chat window both chats share: earlier chats on the left (behind a button on a
 * phone), the conversation on the right and the message box at the bottom. What the
 * conversation shows is given as `children`. */
export function ChatShell({
  labels,
  items,
  onNewChat,
  onSelect,
  onClose,
  onSend,
  asking,
  maxLength,
  toolbar,
  deleteLabel,
  scrollKey,
  children,
}: {
  labels: ShellLabels;
  items: ShellItem[];
  onNewChat: () => void;
  onSelect: (id: string) => void;
  onClose: () => void;
  onSend: (text: string) => Promise<void>;
  asking: boolean;
  maxLength: number;
  toolbar?: ReactNode;
  /** The word on each chat's delete button, when chats can be deleted. */
  deleteLabel?: string;
  /** Changes when the conversation grows, so the view scrolls to its end. */
  scrollKey: number;
  children: ReactNode;
}) {
  const [draft, setDraft] = useState("");
  const [listOpen, setListOpen] = useState(false);
  const windowRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    inputRef.current?.focus();
    return () => before?.focus?.();
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [scrollKey, asking]);

  function keep(event: KeyboardEvent) {
    // A popup opened from here (a confirmation) is outside the window and handles its own keys.
    if (!windowRef.current?.contains(event.target as Node)) return;
    if (event.key === "Escape") {
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = [...windowRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
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
    const text = draft;
    if (!text.trim() || asking) return;
    setDraft("");
    await onSend(text);
    inputRef.current?.focus();
  }

  function choose(action: () => void) {
    action();
    setListOpen(false);
    inputRef.current?.focus();
  }

  return (
    <div className="chat-window__backdrop">
      <div
        ref={windowRef}
        className="chat-window"
        role="dialog"
        aria-modal="true"
        aria-label={labels.windowLabel}
        onKeyDown={keep}
      >
        <aside className="chat-window__sidebar" data-open={listOpen}>
          <Button onClick={() => choose(onNewChat)}>{labels.newChat}</Button>
          <h2 className="chat-window__heading">{labels.chatsHeading}</h2>
          <ul className="chat-window__list">
            {items.map((item) => (
              <li key={item.id} className="chat-window__row">
                <button
                  type="button"
                  className="chat-window__item"
                  aria-current={item.current ? "true" : undefined}
                  onClick={() => choose(() => onSelect(item.id))}
                >
                  {item.title}
                </button>
                {item.onDelete && deleteLabel ? (
                  <button
                    type="button"
                    className="chat-window__delete"
                    aria-label={`${deleteLabel} ${item.title}`}
                    onClick={item.onDelete}
                  >
                    {deleteLabel}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </aside>
        <section className="chat-window__main">
          <header className="chat-window__bar">
            <Button
              variant="secondary"
              className="chat-window__toggle"
              aria-expanded={listOpen}
              onClick={() => setListOpen((current) => !current)}
            >
              {labels.chatsToggle}
            </Button>
            {toolbar}
            <Button variant="secondary" onClick={onClose}>
              {labels.close}
            </Button>
          </header>
          <div className="chat-window__messages" role="log" aria-live="polite">
            {children}
            <div ref={endRef} />
          </div>
          <form className="chat-window__form" onSubmit={submit}>
            <input
              ref={inputRef}
              className="ui-input"
              aria-label={labels.message}
              value={draft}
              maxLength={maxLength}
              autoComplete="off"
              onChange={(event) => setDraft(event.target.value)}
            />
            <Button type="submit" disabled={asking || !draft.trim()}>
              {labels.send}
            </Button>
          </form>
        </section>
      </div>
    </div>
  );
}
