"use client";

import { useState } from "react";

import { useLiveCharts } from "@/components/charts/useLiveCharts";
import { ExportDialog } from "@/components/company/dashboard/ExportDialog";
import { Button, SegmentedControl, Tabs } from "@/components/ui";

import { AdminDetailDialog, type AdminDetail } from "./AdminDetailDialog";
import {
  AiSection,
  AttentionSection,
  OverviewSection,
  RevenueSection,
  UsageSection,
  type Open,
} from "./sections";
import type { AdminData } from "./types";

const PERIOD_NAMES: Record<number, string> = { 1: "Today", 7: "This week", 30: "This month" };
export const ADMIN_SECTIONS = ["overview", "revenue", "usage", "ai", "attention"] as const;
export type AdminSection = (typeof ADMIN_SECTIONS)[number];

/** The admin overview, one tab for each question: how the platform is doing, what it earns, who
 * uses it, how the AI behaves, what waits. A support admin gets no Revenue or AI tab: the server
 * leaves those figures out, so the tabs simply are not there. */
export function AdminDashboard({
  tab,
  onTab,
}: {
  tab: AdminSection;
  onTab: (tab: string) => void;
}) {
  const [days, setDays] = useState<number | null>(null);
  const [detail, setDetail] = useState<AdminDetail | null>(null);
  const { data, error } = useLiveCharts<AdminData>(
    `/api/admin/dashboard/${days === null ? "" : `?days=${days}`}`,
  );
  const open: Open = (kind, key, title) => setDetail({ kind, key, title });
  const unavailable = error ? (
    <p className="ui-error" role="alert">
      {error.message}
    </p>
  ) : null;
  const tabs = [
    {
      value: "overview",
      label: "Overview",
      content: data ? <OverviewSection data={data} open={open} /> : unavailable,
    },
    ...(data?.revenue
      ? [
          {
            value: "revenue",
            label: "Revenue",
            content: data?.revenue ? (
              <RevenueSection revenue={data.revenue} open={open} />
            ) : (
              unavailable
            ),
          },
        ]
      : []),
    {
      value: "usage",
      label: "Usage",
      content: data ? <UsageSection data={data} /> : unavailable,
    },
    ...(data?.ai
      ? [
          {
            value: "ai",
            label: "AI",
            content: data?.ai ? <AiSection ai={data.ai} open={open} /> : unavailable,
          },
        ]
      : []),
    {
      value: "attention",
      label: "Attention",
      content: data ? <AttentionSection pending={data.pending} open={open} /> : unavailable,
    },
  ];
  // A tab this role does not have is the first one, not an empty page.
  const shown = tabs.some((item) => item.value === tab) ? tab : tabs[0].value;
  return (
    <div className="dashboard">
      <AdminDetailDialog detail={detail} days={data?.days} onClose={() => setDetail(null)} />
      {data && (
        <div className="dashboard__header">
          <SegmentedControl
            label="Period"
            value={String(data.days)}
            options={data.choices.map((choice) => ({
              value: String(choice),
              label: PERIOD_NAMES[choice] ?? `${choice} days`,
            }))}
            onChange={(value) => setDays(Number(value))}
          />
          <ExportDialog
            area="admin"
            days={data.days}
            trigger={<Button variant="secondary">Export report</Button>}
          />
        </div>
      )}
      <Tabs label="Overview" value={shown} onValueChange={onTab} tabs={tabs} />
    </div>
  );
}
