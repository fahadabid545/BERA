"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useCompanyRole } from "@/components/company/role";
import { Button, Card, Dialog } from "@/components/ui";
import { getJson, postJson } from "@/lib/api";
import { navigateTo } from "@/lib/navigation";

const PLANS_URL = "/api/plans/";
const CHECKOUT_URL = "/api/company/billing/checkout/";

type Money = { currency: string; amount: string };
export type SalePlan = {
  id: number;
  name: string;
  price: Money & { note: string | null; approximate: boolean };
  charged: Money;
  cvs_per_month: number | null;
};

const money = ({ currency, amount }: Money) =>
  `${currency} ${Number(amount).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;

/** The plans a company can buy; the owner picks one and pays on the payment provider's own page. */
export function PlanCheckout() {
  const isOwner = useCompanyRole() === "owner";
  const cancelled = useSearchParams().get("checkout") === "cancelled";
  const [plans, setPlans] = useState<SalePlan[]>([]);
  const [chosen, setChosen] = useState<SalePlan | null>(null);
  const [starting, setStarting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    getJson<SalePlan[]>(PLANS_URL).then((result) => {
      if (result.ok) setPlans(result.data);
      else setProblem(result.error.message);
    });
  }, []);

  async function pay(plan: SalePlan) {
    if (starting) return; // a second click while the first is on its way does nothing
    setStarting(true);
    setProblem(null);
    const result = await postJson<{ url: string }>(CHECKOUT_URL, { plan_id: plan.id });
    if (result.ok) return navigateTo(result.data.url);
    setProblem(result.error.message);
    setStarting(false);
  }

  return (
    <div className="page-stack">
      {cancelled && <p role="status">Payment cancelled. Nothing was charged.</p>}
      {problem && <p role="alert">{problem}</p>}
      <div className="page-stack">
        {plans.map((plan) => (
          <Card key={plan.id} aria-label={plan.name}>
            <h2>{plan.name}</h2>
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
            {isOwner && (
              <Button disabled={starting} onClick={() => setChosen(plan)}>
                Choose {plan.name}
              </Button>
            )}
          </Card>
        ))}
      </div>
      <Dialog
        open={chosen !== null}
        onOpenChange={(open) => !open && setChosen(null)}
        title={chosen ? `Pay for ${chosen.name}` : "Pay"}
        confirmLabel="Continue to payment"
        onConfirm={() => chosen && pay(chosen)}
      >
        {chosen && <p>{money(chosen.charged)} per month</p>}
      </Dialog>
    </div>
  );
}
