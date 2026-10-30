"use client";

import { useState, type FormEvent } from "react";

import { Button, Dialog, Input } from "@/components/ui";
import { NewPasswordFields } from "@/components/website/NewPasswordFields";
import { postJson, type ApiError } from "@/lib/api";

export function ChangePasswordForm() {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [changed, setChanged] = useState(false);
  // A new key empties the fields after a successful change.
  const [formKey, setFormKey] = useState(0);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSending(true);
    setError(null);
    const result = await postJson("/api/auth/company/change-password/", {
      current_password: form.get("current_password"),
      password: form.get("password"),
      confirm_password: form.get("confirm_password"),
    });
    setSending(false);
    if (result.ok) {
      setChanged(true);
      setFormKey((key) => key + 1);
    } else setError(result.error);
  }

  const fields = error?.fields ?? {};
  const generalError = error && Object.keys(fields).length === 0 ? error.message : null;
  return (
    <>
      <form key={formKey} className="page-form" onSubmit={submit} noValidate>
        <Input
          label="Current password"
          name="current_password"
          type="password"
          autoComplete="current-password"
          error={fields.current_password}
        />
        <NewPasswordFields
          passwordLabel="New password"
          passwordName="password"
          passwordError={fields.password}
          confirm={{
            label: "Confirm new password",
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
            Change password
          </Button>
        </div>
      </form>
      <Dialog
        open={changed}
        onOpenChange={setChanged}
        title="Password changed"
        description="Your other devices were signed out and we sent you a confirmation email."
      />
    </>
  );
}
