"use client";

import { useEffect, useState } from "react";

import { UserMenu } from "@/components/panel/UserMenu";
import { getJson } from "@/lib/api";
import { askedToday, markAskedToday } from "@/lib/betaFeedbackDay";
import { logOut } from "@/lib/logout";

import { FeedbackDialog } from "./FeedbackDialog";
import { PROFILE_HREF, type CompanyRole } from "./navigation";
import type { PlanAndUsage } from "./UsageMeter";

type Asking = "feedback" | "daily" | "logout";

/** Whether the company is on beta access. Read once; only the owner can read the plan, and a beta
 * company has no other people. */
function useBeta(enabled: boolean) {
  const [beta, setBeta] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let current = true;
    void getJson<PlanAndUsage>("/api/company/usage/").then((result) => {
      if (current && result.ok) setBeta(result.data.free_access?.kind === "beta");
    });
    return () => {
      current = false;
    };
  }, [enabled]);
  return beta;
}

/** The company user menu: Profile, Send feedback and Log out. Everyone signed in may send feedback.
 * A beta user is also asked for feedback the first time they visit each day and when they log out
 * (a browser cannot show a form when a tab is closed). */
export function CompanyUserMenu({ userName, role }: { userName: string; role?: CompanyRole }) {
  const [asking, setAsking] = useState<Asking>("feedback");
  // Closing keeps the kind, so a refused message can bring the same popup back.
  const [open, setOpen] = useState(false);
  const ask = (kind: Asking) => {
    setAsking(kind);
    setOpen(true);
  };
  const beta = useBeta(role === "owner");

  useEffect(() => {
    if (!beta || askedToday()) return;
    markAskedToday();
    ask("daily");
  }, [beta]);

  const leaving = asking === "logout";
  return (
    <>
      <UserMenu
        userName={userName}
        items={[
          { label: "Profile", href: PROFILE_HREF },
          { label: "Send feedback", onSelect: () => ask("feedback") },
        ]}
        onLogOut={beta ? () => ask("logout") : logOut}
      />
      <FeedbackDialog
        open={open}
        onOpenChange={setOpen}
        title={leaving ? "Before you leave" : asking === "daily" ? "Beta feedback" : undefined}
        onSent={leaving ? () => void logOut() : undefined}
        skip={
          leaving ? { label: "Log out without feedback", onSkip: () => void logOut() } : undefined
        }
      />
    </>
  );
}
