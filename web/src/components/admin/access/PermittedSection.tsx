"use client";

import { useState } from "react";

import { Tabs } from "@/components/ui";

import { GrantList } from "./GrantList";
import { InviteList } from "./InviteList";

const PERMITTED_KINDS = ["permitted_email" as const];

/** Admin-permitted emails: each is given a plan and has its full limits until it is revoked. */
export function PermittedSection() {
  const [version, setVersion] = useState(0);
  return (
    <Tabs
      label="Admin-permitted users"
      tabs={[
        {
          value: "users",
          label: "Users",
          content: <GrantList kind="permitted" refreshKey={version} />,
        },
        {
          value: "emails",
          label: "Emails",
          content: (
            <InviteList kinds={PERMITTED_KINDS} onChange={() => setVersion((value) => value + 1)} />
          ),
        },
      ]}
    />
  );
}
