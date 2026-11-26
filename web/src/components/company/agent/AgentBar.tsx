"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui";

import { useAgent } from "./AgentProvider";
import { AGENT } from "./labels";

/** The talk bar at the top of every page of the company panel: sending a question opens the
 * agent's window with it. */
export function AgentBar() {
  const agent = useAgent();
  const [question, setQuestion] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    agent.open(question);
    setQuestion("");
  }

  return (
    <form className="chat-search" onSubmit={submit}>
      <input
        className="chat-search__input"
        aria-label={AGENT.barLabel}
        value={question}
        autoComplete="off"
        onChange={(event) => setQuestion(event.target.value)}
      />
      <Button type="submit" disabled={!question.trim()}>
        {AGENT.askButton}
      </Button>
    </form>
  );
}
