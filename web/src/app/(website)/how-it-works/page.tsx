import { ButtonLink, Card } from "@/components/ui";
import { HOW_IT_WORKS } from "@/components/website/content";
import { ACCOUNT_LINKS } from "@/components/website/links";

export default function HowItWorksPage() {
  return (
    <div className="page-stack">
      <h1>{HOW_IT_WORKS.heading}</h1>
      <ol className="content-list page-stack">
        {HOW_IT_WORKS.steps.map((step, index) => (
          <li key={step.title}>
            <Card>
              <h2>
                {index + 1}. {step.title}
              </h2>
              <p>{step.text}</p>
            </Card>
          </li>
        ))}
      </ol>
      <div className="page-actions">
        <ButtonLink href={ACCOUNT_LINKS.signUp.href}>Get started</ButtonLink>
      </div>
    </div>
  );
}
