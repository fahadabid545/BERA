"use client";

import { useState } from "react";

import { Input } from "@/components/ui";
import { PasswordHints } from "@/components/website/PasswordHints";

type Props = {
  passwordLabel: string;
  passwordName: string;
  passwordError?: string;
  /** Leave out where the password is typed only once (sign up). */
  confirm?: { label: string; name: string; error?: string };
};

/** A new password with live hints and, where asked for, a confirm field that says if it matches. */
export function NewPasswordFields({ passwordLabel, passwordName, passwordError, confirm }: Props) {
  const [password, setPassword] = useState("");
  const [repeated, setRepeated] = useState("");

  return (
    <>
      <Input
        label={passwordLabel}
        name={passwordName}
        type="password"
        autoComplete="new-password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        error={passwordError}
      />
      <PasswordHints password={password} />
      {confirm && (
        <>
          <Input
            label={confirm.label}
            name={confirm.name}
            type="password"
            autoComplete="new-password"
            value={repeated}
            onChange={(event) => setRepeated(event.target.value)}
            error={confirm.error}
          />
          {repeated !== "" && !confirm.error && (
            <p className="ui-hint" role="status">
              {repeated === password ? "The passwords match." : "The passwords do not match."}
            </p>
          )}
        </>
      )}
    </>
  );
}
