"use client";

import { useState } from "react";

import { Button, Dialog } from "@/components/ui";
import { requestNewVerificationLink } from "@/lib/verification";

/** For someone who just tried to log in with an email that is not verified yet. */
export function ResendVerificationButton({ email }: { email: string }) {
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function resend() {
    setSending(true);
    setFailure(null);
    const result = await requestNewVerificationLink(email);
    setSending(false);
    if (result.ok) setMessage(result.data.message);
    else setFailure(result.error.message);
  }

  return (
    <>
      <Button variant="secondary" onClick={resend} disabled={sending}>
        Resend verification email
      </Button>
      {failure && (
        <p className="ui-error" role="alert">
          {failure}
        </p>
      )}
      <Dialog
        open={message !== null}
        onOpenChange={(open) => !open && setMessage(null)}
        title="Check your email"
        description={message ?? undefined}
      />
    </>
  );
}
