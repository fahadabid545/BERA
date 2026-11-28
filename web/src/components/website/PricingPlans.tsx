"use client";

import { useEffect, useState } from "react";

import { ButtonLink, Card } from "@/components/ui";
import { getJson } from "@/lib/api";
import { money, type Money } from "@/lib/money";

import { ACCOUNT_LINKS } from "./links";
import { Reveal } from "./Reveal";
import type { Tint } from "./SceneTiles";

const PLANS_URL = "/api/plans/";
const STATUS_URL = "/api/auth/company/status/";
const BILLING_ADDRESS = "/company/billing";
const NO_PLANS = "No plans are available right now. Please check back soon.";

export type PublicPlan = {
  id: number;
  name: string;
  description: string;
  price: Money & { note: string | null; approximate: boolean };
  charged: Money;
  cvs_per_month: number | null;
  cvs_per_project: number | null;
  max_projects: number | null;
  max_team_accounts: number | null;
  max_top_n: number | null;
};

const TINTS: Tint[] = ["lime", "lilac", "peach", "sky", "pink"];
const PAGE_HEADING = "Pricing";

const count = (value: number) => value.toLocaleString("en-US");

function limitsOf(plan: PublicPlan): string[] {
  const lines: [number | null, (value: string) => string][] = [
    [plan.cvs_per_month, (value) => `${value} CVs per month`],
    [plan.cvs_per_project, (value) => `${value} CVs per project`],
    [plan.max_projects, (value) => `Up to ${value} projects`],
    [plan.max_team_accounts, (value) => `Up to ${value} team accounts`],
    [plan.max_top_n, (value) => `Top ${value} shortlist`],
  ];
  return lines.flatMap(([value, words]) => (value === null ? [] : [words(count(value))]));
}

/** The active plans exactly as the admin panel sets them, with the price for the visitor's
 * country. "Choose plan" goes to billing for anyone signed in (a member sees the page's normal
 * no-access message there) and to sign up for everyone else. The links never carry a plan or a
 * price: the plan is chosen, and the amount decided, on the billing page. */
export function PricingPlans() {
  const [plans, setPlans] = useState<PublicPlan[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    getJson<PublicPlan[]>(PLANS_URL).then((result) => {
      if (result.ok) setPlans(result.data);
      else setProblem(result.error.message);
    });
    getJson<{ signed_in: boolean }>(STATUS_URL).then((result) => {
      if (result.ok) setSignedIn(result.data.signed_in);
    });
  }, []);

  if (problem) return <p role="alert">{problem}</p>;
  if (plans === null) return null;
  if (plans.length === 0) return <p role="status">{NO_PLANS}</p>;

  const destination = signedIn ? BILLING_ADDRESS : ACCOUNT_LINKS.signUp.href;
  return (
    <>
      <header className="page-title-block">
        <h1 className="page-title">
          <span className="marker">{PAGE_HEADING}</span>
        </h1>
      </header>
      <Reveal className="plan-grid">
        {plans.map((plan, position) => (
          <Card
            key={plan.id}
            className="plan-card"
            data-tint={TINTS[position % TINTS.length]}
            aria-label={plan.name}
          >
            <h2>{plan.name}</h2>
            <p className="plan-card__price">
              {plan.price.approximate
                ? `About ${money(plan.price)} per month`
                : `${money(plan.price)} per month`}
            </p>
            {plan.description && <p className="plan-card__note">{plan.description}</p>}
            {plan.price.approximate && (
              <p className="plan-card__note">
                {plan.price.note} Charged: {money(plan.charged)} per month
              </p>
            )}
            <ul className="plan-card__limits">
              {limitsOf(plan).map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            <ButtonLink href={destination}>Choose plan</ButtonLink>
          </Card>
        ))}
      </Reveal>
    </>
  );
}
