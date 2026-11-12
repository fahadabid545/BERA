"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button, Input } from "@/components/ui";
import { AuthenticatorSetup } from "@/components/website/AuthenticatorSetup";
import { TwoStepLogin } from "@/components/website/TwoStepLogin";
import { postJson, type ApiError } from "@/lib/api";

const SETUP_BASE = "/api/auth/admin/login/two-step/setup/";
const ADMIN_HOME = "/admin";

type LoginReply = { status: "two_step_required" | "two_step_setup_required"; challenge: string };
/** Where the login is: the password alone never finishes it. */
type Pending = { step: "code" | "setup"; challenge: string };

export function AdminLoginForm() {
  const router = useRouter();
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const signedIn = () => router.push(ADMIN_HOME);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSending(true);
    setError(null);
    const result = await postJson<LoginReply>("/api/auth/admin/login/", {
      email: form.get("email"),
      password: form.get("password"),
    });
    setSending(false);
    if (!result.ok) return setError(result.error);
    setPending({
      step: result.data.status === "two_step_required" ? "code" : "setup",
      challenge: result.data.challenge,
    });
  }

  if (pending?.step === "code") {
    return (
      <TwoStepLogin
        forAdmin
        challenge={pending.challenge}
        onSignedIn={signedIn}
        onStartOver={() => setPending(null)}
      />
    );
  }
  if (pending?.step === "setup") {
    const { challenge } = pending;
    return (
      <AuthenticatorSetup
        begin={() => postJson(SETUP_BASE, { challenge })}
        confirm={(code) => postJson(`${SETUP_BASE}confirm/`, { challenge, code })}
        onFinished={signedIn}
      />
    );
  }

  const fields = error?.fields ?? {};
  const generalError = error && Object.keys(fields).length === 0 ? error.message : null;
  return (
    <form className="page-form" onSubmit={submit} noValidate>
      <Input label="Email" name="email" type="email" autoComplete="email" error={fields.email} />
      <Input
        label="Password"
        name="password"
        type="password"
        autoComplete="current-password"
        error={fields.password}
      />
      {generalError && (
        <p className="ui-error" role="alert">
          {generalError}
        </p>
      )}
      <div className="page-actions">
        <Button type="submit" disabled={sending}>
          Log in
        </Button>
      </div>
    </form>
  );
}
