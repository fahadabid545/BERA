"use client";

import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui";

import { useAgent } from "./AgentProvider";
import { AGENT, AGENT_SUGGESTIONS } from "./labels";

const SUGGESTION_SECONDS = 4;

/** The talk bar at the top of every page of the company panel: sending a question opens the
 * agent's window with it. */
export function AgentBar() {
  const agent = useAgent();
  const [question, setQuestion] = useState("");
  const [suggestion, setSuggestion] = useState(0);

  // The suggestion changes by itself while nothing is typed.
  useEffect(() => {
    if (question) return;
    const timer = setInterval(
      () => setSuggestion((current) => (current + 1) % AGENT_SUGGESTIONS.length),
      SUGGESTION_SECONDS * 1000,
    );
    return () => clearInterval(timer);
  }, [question]);

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
        placeholder={AGENT_SUGGESTIONS[suggestion]}
        autoComplete="off"
        onChange={(event) => setQuestion(event.target.value)}
      />
      <Button type="submit" disabled={!question.trim()}>
        {AGENT.askButton}
      </Button>
    </form>
  );
}
