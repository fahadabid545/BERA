import { ButtonLink } from "@/components/ui";
import { ChatSearchBar } from "@/components/website/chat/ChatEntryPoints";
import { HOME } from "@/components/website/content";
import { HeroScreening } from "@/components/website/home/HeroScreening";
import { FeaturesSection, RoleStrip, StepsSection } from "@/components/website/home/HomeSections";
import { RotatingWord } from "@/components/website/home/RotatingWord";
import { ACCOUNT_LINKS, NAV_LINKS } from "@/components/website/links";
import { ClosingBand } from "@/components/website/SceneTiles";
import { pageMetadata } from "@/lib/seo";

const PRICING_LINK = NAV_LINKS.find((link) => link.label === "Pricing")!;
const CLOSING_CHIPS = ["Grade A", "Shortlisted", "On hold", "Interviewed"];

export async function generateMetadata() {
  return pageMetadata("home");
}

const HOME_ACTIONS = [
  { label: "Get started", href: ACCOUNT_LINKS.signUp.href },
  { label: "See pricing", href: PRICING_LINK.href, secondary: true },
];

function HomeActions() {
  return (
    <div className="page-actions">
      {HOME_ACTIONS.map((action) => (
        <ButtonLink
          key={action.label}
          href={action.href}
          variant={action.secondary ? "secondary" : "primary"}
        >
          {action.label}
        </ButtonLink>
      ))}
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
      <ClosingBand
        id="home-closing"
        heading={HOME.closing}
        actions={HOME_ACTIONS}
        chips={CLOSING_CHIPS}
      />
    </>
  );
}
