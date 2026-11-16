"use client";

import { useState, type FormEvent } from "react";

import { Button, Dialog, Input } from "@/components/ui";
import { postJson, type ApiError } from "@/lib/api";

/** Asks for another email address. The current password is needed, and nothing changes until
 * the link sent to the NEW address is opened; the old address is told when it happens. */
export function ChangeEmailForm() {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [asked, setAsked] = useState(false);
  const [formKey, setFormKey] = useState(0);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSending(true);
    setError(null);
    const result = await postJson("/api/company/profile/email/", {
      email: form.get("email"),
      current_password: form.get("current_password"),
    });
    setSending(false);
    if (result.ok) {
      setAsked(true);
      setFormKey((key) => key + 1);
    } else setError(result.error);
  }

  const fields = error?.fields ?? {};
  const generalError = error && Object.keys(fields).length === 0 ? error.message : null;
  return (
    <>
      <form key={formKey} className="page-form" onSubmit={submit} noValidate>
        <Input
          label="New email"
          name="email"
          type="email"
          autoComplete="email"
          error={fields.email}
        />
        <Input
          label="Current password"
          name="current_password"
          type="password"
          autoComplete="current-password"
          error={fields.current_password}
        />
        {generalError && (
          <p className="ui-error" role="alert">
            {generalError}
          </p>
        )}
        <div className="page-actions">
          <Button type="submit" disabled={sending}>
            Change email
          </Button>
        </div>
      </form>
      <Dialog
        open={asked}
        onOpenChange={setAsked}
        title="Check your email"
        description="If the address can be used, we sent a link to it. Your email changes when you open it."
      />
    </>
  );
}
