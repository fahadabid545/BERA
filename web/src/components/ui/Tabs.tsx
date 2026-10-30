"use client";

import * as RadixTabs from "@radix-ui/react-tabs";
import type { ReactNode } from "react";

export type TabItem = { value: string; label: string; content: ReactNode };

type TabsProps = {
  label: string;
  tabs: TabItem[];
  /** Pass both to control the chosen tab, e.g. to keep it in the address. */
  value?: string;
  onValueChange?: (value: string) => void;
};

export function Tabs({ label, tabs, value, onValueChange }: TabsProps) {
  return (
    <RadixTabs.Root defaultValue={tabs[0]?.value} value={value} onValueChange={onValueChange}>
      <RadixTabs.List className="ui-tabs-list" aria-label={label}>
        {tabs.map((tab) => (
          <RadixTabs.Trigger key={tab.value} value={tab.value} className="ui-tab">
            {tab.label}
          </RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
      {tabs.map((tab) => (
        <RadixTabs.Content key={tab.value} value={tab.value} className="ui-tab-panel">
          {tab.content}
        </RadixTabs.Content>
      ))}
    </RadixTabs.Root>
  );
}
