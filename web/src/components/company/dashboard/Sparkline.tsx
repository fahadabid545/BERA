const WIDTH = 100;
const HEIGHT = 30;
const PADDING = 3;
const PERCENT = 100;

/** A small line of the last days' values. It carries no numbers of its own: the card around it
 * says them. The end marker is an HTML dot so stretching the line never squashes it. */
export function Sparkline({ values, colour }: { values: number[]; colour: string }) {
  const top = Math.max(1, ...values);
  const step = values.length > 1 ? WIDTH / (values.length - 1) : 0;
  const points = values.map((value, index) => ({
    x: index * step,
    y: HEIGHT - PADDING - (value / top) * (HEIGHT - 2 * PADDING),
  }));
  const path = points.map((point, index) => `${index ? "L" : "M"}${point.x},${point.y}`).join(" ");
  const last = points[points.length - 1];
  return (
    <span className="sparkline" style={{ ["--spark" as string]: `var(--color-data-${colour})` }}>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="none" aria-hidden="true">
        <path className="sparkline__area" d={`${path} L${WIDTH},${HEIGHT} L0,${HEIGHT} Z`} />
        <path className="sparkline__line" d={path} />
      </svg>
      {last && (
        <span
          className="sparkline__dot"
          style={{
            left: `${(last.x / WIDTH) * PERCENT}%`,
            top: `${(last.y / HEIGHT) * PERCENT}%`,
          }}
        />
      )}
    </span>
  );
}
