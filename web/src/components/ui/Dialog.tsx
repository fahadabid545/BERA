"use client";

import * as RadixDialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

import { Button } from "./Button";

/**
 * A popup. `trigger` is the button that opens it; Escape and the close button dismiss it.
 * Pass `confirmLabel` and `onConfirm` to make it a confirmation: Cancel plus the confirm button.
 */
export function Dialog({
  trigger,
  title,
  description,
  confirmLabel,
  onConfirm,
  destructive = false,
  children,
}: {
  trigger: ReactNode;
  title: string;
  description?: string;
  confirmLabel?: string;
  onConfirm?: () => void;
  destructive?: boolean;
  children?: ReactNode;
}) {
  const isConfirmation = Boolean(confirmLabel && onConfirm);
  return (
    <RadixDialog.Root>
      <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="ui-overlay" />
        <RadixDialog.Content className="ui-dialog" aria-describedby={description ? undefined : ""}>
          <RadixDialog.Title>{title}</RadixDialog.Title>
          {description && <RadixDialog.Description>{description}</RadixDialog.Description>}
          {children}
          <div className="ui-dialog__actions">
            <RadixDialog.Close asChild>
              <Button variant="secondary">{isConfirmation ? "Cancel" : "Close"}</Button>
            </RadixDialog.Close>
            {isConfirmation && (
              <RadixDialog.Close asChild>
                <Button variant={destructive ? "danger" : "primary"} onClick={onConfirm}>
                  {confirmLabel}
                </Button>
              </RadixDialog.Close>
            )}
          </div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
