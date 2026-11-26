import { ButtonLink, Card } from "@/components/ui";
import { ChatSearchBar } from "@/components/website/chat/ChatEntryPoints";
import { HOME } from "@/components/website/content";
import { ACCOUNT_LINKS, NAV_LINKS } from "@/components/website/links";
import { pageMetadata } from "@/lib/seo";

const PRICING_LINK = NAV_LINKS.find((link) => link.label === "Pricing")!;

export async function generateMetadata() {
  return pageMetadata("home");
}

export default function WebsiteHome() {
  return (
    <div className="page-stack">
      <h1>{HOME.heading}</h1>
      <p>{HOME.subheading}</p>
      <ChatSearchBar />
      {HOME.sections.map((section) => (
        <Card key={section.title} aria-label={section.title}>
          <h2>{section.title}</h2>
          <p>{section.text}</p>
        </Card>
      ))}
      <div className="page-actions">
        <ButtonLink href={ACCOUNT_LINKS.signUp.href}>Get started</ButtonLink>
        <ButtonLink href={PRICING_LINK.href} variant="secondary">
          See pricing
        </ButtonLink>
      </div>
    </div>
  );
}
