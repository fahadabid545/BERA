"use client";

import { useEffect, useState } from "react";

import { Button, Dialog } from "@/components/ui";
import { goToLogin, onUploadsAtRisk } from "@/lib/session";

/**
 * Shown instead of leaving the page when the session ends while files are still uploading,
 * so they are not lost without the person knowing.
 */
export function SessionEndedWarning() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    onUploadsAtRisk(() => setOpen(true));
    return () => onUploadsAtRisk(null);
  }, []);

  return (
    <Dialog
      open={open}
      onOpenChange={setOpen}
      title="Your session has ended"
      description="Files that are still uploading may be lost. Log in again to continue."
      actions={<Button onClick={goToLogin}>Log in</Button>}
    />
  );
}
