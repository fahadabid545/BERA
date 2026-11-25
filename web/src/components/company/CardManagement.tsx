"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui";
import { getJson, postJson } from "@/lib/api";
import { navigateTo } from "@/lib/navigation";

const CARD_URL = "/api/company/billing/card/";
const OPEN_URL = "/api/company/billing/card/update/";
const CHECK_URL = "/api/company/billing/card/check/";

type Card = { brand: string; last4: string; exp_month: number; exp_year: number };
export type CardResult = "updated" | "not_changed" | "checking" | "none";

const BRANDS: Record<string, string> = {
  visa: "Visa",
  mastercard: "Mastercard",
  amex: "American Express",
  discover: "Discover",
  jcb: "JCB",
  diners: "Diners Club",
  unionpay: "UnionPay",
};
const RESULT_WORDS: Record<CardResult, string | null> = {
  updated: "Card updated",
  not_changed: "Not changed",
  checking: "Checking your card",
  none: null,
};

const describe = (card: Card) =>
  `${BRANDS[card.brand] ?? card.brand} ending ${card.last4}, expires ` +
  `${String(card.exp_month).padStart(2, "0")}/${card.exp_year}`;

/** The card on file (brand, last four digits and expiry, read from the payment provider each time)
 * and the way to change it on the provider's own page. The way back carries only a marker: the
 * result is always asked from the server, which reads it from the provider. */
export function CardManagement({
  returned,
  refreshSeconds,
  onResult,
}: {
  returned: boolean;
  refreshSeconds: number;
  onResult: (result: CardResult) => void;
}) {
  const [card, setCard] = useState<Card | null | undefined>(undefined);
  const [result, setResult] = useState<CardResult | null>(null);
  const [asked, setAsked] = useState(0); // a repeated "checking" must still run the effect again
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const loadCard = useCallback(async () => {
    const reply = await getJson<{ card: Card | null }>(CARD_URL);
    if (reply.ok) setCard(reply.data.card);
    else setProblem(reply.error.message);
  }, []);

  useEffect(() => {
    void loadCard();
  }, [loadCard]);

  useEffect(() => {
    if (!returned || (result !== null && result !== "checking")) return;
    const timer = setTimeout(
      async () => {
        const reply = await postJson<{ result: CardResult }>(CHECK_URL, {});
        const found = reply.ok ? reply.data.result : "none";
        if (!reply.ok) setProblem(reply.error.message);
        setResult(found);
        setAsked((count) => count + 1);
        onResult(found);
        if (found === "updated") void loadCard();
      },
      result === null ? 0 : refreshSeconds * 1000,
    );
    return () => clearTimeout(timer);
  }, [returned, result, asked, refreshSeconds, onResult, loadCard]);

  async function openCardPage() {
    if (busy) return; // a second click while the first is on its way does nothing
    setBusy(true);
    setProblem(null);
    const reply = await postJson<{ url: string }>(OPEN_URL, {});
    setBusy(false);
    if (reply.ok) navigateTo(reply.data.url);
    else setProblem(reply.error.message);
  }

  const resultWords = result ? RESULT_WORDS[result] : null;
  return (
    <div className="page-actions">
      {problem && <p role="alert">{problem}</p>}
      {resultWords && <p role="status">{resultWords}</p>}
      {card !== undefined && <p>{card ? describe(card) : "No card on file"}</p>}
      <Button variant="secondary" disabled={busy} onClick={() => void openCardPage()}>
        Update card
      </Button>
    </div>
  );
}
