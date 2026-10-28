"use client";

import * as RadixDialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

import { Button } from "./Button";

/** A popup. `trigger` is the button that opens it; Escape and the close button dismiss it. */
export function Dialog({
  trigger,
  title,
  description,
  children,
}: {
  trigger: ReactNode;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <RadixDialog.Root>
      <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="ui-overlay" />
        <RadixDialog.Content className="ui-dialog">
          <RadixDialog.Title>{title}</RadixDialog.Title>
          <RadixDialog.Description>{description}</RadixDialog.Description>
          {children}
          <div className="ui-dialog__actions">
            <RadixDialog.Close asChild>
              <Button variant="secondary">Close</Button>
            </RadixDialog.Close>
          </div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
