"use client";

import { useState, type FormEvent } from "react";

import { Button, ButtonLink } from "@/components/ui";
import { NewPasswordFields } from "@/components/website/NewPasswordFields";
import { postJson, type ApiError } from "@/lib/api";

const LINK_PROBLEMS = ["link_invalid", "link_used", "link_expired", "account_exists"];

/** The page behind the link in an admin invitation email. `token` is null if the address had none.
 * After this the new admin signs in and sets up two-step verification, like every admin. */
export function AdminAcceptInviteForm({ token }: { token: string | null }) {
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
    const result = await postJson("/api/auth/admin/accept-invite/", {
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
        <p role="status">Your account is ready. Sign in to continue.</p>
        <div className="page-actions">
          <ButtonLink href="/admin/login">Sign in</ButtonLink>
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
      </div>
    );
  }
  const fields = error?.fields ?? {};
  const generalError = error && Object.keys(fields).length === 0 ? error.message : null;
  return (
    <form className="page-form" onSubmit={submit} noValidate>
      <NewPasswordFields
        passwordLabel="Password"
        passwordName="password"
        passwordError={fields.password}
        confirm={{
          label: "Confirm password",
          name: "confirm_password",
          error: fields.confirm_password,
        }}
      />
      {generalError && (
        <p className="ui-error" role="alert">
          {generalError}
        </p>
      )}
      <div className="page-actions">
        <Button type="submit" disabled={sending}>
          Set password
        </Button>
      </div>
    </form>
  );
}
