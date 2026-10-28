"use client";

import * as RadixTooltip from "@radix-ui/react-tooltip";
import type { ReactElement } from "react";

/** Shows on hover and on keyboard focus. `children` must be a single focusable element. */
export function Tooltip({ content, children }: { content: string; children: ReactElement }) {
  return (
    <RadixTooltip.Provider delayDuration={200}>
      <RadixTooltip.Root>
        <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
        <RadixTooltip.Portal>
          <RadixTooltip.Content className="ui-tooltip" sideOffset={6}>
            {content}
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  );
}
