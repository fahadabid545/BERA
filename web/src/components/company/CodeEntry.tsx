"use client";

import { useEffect, useState } from "react";

import { Button, Dialog, Input } from "@/components/ui";
import { postJson } from "@/lib/api";
import { money } from "@/lib/money";

const CHECK_URL = "/api/company/billing/code/";
const REDEEM_URLS = {
  trial: "/api/company/billing/trial/redeem/",
  beta: "/api/company/billing/beta/redeem/",
};

type Starting =
  | { kind: "trial"; plan: string; days: number; cv_limit: number }
  | { kind: "beta"; days: number; cvs_per_day: number };
type Checked = Starting | { kind: "coupon" };
type Preview = {
  currency: string;
  price: string;
  discount: string;
  new_price: string;
  duration: "once" | "months" | "forever";
  months: number | null;
};

/** The "Have a code?" field of the billing page, for the owner. One field takes a trial code, a beta
 * code or a discount code: a trial or beta access asks for a confirmation and starts at once, a
 * discount code is kept and
 * used when a plan is bought. The server decides what a code is and never says why one fails. */
export function CodeEntry({
  appliedCode,
  onApplied,
  onTrialStarted,
}: {
  appliedCode: string | null;
  onApplied: (code: string | null) => void;
  onTrialStarted: () => void;
}) {
  const [typed, setTyped] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [trial, setTrial] = useState<{ code: string; info: Starting } | null>(null);

  async function apply() {
    const code = typed.trim();
    if (!code) return;
    setProblem(null);
    const result = await postJson<Checked>(CHECK_URL, { code });
    if (!result.ok) return setProblem(result.error.message);
    if (result.data.kind === "trial" || result.data.kind === "beta")
      setTrial({ code, info: result.data });
    else {
      onApplied(code);
      setTyped("");
    }
  }

  async function startTrial() {
    if (!trial) return;
    const result = await postJson(REDEEM_URLS[trial.info.kind], { code: trial.code });
    setTrial(null);
    if (!result.ok) return setProblem(result.error.message);
    setTyped("");
    onTrialStarted();
  }

  return (
    <div className="page-stack">
      {appliedCode ? (
        <div className="page-actions">
          <p role="status">Code applied: {appliedCode}</p>
          <Button variant="secondary" onClick={() => onApplied(null)}>
            Remove code
          </Button>
        </div>
      ) : (
        <div className="ask-bar">
          <Input label="Have a code?" value={typed} onChange={(e) => setTyped(e.target.value)} />
          <Button variant="secondary" disabled={!typed.trim()} onClick={() => void apply()}>
            Apply code
          </Button>
        </div>
      )}
      {problem && (
        <p className="ui-error" role="alert">
          {problem}
        </p>
      )}
      <Dialog
        open={trial !== null}
        onOpenChange={(open) => !open && setTrial(null)}
        title={trial?.info.kind === "beta" ? "Start beta access" : "Start free trial"}
        confirmLabel={trial?.info.kind === "beta" ? "Start beta access" : "Start trial"}
        onConfirm={() => void startTrial()}
      >
        {trial && (
          <p>
            {trial.info.kind === "beta"
              ? `${trial.info.days} days, up to ${trial.info.cvs_per_day} CVs a day`
              : `${trial.info.plan} plan, ${trial.info.days} days, up to ${trial.info.cv_limit} CVs`}
          </p>
        )}
      </Dialog>
    </div>
  );
}

/** The price, the discount and the new price of a plan with the company's code, before paying.
 * It is only a preview: the payment provider's invoice is what is charged. */
export function DiscountPreview({ code, planId }: { code: string; planId: number }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    void postJson<Preview & { kind: string }>(CHECK_URL, { code, plan_id: planId }).then(
      (result) => {
        if (!current) return;
        setPreview(result.ok ? result.data : null);
        setProblem(result.ok ? null : result.error.message);
      },
    );
    return () => {
      current = false;
    };
  }, [code, planId]);

  if (problem) return <p className="ui-error">{problem}</p>;
  if (!preview) return null;
  const amount = (value: string) => money({ currency: preview.currency, amount: value });
  const lasts =
    preview.duration === "once"
      ? "first payment"
      : preview.duration === "months"
        ? `first ${preview.months} months`
        : "every payment";
  return (
    <dl>
      <dt>Price</dt>
      <dd>{amount(preview.price)} per month</dd>
      <dt>Discount</dt>
      <dd>
        {amount(preview.discount)} off, {lasts}
      </dd>
      <dt>New price</dt>
      <dd>{amount(preview.new_price)} per month</dd>
    </dl>
  );
}
