const PERCENT = 100;

export type GradeCount = { grade: string; count: number };

/** How the scored candidates spread over the grades: one column for each grade, its count
 * written above it, so the shape reads at a glance and the numbers need no hovering. */
export function Histogram({ grades }: { grades: GradeCount[] }) {
  const tallest = Math.max(1, ...grades.map((item) => item.count));
  return (
    <ol className="chart-histogram" aria-label="Score distribution">
      {grades.map((item) => (
        <li key={item.grade} className="chart-histogram__column">
          <span className="chart-histogram__value">{item.count}</span>
          <span className="chart-histogram__track">
            <span
              className="chart-histogram__bar"
              style={{ height: `${(item.count * PERCENT) / tallest}%` }}
            />
          </span>
          <span className="chart-histogram__label">Grade {item.grade}</span>
        </li>
      ))}
    </ol>
  );
}
