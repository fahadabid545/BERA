import { Card, TextLink } from "@/components/ui";
import { FAQ } from "@/components/website/content";
import { NAV_LINKS } from "@/components/website/links";
import { pageMetadata } from "@/lib/seo";

const CONTACT_LINK = NAV_LINKS.find((link) => link.label === "Contact")!;

export async function generateMetadata() {
  return pageMetadata("faq");
}

export default function FaqPage() {
  return (
    <div className="page-stack">
      <h1>{FAQ.heading}</h1>
      <p>{FAQ.subheading}</p>
      {FAQ.questions.map((item) => (
        <Card key={item.question} aria-label={item.question}>
          <h2>{item.question}</h2>
          <p>{item.answer}</p>
        </Card>
      ))}
      <p>
        {FAQ.closing} <TextLink href={CONTACT_LINK.href}>{FAQ.closingLink}</TextLink>
      </p>
    </div>
  );
}
