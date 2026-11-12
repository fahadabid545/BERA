"use client";

import { useState, type FormEvent } from "react";

import { Button, Input, TextLink } from "@/components/ui";
import { postJson, type ApiError } from "@/lib/api";

const CHALLENGE_ENDED = "two_step_challenge_ended";

/** The step after a right password for a person who has two-step verification on. */
export function TwoStepLogin({
  challenge,
  onSignedIn,
  onStartOver,
  forAdmin = false,
}: {
  challenge: string;
  onSignedIn: () => void;
  onStartOver: () => void;
  /** Admins have no recovery codes and no support contact; their wrong-code message says who resets a lost device. */
  forAdmin?: boolean;
}) {
  const [useRecoveryCode, setUseRecoveryCode] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = String(new FormData(event.currentTarget).get("code") ?? "");
    setSending(true);
    setError(null);
    const kind = forAdmin ? "admin" : "company";
    const result = await postJson(`/api/auth/${kind}/login/two-step/`, { challenge, code });
    if (result.ok) return onSignedIn();
    setSending(false);
    setError(result.error);
  }

  const fields = error?.fields ?? {};
  const generalError = error && Object.keys(fields).length === 0 ? error.message : null;
  return (
    <form className="page-form" onSubmit={submit} noValidate>
      <Input
        key={String(useRecoveryCode)}
        label={useRecoveryCode ? "Recovery code" : "Code from your app"}
        name="code"
        inputMode={useRecoveryCode ? "text" : "numeric"}
        autoComplete="one-time-code"
        error={fields.code}
      />
      {generalError && (
        <p className="ui-error" role="alert">
          {generalError}
        </p>
      )}
      <div className="page-actions">
        <Button type="submit" disabled={sending}>
          Verify
        </Button>
        {error?.code === CHALLENGE_ENDED && (
          <Button variant="secondary" onClick={onStartOver}>
            Back to login
          </Button>
        )}
      </div>
      {!forAdmin && (
        <>
          <div className="page-links">
            <Button variant="secondary" onClick={() => setUseRecoveryCode((current) => !current)}>
              {useRecoveryCode ? "Use the code from my app" : "Use a recovery code"}
            </Button>
          </div>
          <p className="two-step-note">
            Lost your device and your recovery codes?{" "}
            <TextLink href="/contact">Contact support</TextLink>. We will check your identity before
            we can help.
          </p>
        </>
      )}
    </form>
  );
}
