import { Card } from "@/components/ui";

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
} from "./Vignettes";

const STEP_SCENES = [UploadScene, ScoreScene, DecideScene];
const STEP_TINTS = ["lime", "lilac", "peach"] as const;
const FEATURE_SCENES = [
  ExplainScene,
  CompareScene,
  FilterScene,
  ReportScene,
  TeamScene,
  RetentionScene,
];
const FEATURE_TINTS = ["lime", "lilac", "peach", "sky", "pink", "lime"] as const;
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

export function MarkedHeading({
  id,
  heading,
}: {
  id: string;
  heading: { plain: string; marked: string; rest?: string };
}) {
  return (
    <h2 id={id} className="home-heading">
      {heading.plain}
      <span className="marker">{heading.marked}</span>
      {heading.rest}
    </h2>
  );
}

export function StepsSection() {
  return (
    <section className="home-section" aria-labelledby="home-steps">
      <Reveal as="p" className="home-kicker">
        {HOME.steps.kicker}
      </Reveal>
      <Reveal>
        <MarkedHeading id="home-steps" heading={HOME.steps.heading} />
      </Reveal>
      <Reveal className="home-grid home-grid--steps">
        {HOME.steps.items.map((title, position) => {
          const Scene = STEP_SCENES[position];
          return (
            <Card key={title} className="home-tile" data-tint={STEP_TINTS[position]}>
              <div className="home-tile__scene" aria-hidden="true">
                <Scene />
              </div>
              <h3>
                <span className="step-badge" aria-hidden="true">
                  {position + 1}
                </span>
                {title}
              </h3>
            </Card>
          );
        })}
      </Reveal>
    </section>
  );
}

export function FeaturesSection() {
  return (
    <section className="home-section" aria-labelledby="home-features">
      <Reveal as="p" className="home-kicker">
        {HOME.features.kicker}
      </Reveal>
      <Reveal>
        <MarkedHeading id="home-features" heading={HOME.features.heading} />
      </Reveal>
      <Reveal className="home-grid home-grid--features">
        {HOME.features.items.map((title, position) => {
          const Scene = FEATURE_SCENES[position];
          return (
            <Card
              key={title}
              className="home-tile"
              data-tint={FEATURE_TINTS[position]}
              data-span={FEATURE_SPANS[position]}
            >
              <div className="home-tile__scene" aria-hidden="true">
                <Scene />
              </div>
              <h3>{title}</h3>
            </Card>
          );
        })}
      </Reveal>
    </section>
  );
}
