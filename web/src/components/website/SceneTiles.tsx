import type { ComponentType } from "react";

import { ButtonLink, Card } from "@/components/ui";

import { Reveal } from "./Reveal";

export type MarkedText = { plain: string; marked: string; rest?: string };
export type Tint = "lime" | "lilac" | "peach" | "sky" | "pink";

/** A section heading with one phrase on a green highlight, so green is a fill and never text. */
export function MarkedHeading({ id, heading }: { id: string; heading: MarkedText }) {
  return (
    <h2 id={id} className="section-heading">
      {heading.plain}
      <span className="marker">{heading.marked}</span>
      {heading.rest}
    </h2>
  );
}

/** A coloured card with an illustrated scene and a title. The scene is decoration. */
export function SceneTile({
  title,
  tint,
  span,
  badge,
  Scene,
}: {
  title: string;
  tint: Tint;
  span?: "third" | "half" | "full";
  badge?: number;
  Scene: ComponentType;
}) {
  return (
    <Card className="scene-tile" data-tint={tint} data-span={span}>
      <div className="scene-tile__scene" aria-hidden="true">
        <Scene />
      </div>
      <h3>
        {badge ? (
          <span className="step-badge" aria-hidden="true">
            {badge}
          </span>
        ) : null}
        {title}
      </h3>
    </Card>
  );
}

export function SectionIntro({
  id,
  kicker,
  heading,
}: {
  id: string;
  kicker: string;
  heading: MarkedText;
}) {
  return (
    <>
      <Reveal as="p" className="section-kicker">
        {kicker}
      </Reveal>
      <Reveal>
        <MarkedHeading id={id} heading={heading} />
      </Reveal>
    </>
  );
}

/** The green call-to-action band that closes a page, with a few chips floating in it. */
export function ClosingBand({
  id,
  heading,
  actions,
  chips,
}: {
  id: string;
  heading: MarkedText;
  actions: readonly { label: string; href: string; secondary?: boolean }[];
  chips: readonly string[];
}) {
  return (
    <Reveal as="section" className="closing-band" aria-labelledby={id}>
      <MarkedHeading id={id} heading={heading} />
      <div className="page-actions">
        {actions.map((action) => (
          <ButtonLink
            key={action.label}
            href={action.href}
            variant={action.secondary ? "secondary" : "primary"}
          >
            {action.label}
          </ButtonLink>
        ))}
      </div>
      {chips.map((chip, position) => (
        <span
          key={chip}
          className={`closing-band__chip closing-band__chip--${position + 1}`}
          aria-hidden="true"
        >
          {chip}
        </span>
      ))}
    </Reveal>
  );
}
