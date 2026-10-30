"use client";

import { Button, Dialog } from "@/components/ui";
import { logOutEverywhere } from "@/lib/logout";

export function SignOutEverywhere() {
  return (
    <Dialog
      trigger={<Button variant="secondary">Sign out of all devices</Button>}
      title="Sign out of all devices"
      description="Everyone using this account, on every device, will have to log in again."
      confirmLabel="Sign out of all devices"
      onConfirm={logOutEverywhere}
    />
  );
}
