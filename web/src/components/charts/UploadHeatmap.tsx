import { ChartMark, TipLines } from "./ChartTip";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const PERCENT = 100;
const HOUR_LABEL_EVERY = 6;
const hourText = (hour: number) => `${String(hour).padStart(2, "0")}:00`;

/** When CVs are uploaded: one square for each weekday and hour (UTC), darker for more. Every
 * square gives its day, hour and count on hover or focus, so the figure never rests on colour. */
export function UploadHeatmap({ grid }: { grid: number[][] }) {
  const busiest = Math.max(1, ...grid.flat());
  const hours = grid[0]?.map((_, hour) => hour) ?? [];
  return (
    <div className="upload-heatmap" role="group" aria-label="Uploads by weekday and hour">
      <span />
      {hours.map((hour) => (
        <span key={hour} className="upload-heatmap__hour">
          {hour % HOUR_LABEL_EVERY === 0 ? hourText(hour) : ""}
        </span>
      ))}
      {grid.map((counts, day) => (
        <div key={DAYS[day]} className="upload-heatmap__row">
          <span className="upload-heatmap__day">{DAYS[day].slice(0, 3)}</span>
          {counts.map((count, hour) => (
            <ChartMark
              key={hour}
              as="span"
              className="upload-heatmap__cell"
              label={`${DAYS[day]} ${hourText(hour)}: ${count} ${count === 1 ? "CV" : "CVs"}`}
              style={{ ["--share" as string]: `${(count * PERCENT) / busiest}%` }}
              tip={
                <TipLines
                  title={`${DAYS[day]}, ${hourText(hour)}`}
                  lines={[`${count} ${count === 1 ? "CV" : "CVs"} uploaded`]}
                />
              }
            />
          ))}
        </div>
      ))}
    </div>
  );
}
