"use client";

import { Tabs } from "@/components/ui";
import { useTabParam } from "@/lib/useTabParam";

import { SupportChat } from "./SupportChat";
import { TicketList } from "./TicketList";

const TABS = ["chat", "tickets"] as const;

/** Support: describe a problem to the support agent, or follow the tickets already sent. */
export function SupportPage() {
  const [tab, chooseTab] = useTabParam(TABS);
  return (
    <Tabs
      label="Support"
      value={tab}
      onValueChange={chooseTab}
      tabs={[
        { value: "chat", label: "Ask support", content: <SupportChat /> },
        { value: "tickets", label: "My tickets", content: <TicketList /> },
      ]}
    />
  );
}
