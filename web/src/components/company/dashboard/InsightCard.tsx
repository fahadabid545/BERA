import { Tag } from "@/components/ui";
import { ChartMark, TipLines } from "@/components/charts/ChartTip";

const PERCENT = 100;

/** Two thin bars on one scale: this period against the one before. */
function Pair({ now, before, unit }: { now: number | null; before: number | null; unit: string }) {
  const top = Math.max(1, now ?? 0, before ?? 0);
  return (
    <span className="insight-card__pair">
      {[
        ["This period", now, "now"],
        ["Before", before, "before"],
      ].map(([label, value, kind]) => (
        <span key={String(kind)} className="insight-card__row">
          <span>{label}</span>
          <span className="insight-card__track">
            <span
              className={`insight-card__bar insight-card__bar--${kind}`}
              style={{ width: `${(Number(value ?? 0) * PERCENT) / top}%` }}
            />
          </span>
          <span className="insight-card__figure">
            {value === null ? "No data" : `${value}${unit}`}
          </span>
        </span>
      ))}
    </span>
  );
}

/** A headline figure with this period set against the one before, so the person sees at once
 * whether things are better or worse. Clicking opens what stands behind it. */
export function InsightCard({
  title,
  headline,
  tag,
  now,
  before,
  unit,
  tipLines,
  onOpen,
}: {
  title: string;
  headline: string;
  tag: { text: string; variant: "success" | "danger" | "neutral" };
  now: number | null;
  before: number | null;
  unit: string;
  tipLines: string[];
  onOpen: () => void;
}) {
  return (
    <ChartMark
      className="ui-card insight-card"
      onOpen={onOpen}
      tip={<TipLines title={title} lines={tipLines} />}
    >
      <span className="insight-card__title">{title}</span>
      <span className="insight-card__headline">
        <span className="insight-card__big">{headline}</span>
        <Tag variant={tag.variant}>{tag.text}</Tag>
      </span>
      <Pair now={now} before={before} unit={unit} />
    </ChartMark>
  );
}
