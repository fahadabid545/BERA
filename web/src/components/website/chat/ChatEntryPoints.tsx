"use client";

import { usePathname } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui";

import { CHAT } from "../content";
import { useChat } from "./ChatProvider";

/** The home page's search bar: one box; sending a question opens the chat with it. */
export function ChatSearchBar() {
  const chat = useChat();
  const [question, setQuestion] = useState("");
  if (!chat.available) return null;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    chat.open(question);
    setQuestion("");
  }

  return (
    <form className="chat-search" onSubmit={submit}>
      <input
        className="chat-search__input"
        aria-label={CHAT.barLabel}
        value={question}
        maxLength={chat.maxQuestionLength}
        autoComplete="off"
        onChange={(event) => setQuestion(event.target.value)}
      />
      <Button type="submit" disabled={!question.trim()}>
        {CHAT.askButton}
      </Button>
    </form>
  );
}

/** The Chat button at the corner of every public page except the home page, which has the bar. */
export function ChatLauncher() {
  const chat = useChat();
  const pathname = usePathname();
  if (!chat.available || pathname === "/") return null;
  return (
    <Button className="chat-launcher" onClick={() => chat.open()}>
      {CHAT.launcher}
    </Button>
  );
}
