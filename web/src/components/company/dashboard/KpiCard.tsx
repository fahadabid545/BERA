import { Tag } from "@/components/ui";
import { ChartMark, TipLines } from "@/components/charts/ChartTip";

import { Sparkline } from "./Sparkline";
import type { Card } from "./types";

/** One figure for the period with its change against the period before and a small line of the
 * last days. The whole card is a button: it opens who or what was counted. */
export function KpiCard({
  label,
  card,
  colour,
  unit = "%",
  period,
  onOpen,
}: {
  label: string;
  card: Card;
  colour: "blue" | "violet" | "teal" | "amber" | "coral";
  /** "%" for counts (a relative change) or " pts" for scores (a difference in points). */
  unit?: string;
  period: string;
  onOpen: () => void;
}) {
  const { value, previous, change } = card;
  return (
    <ChartMark
      className="ui-card kpi-card"
      onOpen={onOpen}
      tip={
        <TipLines
          title={label}
          lines={[
            `${value ?? "No data"} in ${period}`,
            previous === null ? "Nothing before" : `${previous} in the period before`,
          ]}
        />
      }
    >
      <span className="kpi-card__top">
        <span className="kpi-card__label">{label}</span>
        {change === null ? (
          <Tag variant="neutral">New</Tag>
        ) : (
          <Tag variant={change > 0 ? "success" : change < 0 ? "danger" : "neutral"}>
            {change > 0 ? "+" : ""}
            {change}
            {unit}
          </Tag>
        )}
      </span>
      <span className="kpi-card__value">{value ?? "No data"}</span>
      <Sparkline values={card.series} colour={colour} />
    </ChartMark>
  );
}
