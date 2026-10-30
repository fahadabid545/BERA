import { ButtonLink } from "@/components/ui";
import { ACCOUNT_LINKS, NAV_LINKS } from "@/components/website/links";

const PRICING_LINK = NAV_LINKS.find((link) => link.label === "Pricing")!;

export default function WebsiteHome() {
  return (
    <div className="page-actions">
      <ButtonLink href={ACCOUNT_LINKS.signUp.href}>Get started</ButtonLink>
      <ButtonLink href={PRICING_LINK.href} variant="secondary">
        See pricing
      </ButtonLink>
    </div>
  );
}
