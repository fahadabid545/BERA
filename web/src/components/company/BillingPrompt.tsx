"use client";

import type { ReactNode } from "react";

import { BILLING_HREF } from "@/components/company/links";
import { ButtonLink, Dialog } from "@/components/ui";

type PromptProps = {
  /** The button that opens the popup. Leave it out when the page opens the popup itself. */
  trigger?: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};

function BillingPrompt({
  trigger,
  open,
  onOpenChange,
  title,
  actionLabel,
}: PromptProps & { title: string; actionLabel: string }) {
  return (
    <Dialog
      trigger={trigger}
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      actions={<ButtonLink href={BILLING_HREF}>{actionLabel}</ButtonLink>}
    />
  );
}

/** Shown when a company reaches its limit. */
export function UpgradePrompt(props: PromptProps) {
  return <BillingPrompt {...props} title="Upgrade your plan" actionLabel="Upgrade plan" />;
}

/** Shown when a subscription must be renewed. */
export function RenewalPrompt(props: PromptProps) {
  return (
    <BillingPrompt {...props} title="Renew your subscription" actionLabel="Renew subscription" />
  );
}
