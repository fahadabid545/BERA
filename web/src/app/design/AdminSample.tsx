"use client";

import { AdminHero } from "@/components/admin/dashboard/AdminHero";

/** The admin overview's own building block with sample figures; the rest of the overview is made
 * of the cards, rings, bars and popups shown above. */
export function AdminSample() {
  return (
    <AdminHero
      totals={{ companies: 128, suspended: 2, paying: 104 }}
      revenue={{
        mrr: 12900,
        ai_cost: 3870,
        margin_days: 30,
        margin_percent: 70,
        plans: [],
        states: {},
      }}
      onSuspended={() => undefined}
    />
  );
}
