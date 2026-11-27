"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { ToggleIcon } from "@/components/ui";

import { FeedbackDialog } from "./FeedbackDialog";

/** Feedback and Support, kept below the navigation for every role. */
export function SidebarFooter() {
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const pathname = usePathname();
  return (
    <>
      <FeedbackDialog open={feedbackOpen} onOpenChange={setFeedbackOpen} />
      <button
        type="button"
        className="ui-icon-item panel-group"
        onClick={() => setFeedbackOpen(true)}
      >
        <ToggleIcon name="feedback" />
        <span className="panel-label">Feedback</span>
      </button>
      <Link
        href="/company/support"
        className="ui-icon-item panel-group"
        aria-current={pathname.startsWith("/company/support") ? "page" : undefined}
      >
        <ToggleIcon name="support" />
        <span className="panel-label">Support</span>
      </Link>
    </>
  );
}
