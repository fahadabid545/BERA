"use client";

import { useEffect, useState, type FormEvent } from "react";

import { Button, ButtonLink, Input, TextLink } from "@/components/ui";
import { ACCOUNT_LINKS } from "@/components/website/links";
import { NewPasswordFields } from "@/components/website/NewPasswordFields";
import { postJson, whoIsSignedIn, type ApiError } from "@/lib/api";

const LINK_PROBLEMS = ["link_invalid", "link_used", "link_expired"];

/** The page behind the link in the invitation email. `token` is null if the address had none. */
export function AcceptInviteForm({ token }: { token: string | null }) {
  // undefined while checking, null when nobody is logged in.
  const [signedInAs, setSignedInAs] = useState<string | null | undefined>(undefined);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(
    token ? null : { code: "link_invalid", message: "This link is not valid." },
  );
  const [done, setDone] = useState(false);

  useEffect(() => {
    void whoIsSignedIn().then(setSignedInAs);
  }, []);

  async function logOutFirst() {
    await postJson("/api/auth/company/logout/", {});
    setSignedInAs(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSending(true);
    setError(null);
    const result = await postJson("/api/auth/company/accept-invite/", {
      token,
      name: form.get("name"),
      password: form.get("password"),
      confirm_password: form.get("confirm_password"),
    });
    setSending(false);
    if (result.ok) setDone(true);
    else setError(result.error);
  }

  if (signedInAs === undefined) return null;

  if (signedInAs) {
    // The invitation is for someone else's new account, so the person must log out first.
    return (
      <div className="page-form">
        <p role="status">
          You are logged in as {signedInAs}. Log out first to accept this invitation.
        </p>
        <div className="page-actions">
          <Button onClick={logOutFirst}>Log out</Button>
        </div>
      </div>
    );
  }

  if (done) {
    return (
      <div className="page-form">
        <p role="status">You have joined the team. Log in to continue.</p>
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
      </div>
    );
  }

  const fields = error?.fields ?? {};
  const generalError = error && Object.keys(fields).length === 0 ? error.message : null;
  return (
    <form className="page-form" onSubmit={submit} noValidate>
      <Input label="Your name" name="name" autoComplete="name" error={fields.name} />
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
          Join team
        </Button>
      </div>
      <div className="page-links">
        <TextLink href={ACCOUNT_LINKS.logIn.href}>Back to Log in</TextLink>
      </div>
    </form>
  );
}
