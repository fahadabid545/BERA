"use client";

import { ChartCard } from "@/components/charts/ChartCard";
import { ChartMark, TipLines } from "@/components/charts/ChartTip";
import { TrendCard } from "@/components/charts/TrendCard";
import { Donut } from "@/components/company/dashboard/Donut";
import { Gauge } from "@/components/company/dashboard/Gauge";
import { KpiCard } from "@/components/company/dashboard/KpiCard";
import { periodWords } from "@/components/company/dashboard/types";
import { Button, Card, Table, Tag, TextLink } from "@/components/ui";
import { timeAgo } from "@/lib/timeAgo";

import { AdminHero } from "./AdminHero";
import { PURPOSE_WORDS, STATE_WORDS, usd, whole, type AdminData, type CompanyRow } from "./types";

export type Open = (kind: string, key: string, title: string) => void;

const PERCENT = 100;
const MIX_COLOURS = ["green", "blue", "violet", "amber", "coral", "teal"] as const;
const PURPOSE_COLOURS: Record<string, string> = {
  reading: "blue",
  scoring: "green",
  requirement_extraction: "violet",
  playground: "amber",
};
const TREND_METRICS = [
  { value: "cvs_scored", label: "CVs scored" },
  { value: "ai_calls", label: "AI calls" },
];
const PENDING_ROWS = [
  { key: "past_due", label: "Past-due subscriptions", colour: "coral" },
  { key: "grants_expiring", label: "Free grants ending soon", colour: "blue" },
  { key: "suspended", label: "Suspended companies", colour: "amber" },
  { key: "failed_ai_calls", label: "Failed AI calls", colour: "coral" },
  { key: "failed_jobs", label: "Failed jobs", colour: "coral" },
] as const;

function CompanyLink({ company }: { company: CompanyRow }) {
  return <TextLink href={`/admin/companies/${company.id}`}>{company.name}</TextLink>;
}

