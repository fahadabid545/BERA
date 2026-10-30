"use client";

import { Button, Dialog } from "@/components/ui";

// A client component because the confirm callback cannot be passed from a server page.
export function DeleteConfirmation() {
  return (
    <Dialog
      trigger={<Button variant="danger">Delete</Button>}
      title="Delete this project?"
      confirmLabel="Delete"
      destructive
      onConfirm={() => undefined}
    />
  );
}
