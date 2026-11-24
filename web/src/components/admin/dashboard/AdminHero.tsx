import { ChartMark, TipLines } from "@/components/charts/ChartTip";

import { usd, whole, type AdminData } from "./types";

/** The platform at a glance on an ink surface, like the admin sidebar: how many companies, how
 * many pay, how many are suspended and (super admins) what the paying plans bring in a month. */
export function AdminHero({
  totals,
  revenue,
  onSuspended,
}: {
  totals: AdminData["totals"];
  revenue: AdminData["revenue"];
  onSuspended: () => void;
}) {
  return (
    <section className="admin-hero" aria-label="Platform">
      <h2>Platform</h2>
      <ul className="admin-hero__stats">
        <li>
          <ChartMark
            className="admin-hero__stat"
            tip={<TipLines title="Companies" lines={[`${totals.companies} signed up in all`]} />}
          >
            <span>Companies</span>
            <strong>{whole(totals.companies)}</strong>
          </ChartMark>
        </li>
        <li>
          <ChartMark
            className="admin-hero__stat"
            tip={
              <TipLines
                title="Paying"
                lines={[`${totals.paying} companies with an active paid plan`]}
              />
            }
          >
            <span>Paying</span>
            <strong>{whole(totals.paying)}</strong>
          </ChartMark>
        </li>
        <li>
          <ChartMark
            className="admin-hero__stat"
            onOpen={onSuspended}
            tip={<TipLines title="Suspended" lines={["Companies an admin has suspended"]} />}
          >
            <span>Suspended</span>
            <strong>{whole(totals.suspended)}</strong>
          </ChartMark>
        </li>
        {revenue && (
          <li>
            <ChartMark
              className="admin-hero__stat"
              tip={
                <TipLines
                  title="Revenue received"
                  lines={[`Money received in the last ${revenue.margin_days} days`]}
                />
              }
            >
              <span>Revenue received</span>
              <strong>{usd(revenue.received)}</strong>
            </ChartMark>
          </li>
        )}
      </ul>
    </section>
  );
}
