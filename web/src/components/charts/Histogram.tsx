import { ChartMark, TipLines } from "./ChartTip";

const PERCENT = 100;

export type GradeCount = { grade: string; count: number };

/** How the scored candidates spread over the grades: one column for each grade, its count
 * written above it. Hovering a column gives its share; with `onOpen`, clicking lists them. */
export function Histogram({
  grades,
  onOpen,
}: {
  grades: GradeCount[];
  onOpen?: (grade: string) => void;
}) {
  const tallest = Math.max(1, ...grades.map((item) => item.count));
  const total = grades.reduce((sum, item) => sum + item.count, 0);
  return (
    <ol className="chart-histogram" aria-label="Score distribution">
      {grades.map((item) => (
        <li key={item.grade} className="chart-histogram__item">
          <ChartMark
            tip={
              <TipLines
                title={`Grade ${item.grade}`}
                lines={[
                  `${item.count} candidates`,
                  `${total ? Math.round((item.count * PERCENT) / total) : 0}% of all scored`,
                ]}
              />
            }
            onOpen={onOpen ? () => onOpen(item.grade) : undefined}
            className="chart-histogram__column"
          >
            <span className="chart-histogram__value">{item.count}</span>
            <span className="chart-histogram__track">
              <span
                className={`chart-histogram__bar chart-histogram__bar--${item.grade}`}
                style={{ height: `${(item.count * PERCENT) / tallest}%` }}
              />
            </span>
            <span className="chart-histogram__label">Grade {item.grade}</span>
          </ChartMark>
        </li>
      ))}
    </ol>
  );
}
