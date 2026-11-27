import { FEATURES } from "@/components/website/content";
import { ACCOUNT_LINKS } from "@/components/website/links";
import { Reveal } from "@/components/website/Reveal";
import {
  CompareScene,
  ControlScene,
  DecideScene,
  ExplainScene,
  FilterScene,
  HighlightScene,
  ProjectScene,
  ReportScene,
  RetentionScene,
  ScoreScene,
  ShieldScene,
  TeamScene,
  UploadScene,
  UsageScene,
} from "@/components/website/Scenes";
import { ClosingBand, SceneTile, SectionIntro, type Tint } from "@/components/website/SceneTiles";
import { pageMetadata } from "@/lib/seo";

export async function generateMetadata() {
  return pageMetadata("features");
}

/** One scene per feature, in the same order as FEATURES.items. */
const FEATURE_SCENES = [
  ProjectScene,
  UploadScene,
  ScoreScene,
  ExplainScene,
  CompareScene,
  FilterScene,
  DecideScene,
  ReportScene,
  TeamScene,
  UsageScene,
  RetentionScene,
];
const TINTS: Tint[] = ["lime", "lilac", "peach", "sky", "pink"];
const TRUST_SCENES = [ControlScene, HighlightScene, ShieldScene];
const TRUST_TINTS: Tint[] = ["sky", "pink", "lime"];
const CLOSING_ACTIONS = [{ label: "Get started", href: ACCOUNT_LINKS.signUp.href }];
const CLOSING_CHIPS = ["Grade A", "Shortlisted", "Interviewed", "On hold"];

export default function FeaturesPage() {
  return (
    <>
      <header className="page-title-block">
        <h1 className="page-title">
          <span className="marker">{FEATURES.heading}</span>
        </h1>
      </header>
      <section className="page-section page-section--tight" aria-label="All features">
        <Reveal className="tile-grid tile-grid--all">
          {FEATURES.items.map((name, position) => (
            <SceneTile
              key={name}
              title={name}
              tint={TINTS[position % TINTS.length]}
              span={position >= FEATURES.items.length - 2 ? "half" : "third"}
              Scene={FEATURE_SCENES[position]}
            />
          ))}
        </Reveal>
      </section>
      <section className="page-section" aria-labelledby="features-trust">
        <SectionIntro
          id="features-trust"
          kicker={FEATURES.trust.kicker}
          heading={FEATURES.trust.heading}
        />
        <Reveal className="tile-grid tile-grid--steps">
          {FEATURES.trust.items.map((title, position) => (
            <SceneTile
              key={title}
              title={title}
              tint={TRUST_TINTS[position]}
              Scene={TRUST_SCENES[position]}
            />
          ))}
        </Reveal>
      </section>
      <ClosingBand
        id="features-closing"
        heading={FEATURES.closing}
        actions={CLOSING_ACTIONS}
        chips={CLOSING_CHIPS}
      />
    </>
  );
}
