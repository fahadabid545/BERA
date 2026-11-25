"use client";

import { useState } from "react";

import { UserMenu } from "@/components/panel/UserMenu";

import { FeedbackDialog } from "./FeedbackDialog";
import { PROFILE_HREF } from "./navigation";

/** The company user menu: Profile, Send feedback and Log out. Everyone signed in may send feedback. */
export function CompanyUserMenu({ userName }: { userName: string }) {
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  return (
    <>
      <UserMenu
        userName={userName}
        items={[
          { label: "Profile", href: PROFILE_HREF },
          { label: "Send feedback", onSelect: () => setFeedbackOpen(true) },
        ]}
      />
      <FeedbackDialog open={feedbackOpen} onOpenChange={setFeedbackOpen} />
    </>
  );
}
