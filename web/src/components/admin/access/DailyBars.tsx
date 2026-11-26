import { ChartMark, TipLines } from "@/components/charts/ChartTip";

import { day, type DailyCvs } from "./types";

const PERCENT = 100;

/** CVs for each day: one column a day with its count in a tooltip; a limit, when given, is
 * written beside the chart. */
export function DailyBars({ days, label }: { days: DailyCvs; label: string }) {
  const tallest = Math.max(1, ...days.map((item) => item.cvs));
  return (
    <ol className="chart-days" aria-label={label}>
      {days.map((item) => (
        <li key={item.day} className="chart-days__item">
          <ChartMark
            label={`${day(item.day)}: ${item.cvs} CVs`}
            tip={<TipLines title={day(item.day)} lines={[`${item.cvs} CVs`]} />}
            className="chart-days__column"
          >
            <span className="chart-days__track">
              <span
                className="chart-days__bar"
                style={{ height: `${(item.cvs * PERCENT) / tallest}%` }}
              />
            </span>
          </ChartMark>
        </li>
      ))}
    </ol>
  );
}
