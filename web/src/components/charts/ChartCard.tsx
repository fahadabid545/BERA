import type { ReactNode } from "react";

import { Card } from "@/components/ui";

/** The frame every chart sits in: a title, optional controls on the right, then the chart. */
export function ChartCard({
  title,
  controls,
  children,
}: {
  title: string;
  controls?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card className="ui-card chart-card">
      <div className="chart-card__header">
        <h2>{title}</h2>
        {controls && <div className="chart-card__controls">{controls}</div>}
      </div>
      <div className="chart-card__body">{children}</div>
    </Card>
  );
}
