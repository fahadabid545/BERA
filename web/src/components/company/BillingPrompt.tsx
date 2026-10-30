"use client";

import type { ReactNode } from "react";

import { BILLING_HREF } from "@/components/company/links";
import { ButtonLink, Dialog } from "@/components/ui";

type PromptProps = {
  /** The button that opens the popup; the code that decides when to show it comes later. */
  trigger: ReactNode;
};

function BillingPrompt({
  trigger,
  title,
  actionLabel,
}: PromptProps & { title: string; actionLabel: string }) {
  return (
    <Dialog
      trigger={trigger}
      title={title}
      actions={<ButtonLink href={BILLING_HREF}>{actionLabel}</ButtonLink>}
    />
  );
}

/** Shown when a company reaches its limit. */
export function UpgradePrompt({ trigger }: PromptProps) {
  return <BillingPrompt trigger={trigger} title="Upgrade your plan" actionLabel="Upgrade plan" />;
}
