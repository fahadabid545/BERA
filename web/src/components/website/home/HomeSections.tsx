import { HOME } from "../content";
import { Reveal } from "../Reveal";
import {
  CompareScene,
  DecideScene,
  ExplainScene,
  FilterScene,
  ReportScene,
  RetentionScene,
  ScoreScene,
  TeamScene,
  UploadScene,
} from "../Scenes";
import { SceneTile, SectionIntro, type Tint } from "../SceneTiles";

const STEP_SCENES = [UploadScene, ScoreScene, DecideScene];
const STEP_TINTS: Tint[] = ["lime", "lilac", "peach"];
const FEATURE_SCENES = [
  ExplainScene,
  CompareScene,
  FilterScene,
  ReportScene,
  TeamScene,
  RetentionScene,
];
const FEATURE_TINTS: Tint[] = ["lime", "lilac", "peach", "sky", "pink", "lime"];
/** The grid spans of the six feature tiles: two wide, three narrow, one full row. */
const FEATURE_SPANS = ["half", "half", "third", "third", "third", "full"] as const;

export function RoleStrip() {
  const roles = [...HOME.roles, ...HOME.roles];
  return (
    <div className="role-strip" aria-hidden="true">
      <div className="role-strip__track">
        {roles.map((role, position) => (
          <span key={position}>{role}</span>
        ))}
      </div>
    </div>
  );
}

export function StepsSection() {
  return (
    <section className="page-section" aria-labelledby="home-steps">
      <SectionIntro id="home-steps" kicker={HOME.steps.kicker} heading={HOME.steps.heading} />
      <Reveal className="tile-grid tile-grid--steps">
        {HOME.steps.items.map((title, position) => (
          <SceneTile
            key={title}
            title={title}
            tint={STEP_TINTS[position]}
            badge={position + 1}
            Scene={STEP_SCENES[position]}
          />
        ))}
      </Reveal>
    </section>
  );
}

export function FeaturesSection() {
  return (
    <section className="page-section" aria-labelledby="home-features">
      <SectionIntro
        id="home-features"
        kicker={HOME.features.kicker}
        heading={HOME.features.heading}
      />
      <Reveal className="tile-grid tile-grid--features">
        {HOME.features.items.map((title, position) => (
          <SceneTile
            key={title}
            title={title}
            tint={FEATURE_TINTS[position]}
            span={FEATURE_SPANS[position]}
            Scene={FEATURE_SCENES[position]}
          />
        ))}
      </Reveal>
    </section>
  );
}
