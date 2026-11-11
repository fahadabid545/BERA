"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Button, Dialog, Input } from "@/components/ui";
import { AuthenticatorSetup } from "@/components/website/AuthenticatorSetup";
import { getJson, postJson, putJson, type ApiError } from "@/lib/api";

const BASE = "/api/auth/company/two-step/";

type Status = { enabled: boolean; recovery_codes_left: number; required_by_company: boolean };

/** The owner's two-step verification controls on Advanced > Security. */
export function TwoStepSettings() {
  const [status, setStatus] = useState<Status | null>(null);
  const [settingUp, setSettingUp] = useState(false);
  const [turningOff, setTurningOff] = useState(false);
  const [offDetails, setOffDetails] = useState<{ password: string; code: string } | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    const result = await getJson<Status>(BASE);
    if (result.ok) setStatus(result.data);
    else setError(result.error);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  function askToTurnOff(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    setOffDetails({
      password: String(form.get("password") ?? ""),
      code: String(form.get("code") ?? ""),
    });
    setTurningOff(true);
  }

  async function turnOff() {
    if (!offDetails) return;
    const result = await postJson(`${BASE}turn-off/`, offDetails);
    setOffDetails(null);
    if (result.ok) await load();
    else setError(result.error);
  }

  async function setRequirement(required: boolean) {
    setError(null);
    const result = await putJson(`${BASE}company-requirement/`, { required });
    if (result.ok) await load();
    else setError(result.error);
  }

  const fields = error?.fields ?? {};
  const generalError = error && Object.keys(fields).length === 0 ? error.message : null;

  if (settingUp) {
    return (
      <AuthenticatorSetup
        begin={() => postJson(`${BASE}setup/`, {})}
        confirm={(code) => postJson(`${BASE}setup/confirm/`, { code })}
        onFinished={() => {
          setSettingUp(false);
          void load();
        }}
      />
    );
  }
  if (!status) {
    return generalError ? (
      <p className="ui-error" role="alert">
        {generalError}
      </p>
    ) : null;
  }

  return (
    <div className="page-form page-stack">
      {generalError && (
        <p className="ui-error" role="alert">
          {generalError}
        </p>
      )}
      {status.enabled ? (
        <>
          <p className="two-step-note">
            Two-step verification is on. Recovery codes left: {status.recovery_codes_left}
          </p>
          <form onSubmit={askToTurnOff} noValidate>
            <Input
              label="Password"
              name="password"
              type="password"
              autoComplete="current-password"
              error={fields.password}
            />
            <Input
              label="Code from your app or a recovery code"
              name="code"
              autoComplete="one-time-code"
              error={fields.code}
            />
            <div className="page-actions">
              <Button type="submit" variant="secondary">
                Turn off two-step verification
              </Button>
            </div>
          </form>
          <Dialog
            open={turningOff}
            onOpenChange={setTurningOff}
            title="Turn off two-step verification"
            confirmLabel="Turn off"
            onConfirm={turnOff}
            destructive
          />
        </>
      ) : (
        <div className="page-actions">
          <Button onClick={() => setSettingUp(true)}>Set up two-step verification</Button>
        </div>
      )}
      <div className="page-actions">
        {status.required_by_company ? (
          <Dialog
            trigger={<Button variant="secondary">Stop requiring it for members</Button>}
            title="Stop requiring two-step verification"
            confirmLabel="Stop requiring"
            onConfirm={() => setRequirement(false)}
          />
        ) : (
          <Dialog
            trigger={<Button variant="secondary">Require it for all members</Button>}
            title="Require two-step verification"
            description="Members must set it up the next time they log in."
            confirmLabel="Require it"
            onConfirm={() => setRequirement(true)}
          />
        )}
      </div>
    </div>
  );
}