export function OverviewSection({ data, open }: { data: AdminData; open: Open }) {
  const { cards, revenue, totals, recent } = data;
  const period = periodWords(data.days);
  return (
    <div className="dashboard__section">
      <AdminHero
        totals={totals}
        revenue={revenue}
        onSuspended={() => open("pending", "suspended", "Suspended companies")}
      />
      <div className="dashboard__kpis">
        <KpiCard
          label="New companies"
          card={cards.companies}
          colour="blue"
          period={period}
          onOpen={() => open("metric", "companies", `New companies ${period}`)}
        />
        <KpiCard
          label="CVs scored"
          card={cards.cvs_scored}
          colour="violet"
          period={period}
          onOpen={() => open("metric", "cvs_scored", `Companies by CVs scored ${period}`)}
        />
        {cards.ai_cost && (
          <KpiCard
            label="AI cost"
            card={cards.ai_cost}
            colour="amber"
            period={period}
            format={usd}
            onOpen={() => open("metric", "cvs_scored", `Companies by CVs scored ${period}`)}
          />
        )}
      </div>
      <Card className="ui-card">
        <div className="chart-card__header">
          <h2>Newest companies</h2>
        </div>
        {recent.length === 0 ? (
          <p role="status">No companies yet.</p>
        ) : (
          <ul className="activity-feed">
            {recent.map((company) => (
              <li key={company.id} className="activity-feed__item">
                <span>
                  <CompanyLink company={company} />{" "}
                  <Tag variant="neutral">{STATE_WORDS[company.state] ?? company.state}</Tag>
                </span>
                {company.created_at && (
                  <time dateTime={company.created_at}>{timeAgo(company.created_at)}</time>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

/** What the paying plans bring in, set against what the AI costs, and how the subscriptions
 * and plans are split. Every row and slice opens the companies in it. */
export function RevenueSection({
  revenue,
  open,
}: {
  revenue: NonNullable<AdminData["revenue"]>;
  open: Open;
}) {
  const top = Math.max(1, revenue.mrr, revenue.ai_cost);
  const states = Object.entries(revenue.states);
  const stateTotal = Math.max(1, ...states.map(([, count]) => count));
  return (
    <div className="dashboard__section">
      <div className="dashboard__row">
        <Card className="ui-card revenue-card">
          <div className="chart-card__header">
            <h2>Revenue against AI cost</h2>
            {revenue.margin_percent === null ? (
              <Tag variant="neutral">No revenue yet</Tag>
            ) : (
              <Tag variant={revenue.margin_percent >= 0 ? "success" : "danger"}>
                Margin {revenue.margin_percent}%
              </Tag>
            )}
          </div>
          {[
            ["Monthly revenue", revenue.mrr, "revenue-card__bar--revenue"],
            [
              `AI cost, last ${revenue.margin_days} days`,
              revenue.ai_cost,
              "revenue-card__bar--cost",
            ],
          ].map(([label, value, kind]) => (
            <ChartMark
              key={String(label)}
              className="revenue-card__row"
              tip={
                <TipLines
                  title={String(label)}
                  lines={[usd(Number(value)), "Estimated, not money received"]}
                />
              }
            >
              <span>{label}</span>
              <span className="revenue-card__track">
                <span
                  className={`revenue-card__bar ${kind}`}
                  style={{ width: `${(Number(value) * PERCENT) / top}%` }}
                />
              </span>
              <strong>{usd(Number(value))}</strong>
            </ChartMark>
          ))}
        </Card>
        <Card className="ui-card">
          <div className="chart-card__header">
            <h2>Plan mix</h2>
          </div>
          {revenue.plans.length === 0 ? (
            <p role="status">No paying subscriptions yet.</p>
          ) : (
            <Donut
              total={revenue.plans.reduce((sum, plan) => sum + plan.subscribers, 0)}
              centreLabel="paying"
              noun="subscribers"
              parts={revenue.plans.map((plan, index) => ({
                key: String(plan.id),
                label: `${plan.name} · ${usd(plan.mrr)}`,
                count: plan.subscribers,
                colour: MIX_COLOURS[index % MIX_COLOURS.length],
              }))}
              onOpen={(key) =>
                open(
                  "plan",
                  key,
                  `${revenue.plans.find((p) => String(p.id) === key)?.name ?? "Plan"}: paying companies`,
                )
              }
            />
          )}
        </Card>
      </div>
      <Card className="ui-card">
        <div className="chart-card__header">
          <h2>Subscriptions by state</h2>
        </div>
        <ul className="state-list">
          {states.map(([state, count]) => (
            <li key={state}>
              <ChartMark
                className="state-list__row"
                onOpen={() => open("state", state, `Companies: ${STATE_WORDS[state] ?? state}`)}
                tip={
                  <TipLines title={STATE_WORDS[state] ?? state} lines={[`${count} companies`]} />
                }
              >
                <span>{STATE_WORDS[state] ?? state}</span>
                <span className="revenue-card__track">
                  <span
                    className="revenue-card__bar revenue-card__bar--revenue"
                    style={{ width: `${(count * PERCENT) / stateTotal}%` }}
                  />
                </span>
                <strong>{whole(count)}</strong>
              </ChartMark>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

export function UsageSection({ data }: { data: AdminData }) {
  const { usage } = data;
  const withCost = usage.top_companies.some((company) => company.cost !== undefined);
  return (
    <div className="dashboard__section">
      <TrendCard trend={usage.trend} metrics={TREND_METRICS} />
      <ChartCard title="Companies using the platform most">
        {usage.top_companies.length === 0 ? (
          <p role="status">No CVs scored in this period.</p>
        ) : (
          <Table label="Companies by CVs scored">
            <thead>
              <tr>
                <th scope="col">Company</th>
                <th scope="col">Plan</th>
                <th scope="col">Subscription</th>
                <th scope="col">CVs scored</th>
                {withCost && <th scope="col">Tokens</th>}
                {withCost && <th scope="col">AI cost</th>}
              </tr>
            </thead>
            <tbody>
              {usage.top_companies.map((company) => (
                <tr key={company.id}>
                  <td>
                    <CompanyLink company={company} />
                  </td>
                  <td>{company.plan ?? "No plan"}</td>
                  <td>
                    <Tag variant={company.state === "past_due" ? "danger" : "neutral"}>
                      {STATE_WORDS[company.state] ?? company.state}
                    </Tag>
                  </td>
                  <td>{whole(company.cvs_scored ?? 0)}</td>
                  {withCost && <td>{whole(company.tokens ?? 0)}</td>}
                  {withCost && <td>{usd(company.cost ?? 0)}</td>}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </ChartCard>
    </div>
  );
}

/** How the AI calls went: by purpose and model, the failure rate, the token budget and whether
 * AI work is running. */
export function AiSection({ ai, open }: { ai: NonNullable<AdminData["ai"]>; open: Open }) {
  const costTop = Math.max(0.000001, ...ai.by_model.map((model) => model.cost));
  return (
    <div className="dashboard__section">
      <div className="dashboard__row">
        <Card className="ui-card">
          <div className="chart-card__header">
            <h2>Token budget</h2>
            <Tag variant={ai.control.paused ? "warning" : "neutral"}>
              {ai.control.paused ? "AI work paused" : "AI work running"}
            </Tag>
          </div>
          <Gauge
            percent={ai.tokens.percent}
            scored={ai.tokens.used}
            uploaded={ai.tokens.cap}
            label="of the plans' tokens"
            title="Token budget"
            lines={[
              `${whole(ai.tokens.used)} tokens used in the last ${ai.tokens.days} days`,
              `${whole(ai.tokens.cap)} tokens in the paying plans' caps`,
            ]}
          />
        </Card>
        <Card className="ui-card">
          <div className="chart-card__header">
            <h2>AI calls by purpose</h2>
            {ai.calls.failure_percent === null ? (
              <Tag variant="neutral">No calls</Tag>
            ) : (
              <Tag variant={ai.calls.failure_percent > 0 ? "warning" : "success"}>
                {ai.calls.failure_percent}% failed
              </Tag>
            )}
          </div>
          <Donut
            total={ai.calls.total}
            centreLabel="calls"
            noun="calls"
            parts={ai.by_purpose.map((part) => ({
              key: part.purpose,
              label: PURPOSE_WORDS[part.purpose] ?? part.purpose,
              count: part.count,
              colour: PURPOSE_COLOURS[part.purpose] ?? "grey",
            }))}
            onOpen={(key) => open("ai_purpose", key, `AI calls: ${PURPOSE_WORDS[key] ?? key}`)}
          />
        </Card>
      </div>
      <Card className="ui-card">
        <div className="chart-card__header">
          <h2>Cost by model</h2>
        </div>
        {ai.by_model.length === 0 ? (
          <p role="status">No AI calls in this period.</p>
        ) : (
          <ul className="state-list">
            {ai.by_model.map((model) => (
              <li key={model.model}>
                <ChartMark
                  className="state-list__row"
                  onOpen={() => open("ai_model", model.model, `AI calls: ${model.model}`)}
                  tip={
                    <TipLines
                      title={model.model}
                      lines={[
                        `${whole(model.calls)} calls`,
                        `${whole(model.tokens)} tokens`,
                        usd(model.cost),
                      ]}
                    />
                  }
                >
                  <span>{model.model}</span>
                  <span className="revenue-card__track">
                    <span
                      className="revenue-card__bar revenue-card__bar--cost"
                      style={{ width: `${(model.cost * PERCENT) / costTop}%` }}
                    />
                  </span>
                  <strong>{usd(model.cost)}</strong>
                </ChartMark>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

/** What waits for an admin, each with its count; Review lists the companies or calls. */
export function AttentionSection({ pending, open }: { pending: AdminData["pending"]; open: Open }) {
  const rows = PENDING_ROWS.filter((row) => pending[row.key] !== undefined);
  const total = rows.reduce((sum, row) => sum + (pending[row.key] ?? 0), 0);
  return (
    <Card className="ui-card">
      <div className="chart-card__header">
        <h2>Pending actions</h2>
        <Tag variant={total ? "warning" : "neutral"}>{total} pending</Tag>
      </div>
      <ul className="pending-list">
        {rows.map((row) => (
          <li key={row.key} className={`pending-row pending-row--${row.colour}`}>
            <span className={`pending-row__count pending-row__count--${row.colour}`}>
              {pending[row.key]}
            </span>
            <span className="pending-row__label">{row.label}</span>
            <Button
              variant="secondary"
              disabled={!pending[row.key]}
              onClick={() => open("pending", row.key, row.label)}
            >
              Review
            </Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
