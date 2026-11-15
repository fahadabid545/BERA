import { Tag } from "@/components/ui";

import { ChartMark, TipLines } from "./ChartTip";

const WIDTH = 300;
const HEIGHT = 100;
const PADDING = 6;
const PERCENT = 100;
const SCALE_STEPS = 2;

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

function dayLabel(start: string, offset: number) {
  const day = new Date(start);
  day.setUTCDate(day.getUTCDate() + offset);
  return day.toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

/** The last period against the one before it: this period as a solid line with a soft fill, the
 * previous one dashed on the same scale, the total as the headline and the change written out.
 * Each day has a marker; hovering it gives that day's figure next to the same day before. */
export function Trend({
  metric,
  start,
  label,
}: {
  metric: TrendMetric;
  /** The first day of this period, as YYYY-MM-DD. */
  start: string;
  label: string;
}) {
  const top = Math.max(1, ...metric.current, ...metric.previous);
  const now = points(metric.current, top);
  const before = points(metric.previous, top);
  const days = metric.current.length;
  const change = metric.change_percent;
  const scale = Array.from({ length: SCALE_STEPS + 1 }, (_, step) => (top * step) / SCALE_STEPS);
  const cell = PERCENT / Math.max(1, days);
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
        <ul className="chart-trend__scale" aria-hidden="true">
          {scale
            .slice()
            .reverse()
            .map((value) => (
              <li key={value}>{Math.round(value)}</li>
            ))}
        </ul>
        <div className="chart-trend__plotbox">
          <svg
            className="chart-trend__plot"
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            preserveAspectRatio="none"
            role="img"
            aria-label={`${label}: this period ${metric.total}, previous period ${metric.previous_total}`}
          >
            {scale.map((value) => (
              <line
                key={value}
                className="chart-trend__grid"
                x1={0}
                x2={WIDTH}
                y1={HEIGHT - PADDING - (value / top) * (HEIGHT - 2 * PADDING)}
                y2={HEIGHT - PADDING - (value / top) * (HEIGHT - 2 * PADDING)}
              />
            ))}
            <path
              className="chart-trend__area"
              d={`${line(now)} L${WIDTH},${HEIGHT} L0,${HEIGHT} Z`}
            />
            <path className="chart-trend__previous-line" d={line(before)} />
            <path className="chart-trend__line" d={line(now)} />
          </svg>
          {now.map((point, index) => (
            <span
              key={`dot-${index}`}
              className="chart-trend__dot"
              style={{
                left: `${(point.x / WIDTH) * PERCENT}%`,
                top: `${(point.y / HEIGHT) * PERCENT}%`,
              }}
            />
          ))}
          {now.map((point, index) => (
            <ChartMark
              key={`hit-${index}`}
              className="chart-trend__hit"
              label={`${dayLabel(start, index)}: ${metric.current[index]}`}
              style={{
                left: `${Math.min(PERCENT - cell, Math.max(0, (point.x / WIDTH) * PERCENT - cell / 2))}%`,
                width: `${cell}%`,
              }}
              tip={
                <TipLines
                  title={dayLabel(start, index)}
                  lines={[
                    `${label}: ${metric.current[index]}`,
                    `Same day before: ${metric.previous[index]}`,
                  ]}
                />
              }
            ></ChartMark>
          ))}
        </div>
      </div>
      <div className="chart-trend__axis">
        <span>{dayLabel(start, 0)}</span>
        {days > 2 && <span>{dayLabel(start, Math.floor((days - 1) / 2))}</span>}
        <span>{dayLabel(start, days - 1)}</span>
      </div>
    </div>
  );
}
