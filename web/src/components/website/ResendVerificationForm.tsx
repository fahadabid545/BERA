"use client";

import { useState, type FormEvent } from "react";

import { Button, Dialog, Input } from "@/components/ui";
import type { ApiError } from "@/lib/api";
import { requestNewVerificationLink } from "@/lib/verification";

/** Asks for a new verification link. The answer is the same whatever the email is. */
export function ResendVerificationForm() {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [doneMessage, setDoneMessage] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSending(true);
    setError(null);
    const result = await requestNewVerificationLink(String(form.get("email") ?? ""));
    setSending(false);
    if (result.ok) setDoneMessage(result.data.message);
    else setError(result.error);
  }

  return (
    <>
      <form className="page-form" onSubmit={submit} noValidate>
        <Input
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          error={error?.fields?.email}
        />
        {error && !error.fields?.email && (
          <p className="ui-error" role="alert">
            {error.message}
          </p>
        )}
        <div className="page-actions">
          <Button type="submit" disabled={sending}>
            Resend verification email
          </Button>
        </div>
      </form>
      <Dialog
        open={doneMessage !== null}
        onOpenChange={(open) => !open && setDoneMessage(null)}
        title="Check your email"
        description={doneMessage ?? undefined}
      />
    </>
  );
}
