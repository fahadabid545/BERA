"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button, Input, TextLink } from "@/components/ui";
import { ACCOUNT_LINKS } from "@/components/website/links";
import { ResendVerificationButton } from "@/components/website/ResendVerificationButton";
import { postJson, type ApiError } from "@/lib/api";
import { pageAfterLogin } from "@/lib/redirect";

const EMAIL_NOT_VERIFIED = "email_not_verified";

export function LoginForm({ next }: { next?: string | string[] }) {
  const router = useRouter();
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [typedEmail, setTypedEmail] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "");
    setSending(true);
    setError(null);
    setTypedEmail(email);
    const result = await postJson("/api/auth/company/login/", {
      email,
      password: form.get("password"),
    });
    if (result.ok) {
      router.push(pageAfterLogin(next));
      return;
    }
    setSending(false);
    setError(result.error);
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
      {error?.code === EMAIL_NOT_VERIFIED && <ResendVerificationButton email={typedEmail} />}
      <div className="page-actions">
        <Button type="submit" disabled={sending}>
          Log in
        </Button>
      </div>
      <div className="page-links">
        <TextLink href={ACCOUNT_LINKS.forgotPassword.href}>Forgot password?</TextLink>
        <TextLink href={ACCOUNT_LINKS.resendVerification.href}>
          {ACCOUNT_LINKS.resendVerification.label}
        </TextLink>
        <TextLink href={ACCOUNT_LINKS.signUp.href}>Create an account</TextLink>
      </div>
    </form>
  );
}
