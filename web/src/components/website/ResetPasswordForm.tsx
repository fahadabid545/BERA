"use client";

import { useState, type FormEvent } from "react";

import { Button, ButtonLink, Input, TextLink } from "@/components/ui";
import { ACCOUNT_LINKS } from "@/components/website/links";
import { postJson, type ApiError } from "@/lib/api";

const LINK_PROBLEMS = ["link_invalid", "link_used", "link_expired"];

/** The page behind the link in the reset email. `token` is null if the address had none. */
export function ResetPasswordForm({ token }: { token: string | null }) {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(
    token ? null : { code: "link_invalid", message: "This link is not valid." },
  );
  const [done, setDone] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSending(true);
    setError(null);
    const result = await postJson("/api/auth/company/reset-password/", {
      token,
      password: form.get("password"),
      confirm_password: form.get("confirm_password"),
    });
    setSending(false);
    if (result.ok) setDone(true);
    else setError(result.error);
  }

  if (done) {
    return (
      <div className="page-form">
        <p role="status">Your password was changed. Log in with your new password.</p>
        <div className="page-actions">
          <ButtonLink href={ACCOUNT_LINKS.logIn.href}>Log in</ButtonLink>
        </div>
      </div>
    );
  }

  if (error && LINK_PROBLEMS.includes(error.code)) {
    return (
      <div className="page-form">
        <p className="ui-error" role="alert">
          {error.message}
        </p>
        <div className="page-actions">
          <ButtonLink href={ACCOUNT_LINKS.forgotPassword.href}>Request a new link</ButtonLink>
        </div>
      </div>
    );
  }

  const fields = error?.fields ?? {};
  const generalError = error && Object.keys(fields).length === 0 ? error.message : null;
  return (
    <form className="page-form" onSubmit={submit} noValidate>
      <Input
        label="New password"
        name="password"
        type="password"
        autoComplete="new-password"
        error={fields.password}
      />
      <Input
        label="Confirm password"
        name="confirm_password"
        type="password"
        autoComplete="new-password"
        error={fields.confirm_password}
      />
      {generalError && (
        <p className="ui-error" role="alert">
          {generalError}
        </p>
      )}
      <div className="page-actions">
        <Button type="submit" disabled={sending}>
          Save password
        </Button>
      </div>
      <div className="page-links">
        <TextLink href={ACCOUNT_LINKS.logIn.href}>Back to Log in</TextLink>
      </div>
    </form>
  );
}
