"use client";

import { useState } from "react";

import { ToggleIcon } from "@/components/ui";

import { FeedbackDialog } from "./FeedbackDialog";

/** Feedback and Support, kept below the navigation for every role. */
export function SidebarFooter() {
  const [feedbackOpen, setFeedbackOpen] = useState(false);
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
    </>
  );
}
