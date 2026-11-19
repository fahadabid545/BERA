"use client";

import type { ReactNode } from "react";

import { BILLING_HREF, CONTACT_HREF } from "@/components/company/links";
import { useCompanyRole } from "@/components/company/role";
import { ButtonLink, Dialog } from "@/components/ui";

export type PromptKind = "upgrade" | "renewal" | "highest_plan";

const PROMPTS: Record<
  PromptKind,
  { title: string; actionLabel: string; href: string; askOwner: string }
> = {
  upgrade: {
    title: "Upgrade your plan",
    actionLabel: "Upgrade plan",
    href: BILLING_HREF,
    askOwner: "Please ask your company owner to upgrade.",
  },
  renewal: {
    title: "Renew your subscription",
    actionLabel: "Renew subscription",
    href: BILLING_HREF,
    askOwner: "Please ask your company owner to renew.",
  },
  highest_plan: {
    title: "You have used your highest plan",
    actionLabel: "Contact us",
    href: CONTACT_HREF,
    askOwner: "Please ask your company owner to get in touch.",
  },
};

/** What the server's `prompt` answer may be; anything else is not a billing prompt. */
export const isPromptKind = (value: unknown): value is PromptKind =>
  typeof value === "string" && value in PROMPTS;

type PromptProps = {
  /** The button that opens the popup. Leave it out when the page opens the popup itself. */
  trigger?: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};

/** The popup for one kind of block. Only owners get the action button; a member is asked to
 * pass it on. */
export function BillingPrompt({ kind, ...props }: PromptProps & { kind: PromptKind }) {
  const role = useCompanyRole();
  const prompt = PROMPTS[kind];
  const isOwner = role === "owner";
  return (
    <Dialog
      {...props}
      title={prompt.title}
      description={isOwner ? undefined : prompt.askOwner}
      actions={
        isOwner ? <ButtonLink href={prompt.href}>{prompt.actionLabel}</ButtonLink> : undefined
      }
    />
  );
}

/** Shown when a company reaches its limit. */
export const UpgradePrompt = (props: PromptProps) => <BillingPrompt {...props} kind="upgrade" />;

/** Shown when a subscription must be renewed. */
export const RenewalPrompt = (props: PromptProps) => <BillingPrompt {...props} kind="renewal" />;

/** Shown when a limit is reached on the highest plan. */
export const HighestPlanPrompt = (props: PromptProps) => (
  <BillingPrompt {...props} kind="highest_plan" />
);

/** The popup for whichever block a page was told about (nothing when there is none). */
export function BillingPrompts({
  kind,
  onClose,
}: {
  kind: PromptKind | null;
  onClose: () => void;
}) {
  return (
    <>
      {(Object.keys(PROMPTS) as PromptKind[]).map((each) => (
        <BillingPrompt
          key={each}
          kind={each}
          open={kind === each}
          onOpenChange={(open) => !open && onClose()}
        />
      ))}
    </>
  );
}
