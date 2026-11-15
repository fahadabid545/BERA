import { Tag } from "@/components/ui";

const WIDTH = 300;
const HEIGHT = 100;
const PADDING = 6;

export type TrendMetric = {
  current: number[];
  previous: number[];
  total: number;
  previous_total: number;
  change_percent: number | null;
};

function points(values: number[], top: number) {
  const step = values.length > 1 ? WIDTH / (values.length - 1) : 0;
  return values.map((value, index) => ({
    x: index * step,
    y: HEIGHT - PADDING - (value / top) * (HEIGHT - 2 * PADDING),
  }));
}
const line = (list: { x: number; y: number }[]) =>
  list.map((point, index) => `${index ? "L" : "M"}${point.x},${point.y}`).join(" ");

/** The last period against the one before it: this period as a solid line with a soft fill, the
 * previous one dashed on the same scale, the total as the headline and the change written out. */
export function Trend({
  metric,
  startLabel,
  endLabel,
}: {
  metric: TrendMetric;
  startLabel: string;
  endLabel: string;
}) {
  const top = Math.max(1, ...metric.current, ...metric.previous);
  const now = points(metric.current, top);
  const before = points(metric.previous, top);
  const last = now[now.length - 1];
  const change = metric.change_percent;
  return (
    <div className="chart-trend">
      <div className="chart-trend__headline">
        <span className="chart-trend__total">{metric.total}</span>
        {change === null ? (
          <Tag variant="neutral">No earlier period</Tag>
        ) : (
          <Tag variant={change < 0 ? "danger" : change > 0 ? "success" : "neutral"}>
            {change > 0 ? "+" : ""}
            {change}% against the previous period
          </Tag>
        )}
        <span className="chart-trend__previous">Previous period {metric.previous_total}</span>
      </div>
      <div className="chart-trend__frame">
        <svg
          className="chart-trend__plot"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={`This period ${metric.total}, previous period ${metric.previous_total}`}
        >
          <path
            className="chart-trend__area"
            d={`${line(now)} L${WIDTH},${HEIGHT} L0,${HEIGHT} Z`}
          />
          <path className="chart-trend__previous-line" d={line(before)} />
          <path className="chart-trend__line" d={line(now)} />
        </svg>
        {last && (
          <span
            className="chart-trend__dot"
            style={{ left: `${(last.x / WIDTH) * 100}%`, top: `${(last.y / HEIGHT) * 100}%` }}
          />
        )}
      </div>
      <div className="chart-trend__axis">
        <span>{startLabel}</span>
        <span>{endLabel}</span>
      </div>
    </div>
  );
}
