import { ButtonLink } from "@/components/ui";
import { ChatSearchBar } from "@/components/website/chat/ChatEntryPoints";
import { HOME } from "@/components/website/content";
import { HeroScreening } from "@/components/website/home/HeroScreening";
import {
  FeaturesSection,
  MarkedHeading,
  RoleStrip,
  StepsSection,
} from "@/components/website/home/HomeSections";
import { RotatingWord } from "@/components/website/home/RotatingWord";
import { ACCOUNT_LINKS, NAV_LINKS } from "@/components/website/links";
import { Reveal } from "@/components/website/Reveal";
import { pageMetadata } from "@/lib/seo";

const PRICING_LINK = NAV_LINKS.find((link) => link.label === "Pricing")!;
const CLOSING_CHIPS = ["Grade A", "Shortlisted", "On hold", "Interviewed"];

export async function generateMetadata() {
  return pageMetadata("home");
}

function HomeActions() {
  return (
    <div className="page-actions">
      <ButtonLink href={ACCOUNT_LINKS.signUp.href}>Get started</ButtonLink>
      <ButtonLink href={PRICING_LINK.href} variant="secondary">
        See pricing
      </ButtonLink>
    </div>
  );
}

export default function WebsiteHome() {
  return (
    <>
      <div className="site-bleed home-hero">
        <div className="site-bleed__inner home-hero__grid">
          <div className="home-hero__copy">
            <span className="home-eyebrow">{HOME.eyebrow}</span>
            <h1>
              {HOME.heading} <RotatingWord words={HOME.rotatingWords} />
            </h1>
            <HomeActions />
            <ChatSearchBar />
          </div>
          <HeroScreening />
        </div>
        <RoleStrip />
      </div>
      <StepsSection />
      <FeaturesSection />
      <Reveal as="section" className="home-closing" aria-labelledby="home-closing">
        <MarkedHeading id="home-closing" heading={HOME.closing} />
        <HomeActions />
        {CLOSING_CHIPS.map((chip, position) => (
          <span
            key={chip}
            className={`home-closing__chip home-closing__chip--${position + 1}`}
            aria-hidden="true"
          >
            {chip}
          </span>
        ))}
      </Reveal>
    </>
  );
}
