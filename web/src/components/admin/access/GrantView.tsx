"use client";

import { useEffect, useState } from "react";

import { ChartCard } from "@/components/charts/ChartCard";
import { Button, Table, Tabs, TextLink } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

import { DailyBars } from "./DailyBars";
import { BASE, day, type Grant, type GrantDetail } from "./types";

const TOKEN_FORMAT = new Intl.NumberFormat("en-US");

/** One person's access: usage and the daily CVs, what the team did, and the feedback they sent. */
export function GrantView({ grant, onBack }: { grant: Grant; onBack: () => void }) {
  const [detail, setDetail] = useState<GrantDetail | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    void getJson<GrantDetail>(`${BASE}access/${grant.id}/`).then((result) => {
      if (result.ok) setDetail(result.data);
      else setError(result.error);
    });
  }, [grant.id]);

  const usage = detail?.usage;
  return (
    <div className="page-stack">
      <div className="page-actions">
        <Button variant="secondary" onClick={onBack}>
          Back to the list
        </Button>
        {grant.company && (
          <TextLink href={`/admin/companies/${grant.company.id}`}>{grant.company.name}</TextLink>
        )}
      </div>
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      {detail && usage && (
        <Tabs
          label="Access details"
          tabs={[
            {
              value: "usage",
              label: "Usage",
              content: (
                <div className="page-stack">
                  <Table label="Usage">
                    <tbody>
                      <tr>
                        <th scope="row">CVs today</th>
                        <td>
                          {usage.cvs_today}
                          {usage.cvs_per_day_limit !== undefined &&
                            ` of ${usage.cvs_per_day_limit}`}
                        </td>
                      </tr>
                      <tr>
                        <th scope="row">CVs this period</th>
                        <td>
                          {usage.cvs_this_period} of {usage.cvs_per_month_limit}
                        </td>
                      </tr>
                      <tr>
                        <th scope="row">AI tokens in</th>
                        <td>{TOKEN_FORMAT.format(usage.tokens_in)}</td>
                      </tr>
                      <tr>
                        <th scope="row">AI tokens out</th>
                        <td>{TOKEN_FORMAT.format(usage.tokens_out)}</td>
                      </tr>
                      <tr>
                        <th scope="row">Estimated cost</th>
                        <td>{usage.estimated_cost}</td>
                      </tr>
                      <tr>
                        <th scope="row">Projects</th>
                        <td>{usage.projects}</td>
                      </tr>
                    </tbody>
                  </Table>
                  <ChartCard title="CVs a day">
                    <DailyBars days={detail.daily_cvs} label="CVs a day" />
                  </ChartCard>
                </div>
              ),
            },
            {
              value: "activity",
              label: "Activity",
              content: (
                <Table label="Activity">
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>Who</th>
                      <th>What</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.activity.map((entry) => (
                      <tr key={entry.id}>
                        <td>{day(entry.created_at)}</td>
                        <td>{entry.actor_name}</td>
                        <td>{entry.kind.replaceAll("_", " ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              ),
            },
            {
              value: "feedback",
              label: "Feedback",
              content: (
                <Table label="Feedback">
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>Who</th>
                      <th>Kind</th>
                      <th>Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.feedback.map((item) => (
                      <tr key={item.id}>
                        <td>{day(item.created_at)}</td>
                        <td>{item.user}</td>
                        <td>{item.kind}</td>
                        <td>{item.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              ),
            },
          ]}
        />
      )}
    </div>
  );
}
