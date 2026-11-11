"use client";

import QRCode from "qrcode";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button, Input } from "@/components/ui";
import type { ApiError, ApiResult } from "@/lib/api";

type Begun = { secret: string; uri: string };
type Confirmed = { recovery_codes: string[] };

/**
 * Sets up an authenticator app, then shows the recovery codes once. The same steps are used
 * at login (a member whose company requires it) and on the Security page, so the caller says
 * which routes to use and what happens when the person is done.
 */
export function AuthenticatorSetup({
  begin,
  confirm,
  onFinished,
}: {
  begin: () => Promise<ApiResult<Begun>>;
  confirm: (code: string) => Promise<ApiResult<Confirmed>>;
  onFinished: () => void;
}) {
  const [app, setApp] = useState<(Begun & { picture: string }) | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [sending, setSending] = useState(false);

  // Starting twice would replace the secret the person has just scanned, so it starts once,
  // even where React runs effects twice (development).
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void begin().then(async (result) => {
      if (!result.ok) return setError(result.error);
      const picture = await QRCode.toDataURL(result.data.uri, { margin: 1, width: 192 });
      setApp({ ...result.data, picture });
    });
  }, [begin]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = String(new FormData(event.currentTarget).get("code") ?? "");
    setSending(true);
    setError(null);
    const result = await confirm(code);
    setSending(false);
    if (result.ok) setCodes(result.data.recovery_codes);
    else setError(result.error);
  }

  if (codes) {
    return (
      <div className="page-form">
        <h2>Recovery codes</h2>
        <p className="two-step-note">
          Each code works once. They are shown only now, so save them somewhere safe.
        </p>
        <ul className="recovery-codes" aria-label="Recovery codes">
          {codes.map((code) => (
            <li key={code}>{code}</li>
          ))}
        </ul>
        <div className="page-actions">
          <Button onClick={onFinished}>I have saved my codes</Button>
        </div>
      </div>
    );
  }

  const fields = error?.fields ?? {};
  const generalError = error && Object.keys(fields).length === 0 ? error.message : null;
  return (
    <form className="page-form" onSubmit={submit} noValidate>
      {app && (
        <>
          <img className="two-step-qr" src={app.picture} alt="QR code for your authenticator app" />
          <p className="two-step-note">
            Cannot scan it? Enter this key in your app: <code>{app.secret}</code>
          </p>
        </>
      )}
      <Input
        label="Code from your app"
        name="code"
        inputMode="numeric"
        autoComplete="one-time-code"
        error={fields.code}
      />
      {generalError && (
        <p className="ui-error" role="alert">
          {generalError}
        </p>
      )}
      <div className="page-actions">
        <Button type="submit" disabled={sending || !app}>
          Turn on
        </Button>
      </div>
    </form>
  );
}
