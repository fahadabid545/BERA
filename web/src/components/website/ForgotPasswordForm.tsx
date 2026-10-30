"use client";

import { useState, type FormEvent } from "react";

import { Button, Dialog, Input, TextLink } from "@/components/ui";
import { ACCOUNT_LINKS } from "@/components/website/links";
import { postJson, type ApiError } from "@/lib/api";

export function ForgotPasswordForm() {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [doneMessage, setDoneMessage] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSending(true);
    setError(null);
    const result = await postJson<{ message: string }>("/api/auth/company/forgot-password/", {
      email: form.get("email"),
    });
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
            Send reset link
          </Button>
        </div>
        <div className="page-links">
          <TextLink href={ACCOUNT_LINKS.logIn.href}>Back to Log in</TextLink>
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
