"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { CardManagement, type CardResult } from "@/components/company/CardManagement";
import { useCompanyRole } from "@/components/company/role";
import { Button, Card, Dialog, Tag } from "@/components/ui";
import { getJson, postJson } from "@/lib/api";
import { money, type Money } from "@/lib/money";
import { navigateTo } from "@/lib/navigation";

const PLANS_URL = "/api/plans/";
const CHECKOUT_URL = "/api/company/billing/checkout/";
const USAGE_URL = "/api/company/usage/";
const CHANGE_URL = "/api/company/billing/change-plan/";
const CANCEL_DOWNGRADE_URL = "/api/company/billing/change-plan/cancel/";
const CANCEL_SUBSCRIPTION_URL = "/api/company/billing/cancel/";
const RESUME_SUBSCRIPTION_URL = "/api/company/billing/resume/";
const PORTAL_URL = "/api/company/billing/portal/";

export type SalePlan = {
  id: number;
  name: string;
  price: Money & { note: string | null; approximate: boolean };
  charged: Money;
  cvs_per_month: number | null;
};

type PendingChange = {
  kind: "upgrade" | "downgrade";
  plan_id: number;
  plan_name: string;
  takes_effect: string | null;
  processing: boolean;
};
type Billing = {
  state: string;
  plan_id: number | null;
  renewal: boolean;
  can_manage_billing: boolean;
  period_end: string | null;
  grace_ends_at: string | null;
  pending_change: PendingChange | null;
  refresh_seconds: number;
};
type ChangeReply = { result: string; url: string | null };

const day = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", { dateStyle: "medium", timeZone: "UTC" });

/** The plans a company can buy, and, for a company that already has one, the way to change it:
 * an upgrade is charged now and shows as processing until the payment is confirmed; a downgrade
 * waits for the next renewal. Card details are only ever typed on the provider's own page. */
