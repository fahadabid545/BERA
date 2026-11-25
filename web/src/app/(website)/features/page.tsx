import { ButtonLink, Card } from "@/components/ui";
import { FEATURES } from "@/components/website/content";
import { ACCOUNT_LINKS } from "@/components/website/links";

export default function FeaturesPage() {
  return (
    <div className="page-stack">
      <h1>{FEATURES.heading}</h1>
      {FEATURES.items.map((feature) => (
        <Card key={feature.name} aria-label={feature.name}>
          <h2>{feature.name}</h2>
          <p>{feature.does}</p>
          <p>{feature.helps}</p>
        </Card>
      ))}
      <div className="page-actions">
        <ButtonLink href={ACCOUNT_LINKS.signUp.href}>Get started</ButtonLink>
      </div>
    </div>
  );
}
