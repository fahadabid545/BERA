"use client";

import { useState } from "react";

import { Button, ButtonLink } from "@/components/ui";
import { ACCOUNT_LINKS } from "@/components/website/links";
import { postJson } from "@/lib/api";

type State =
  | { step: "ready" }
  | { step: "working" }
  | { step: "changed" }
  | { step: "refused"; message: string };

const NOT_VALID = "This link is not valid.";

/** The page behind the link sent to the new address. Opening it changes nothing; pressing the
 * button does, so mail programs that open links to check them cannot use it up. */
export function ConfirmEmailChange({ token }: { token: string | null }) {
  const [state, setState] = useState<State>(
    token ? { step: "ready" } : { step: "refused", message: NOT_VALID },
  );

  async function confirm() {
    setState({ step: "working" });
    const result = await postJson("/api/auth/company/confirm-email-change/", { token });
    setState(result.ok ? { step: "changed" } : { step: "refused", message: result.error.message });
  }

  if (state.step === "changed") {
    return (
      <div className="page-form">
        <p role="status">Your email address was changed. Use it the next time you log in.</p>
        <div className="page-actions">
          <ButtonLink href={ACCOUNT_LINKS.logIn.href}>Log in</ButtonLink>
        </div>
      </div>
    );
  }
  if (state.step === "refused") {
    return (
      <p className="ui-error page-form" role="alert">
        {state.message}
      </p>
    );
  }
  return (
    <div className="page-actions">
      <Button onClick={confirm} disabled={state.step === "working"}>
        Confirm email address
      </Button>
    </div>
  );
}