export function PlanCheckout() {
  const isOwner = useCompanyRole() === "owner";
  const query = useSearchParams();
  const cancelled = query.get("checkout") === "cancelled";
  const cameBackFromPortal = query.get("portal") === "returned";
  const cameBackFromCard = query.get("card") === "returned";
  const [plans, setPlans] = useState<SalePlan[]>([]);
  const [billing, setBilling] = useState<Billing | null>(null);
  const [chosen, setChosen] = useState<SalePlan | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [cardResult, setCardResult] = useState<CardResult | null>(null);

  const loadBilling = useCallback(async () => {
    const result = await getJson<Billing>(USAGE_URL);
    if (result.ok) setBilling(result.data);
  }, []);

  useEffect(() => {
    getJson<SalePlan[]>(PLANS_URL).then((result) => {
      if (result.ok) setPlans(result.data);
      else setProblem(result.error.message);
    });
    if (isOwner) void loadBilling();
  }, [isOwner, loadBilling]);

  const processing = billing?.pending_change?.processing ?? false;
  // Access returns only when the provider's paid notice arrives, never because of the return trip.
  const paymentProcessing =
    (cameBackFromPortal || cardResult === "updated") && billing?.state === "past_due";
  const waitingForNotice = processing || paymentProcessing;
  useEffect(() => {
    if (!waitingForNotice || !billing) return;
    const timer = setTimeout(() => void loadBilling(), billing.refresh_seconds * 1000);
    return () => clearTimeout(timer);
  }, [waitingForNotice, billing, loadBilling]);

  const subscribed = billing?.state === "active" && billing.plan_id !== null;
  const currentPlan = plans.find((plan) => plan.id === billing?.plan_id);
  const dearer = (plan: SalePlan) =>
    currentPlan !== undefined && Number(plan.charged.amount) > Number(currentPlan.charged.amount);

  async function send<T>(
    request: () => Promise<{ ok: true; data: T } | { ok: false; error: { message: string } }>,
  ) {
    if (busy) return null; // a second click while the first is on its way does nothing
    setBusy(true);
    setProblem(null);
    const result = await request();
    setBusy(false);
    if (!result.ok) {
      setProblem(result.error.message);
      return null;
    }
    return result.data;
  }

  async function pay(plan: SalePlan) {
    const reply = await send(() => postJson<{ url: string }>(CHECKOUT_URL, { plan_id: plan.id }));
    if (reply) navigateTo(reply.url);
  }

  async function change(plan: SalePlan) {
    setChosen(null);
    const reply = await send(() => postJson<ChangeReply>(CHANGE_URL, { plan_id: plan.id }));
    if (!reply) return;
    if (reply.url) return navigateTo(reply.url);
    await loadBilling();
  }

  async function takeDowngradeBack() {
    const reply = await send(() => postJson<{ result: string }>(CANCEL_DOWNGRADE_URL, {}));
    if (reply) await loadBilling();
  }

  async function stopRenewal() {
    const reply = await send(() => postJson<{ result: string }>(CANCEL_SUBSCRIPTION_URL, {}));
    if (reply) await loadBilling();
  }

  async function resumeRenewal() {
    const reply = await send(() => postJson<{ result: string }>(RESUME_SUBSCRIPTION_URL, {}));
    if (reply) await loadBilling();
  }

  async function openPortal() {
    const reply = await send(() => postJson<{ url: string }>(PORTAL_URL, {}));
    if (reply) navigateTo(reply.url);
  }

  const state = billing?.state;
  const canPick = billing === null || ["no_plan", "expired", "active"].includes(billing.state);
  const waiting = billing?.pending_change ?? null;
  const chooseLabel = (plan: SalePlan) =>
    !subscribed ? "Choose" : dearer(plan) ? "Upgrade to" : "Downgrade to";

  return (
    <div className="page-stack">
      {cancelled && <p role="status">Payment cancelled. Nothing was charged.</p>}
      {problem && <p role="alert">{problem}</p>}
      {paymentProcessing && <p role="status">Payment processing</p>}
      {state === "past_due" && !paymentProcessing && (
        <p role="status">
          Payment failed
          {billing?.grace_ends_at ? `. Full access until ${day(billing.grace_ends_at)}` : ""}
        </p>
      )}
      {state === "cancelled" && (
        <p role="status">
          Cancelled{billing?.period_end ? `. Access until ${day(billing.period_end)}` : ""}
        </p>
      )}
      {isOwner && billing && (
        <div className="page-actions">
          {state === "active" && billing.renewal && (
            <Button variant="secondary" disabled={busy} onClick={() => setStopping(true)}>
              Cancel subscription
            </Button>
          )}
          {state === "cancelled" && (
            <Button disabled={busy} onClick={() => void resumeRenewal()}>
              Resume subscription
            </Button>
          )}
          {billing.can_manage_billing && (
            <Button variant="secondary" disabled={busy} onClick={() => void openPortal()}>
              Manage billing
            </Button>
          )}
        </div>
      )}
      {isOwner && billing?.can_manage_billing && (
        <CardManagement
          returned={cameBackFromCard}
          refreshSeconds={billing.refresh_seconds}
          onResult={setCardResult}
        />
      )}
      {waiting?.kind === "upgrade" && (
        <p role="status">
          Upgrade to {waiting.plan_name}: {waiting.processing ? "processing" : "not confirmed yet"}
        </p>
      )}
      {waiting?.kind === "downgrade" && (
        <div className="page-actions">
          <p role="status">
            Downgrade to {waiting.plan_name} on{" "}
            {waiting.takes_effect ? day(waiting.takes_effect) : "renewal"}
          </p>
          {isOwner && (
            <Button variant="secondary" disabled={busy} onClick={() => setCancelling(true)}>
              Cancel downgrade
            </Button>
          )}
        </div>
      )}
      <div className="page-stack">
        {plans.map((plan) => (
          <Card key={plan.id} aria-label={plan.name}>
            <h2>
              {plan.name}{" "}
              {subscribed && plan.id === billing?.plan_id && (
                <Tag variant="neutral">Current plan</Tag>
              )}
            </h2>
            <p>
              {plan.price.approximate
                ? `About ${money(plan.price)} per month`
                : `${money(plan.price)} per month`}
            </p>
            {plan.price.approximate && (
              <p>
                {plan.price.note} Charged: {money(plan.charged)} per month
              </p>
            )}
            {isOwner && canPick && !(subscribed && plan.id === billing?.plan_id) && (
              <Button
                disabled={busy || processing || (subscribed && waiting?.plan_id === plan.id)}
                onClick={() => setChosen(plan)}
              >
                {chooseLabel(plan)} {plan.name}
              </Button>
            )}
          </Card>
        ))}
      </div>
      <Dialog
        open={chosen !== null}
        onOpenChange={(open) => !open && setChosen(null)}
        title={chosen ? `${chooseLabel(chosen)} ${chosen.name}` : "Choose a plan"}
        confirmLabel={
          chosen && subscribed ? (dearer(chosen) ? "Upgrade" : "Downgrade") : "Continue to payment"
        }
        onConfirm={() => chosen && (subscribed ? change(chosen) : pay(chosen))}
      >
        {chosen && <p>{money(chosen.charged)} per month</p>}
      </Dialog>
      <Dialog
        open={stopping}
        onOpenChange={setStopping}
        title="Cancel subscription"
        confirmLabel="Cancel subscription"
        onConfirm={() => void stopRenewal()}
      />
      <Dialog
        open={cancelling}
        onOpenChange={setCancelling}
        title="Cancel downgrade"
        confirmLabel="Cancel downgrade"
        onConfirm={() => void takeDowngradeBack()}
      />
    </div>
  );
}
