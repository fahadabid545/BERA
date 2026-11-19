"use client";

import { useState } from "react";

import { Button, ButtonLink } from "@/components/ui";
import { ACCOUNT_LINKS } from "@/components/website/links";
import { postJson } from "@/lib/api";

type State =
  | { step: "ready" }
  | { step: "working" }
  | { step: "restored" }
  | { step: "refused"; message: string };

const NOT_VALID = "This link is not valid.";

/** The page behind the undo link in the deletion email. Opening it changes nothing; pressing the
 * button does, so mail programs that open links to check them cannot use it up. */
export function UndoCompanyDeletion({ token }: { token: string | null }) {
  const [state, setState] = useState<State>(
    token ? { step: "ready" } : { step: "refused", message: NOT_VALID },
  );

  async function undo() {
    setState({ step: "working" });
    const result = await postJson("/api/auth/company/undo-deletion/", { token });
    setState(result.ok ? { step: "restored" } : { step: "refused", message: result.error.message });
  }

  if (state.step === "restored") {
    return (
      <div className="page-form">
        <p role="status">Your company will not be deleted. You can log in again.</p>
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
      <Button onClick={undo} disabled={state.step === "working"}>
        Undo the deletion
      </Button>
    </div>
  );
}
