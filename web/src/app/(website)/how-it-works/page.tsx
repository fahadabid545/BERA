import { HOW_IT_WORKS } from "@/components/website/content";
import { ACCOUNT_LINKS, NAV_LINKS } from "@/components/website/links";
import { Reveal } from "@/components/website/Reveal";
import { CompareScene, ProjectScene, ScoreScene, UploadScene } from "@/components/website/Scenes";
import { ClosingBand, SceneTile, type Tint } from "@/components/website/SceneTiles";
import { pageMetadata } from "@/lib/seo";

export async function generateMetadata() {
  return pageMetadata("howItWorks");
}

/** One scene per step, in the same order as HOW_IT_WORKS.steps. */
const STEP_SCENES = [ProjectScene, UploadScene, ScoreScene, CompareScene];
const STEP_TINTS: Tint[] = ["lime", "lilac", "peach", "sky"];
const PRICING_LINK = NAV_LINKS.find((link) => link.label === "Pricing")!;
const CLOSING_ACTIONS = [
  { label: "Get started", href: ACCOUNT_LINKS.signUp.href },
  { label: "See pricing", href: PRICING_LINK.href, secondary: true },
];
const CLOSING_CHIPS = ["Grade A", "Shortlisted", "Interviewed", "On hold"];

export default function HowItWorksPage() {
  return (
    <>
      <header className="page-title-block">
        <h1 className="page-title">
          <span className="marker">{HOW_IT_WORKS.heading}</span>
        </h1>
      </header>
      <Reveal as="ol" className="step-list">
        {HOW_IT_WORKS.steps.map((title, position) => (
          <li key={title}>
            <SceneTile
              title={title}
              tint={STEP_TINTS[position]}
              badge={position + 1}
              Scene={STEP_SCENES[position]}
            />
          </li>
        ))}
      </Reveal>
      <ClosingBand
        id="how-closing"
        heading={HOW_IT_WORKS.closing}
        actions={CLOSING_ACTIONS}
        chips={CLOSING_CHIPS}
      />
    </>
  );
}
