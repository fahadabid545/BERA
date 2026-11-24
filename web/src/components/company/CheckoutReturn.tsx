"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { BILLING_HREF } from "@/components/company/links";
import { Button, ButtonLink } from "@/components/ui";
import { postJson } from "@/lib/api";

const CONFIRM_URL = "/api/company/billing/checkout/confirm/";

const WORDS: Record<string, string> = {
  activated: "Your plan is active.",
  pending: "Your payment is not confirmed yet.",
  cancelled: "Payment cancelled. Nothing was charged.",
  closed: "This payment page was closed. Nothing was charged.",
};

/** Where the payment page sends the person back to. It never trusts the address: the server asks
 * the payment provider whether the payment went through. */
export function CheckoutReturn() {
  const sessionId = useSearchParams().get("session_id");
  const [outcome, setOutcome] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const check = useCallback(async () => {
    if (!sessionId) return setOutcome("cancelled");
    setProblem(null);
    const result = await postJson<{ result: string }>(CONFIRM_URL, { session_id: sessionId });
    if (result.ok) setOutcome(result.data.result);
    else setProblem(result.error.message);
  }, [sessionId]);

  useEffect(() => {
    // The server settles the payment once, so opening this page again is harmless.
    void check();
  }, [check]);

  return (
    <div className="page-stack">
      {problem && <p role="alert">{problem}</p>}
      {outcome && <p role="status">{WORDS[outcome] ?? WORDS.pending}</p>}
      <div className="page-actions">
        {outcome === "pending" && <Button onClick={check}>Check again</Button>}
        {(outcome !== null || problem !== null) && (
          <ButtonLink href={BILLING_HREF} variant="secondary">
            Back to billing
          </ButtonLink>
        )}
      </div>
    </div>
  );
}
