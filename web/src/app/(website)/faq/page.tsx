import { FAQ } from "@/components/website/content";
import { NAV_LINKS } from "@/components/website/links";
import { Reveal } from "@/components/website/Reveal";
import { ClosingBand, type Tint } from "@/components/website/SceneTiles";
import { pageMetadata } from "@/lib/seo";

const CONTACT_LINK = NAV_LINKS.find((link) => link.label === "Contact")!;
const TINTS: Tint[] = ["lime", "lilac", "peach", "sky", "pink"];
const CLOSING_ACTIONS = [{ label: CONTACT_LINK.label, href: CONTACT_LINK.href }];

export async function generateMetadata() {
  return pageMetadata("faq");
}

/** Each question is a sticker card that opens to its answer (a native details element, so it
 * works from the keyboard and without scripts). */
export default function FaqPage() {
  return (
    <>
      <header className="page-title-block">
        <h1 className="page-title">
          <span className="marker">{FAQ.heading}</span>
        </h1>
      </header>
      <section className="page-section page-section--tight" aria-label={FAQ.heading}>
        <Reveal className="faq-list">
          {FAQ.questions.map((item, position) => (
            <details
              key={item.question}
              className="faq-item ui-card"
              data-tint={TINTS[position % TINTS.length]}
              aria-label={item.question}
              role="region"
            >
              <summary className="faq-item__question">
                <h2>{item.question}</h2>
                <span className="faq-item__sign" aria-hidden="true" />
              </summary>
              <p>{item.answer}</p>
            </details>
          ))}
        </Reveal>
      </section>
      <ClosingBand id="faq-closing" heading={FAQ.closing} actions={CLOSING_ACTIONS} chips={[]} />
    </>
  );
}
