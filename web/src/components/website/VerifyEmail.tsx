"use client";

import { useState } from "react";

import { Button, ButtonLink } from "@/components/ui";
import { ACCOUNT_LINKS } from "@/components/website/links";
import { ResendVerificationForm } from "@/components/website/ResendVerificationForm";
import { postJson } from "@/lib/api";

type State =
  | { step: "ready" }
  | { step: "working" }
  | { step: "verified" }
  | { step: "refused"; message: string };

const NOT_VALID = "This link is not valid.";

/**
 * The page behind the link in the verification email. Opening the link changes nothing;
 * pressing the button does, so mail programs that open links to check them cannot use it up.
 * Whoever is signed in is left alone: the link alone decides which email is verified.
 */
export function VerifyEmail({ token }: { token: string | null }) {
  const [state, setState] = useState<State>(
    token ? { step: "ready" } : { step: "refused", message: NOT_VALID },
  );

  async function verify() {
    setState({ step: "working" });
    const result = await postJson("/api/auth/company/verify-email/", { token });
    setState(result.ok ? { step: "verified" } : { step: "refused", message: result.error.message });
  }

  if (state.step === "verified") {
    return (
      <div className="page-form">
        <p role="status">Your email is verified.</p>
        <div className="page-actions">
          <ButtonLink href={ACCOUNT_LINKS.logIn.href}>Log in</ButtonLink>
        </div>
      </div>
    );
  }
  if (state.step === "refused") {
    return (
      <>
        <p className="ui-error page-form" role="alert">
          {state.message}
        </p>
        <ResendVerificationForm />
      </>
    );
  }
  return (
    <div className="page-actions">
      <Button onClick={verify} disabled={state.step === "working"}>
        Verify email
      </Button>
    </div>
  );
}
