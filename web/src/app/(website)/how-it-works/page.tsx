import { ButtonLink } from "@/components/ui";
import { ACCOUNT_LINKS } from "@/components/website/links";

export default function HowItWorksPage() {
  return (
    <div className="page-actions">
      <ButtonLink href={ACCOUNT_LINKS.signUp.href}>Get started</ButtonLink>
    </div>
  );
}
