"use client";

import { useEffect, useState } from "react";

import { Button, Checkbox, Dialog, Table, Tag, Textarea } from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";

type State = { enabled: boolean; message: string };

const BASE = "/api/admin/settings/maintenance/";

/** Maintenance mode: while it is on, companies see the message and cannot upload, and admins sign
 * in as usual. Turning it on or off needs a written reason, because it affects every company. */
export function AdminMaintenance() {
  const [state, setState] = useState<State | null>(null);
  const [open, setOpen] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [message, setMessage] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    void getJson<State>(BASE).then((result) => {
      if (result.ok) setState(result.data);
      else setError(result.error);
    });
  }, []);

  function show() {
    if (!state) return;
    setEnabled(state.enabled);
    setMessage(state.message);
    setReason("");
    setError(null);
    setOpen(true);
  }

  async function save() {
    setError(null);
    const result = await postJson<State>(BASE, { enabled, message, reason });
    if (result.ok) setState(result.data);
    else {
      setError(result.error);
      // The popup closes when confirmed; a refused form comes back with what was typed.
      setOpen(true);
    }
  }

  if (!state) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const fields = error?.fields ?? {};
  const generalError = error && Object.keys(fields).length === 0 ? error.message : null;
  return (
    <div className="page-stack">
      {generalError && !open && (
        <p className="ui-error" role="alert">
          {generalError}
        </p>
      )}
      <Table label="Maintenance mode">
        <thead>
          <tr>
            <th scope="col">Status</th>
            <th scope="col">Message</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>
              <Tag variant={state.enabled ? "warning" : "neutral"}>
                {state.enabled ? "On" : "Off"}
              </Tag>
            </td>
            <td>{state.message}</td>
          </tr>
        </tbody>
      </Table>
      <div className="page-actions">
        <Button onClick={show}>Change</Button>
      </div>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Maintenance mode"
        confirmLabel="Save"
        onConfirm={() => void save()}
      >
        <div className="page-stack">
          <Checkbox
            label="Maintenance mode is on"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          <Textarea
            label="Message"
            value={message}
            error={fields.message}
            onChange={(event) => setMessage(event.target.value)}
          />
          <Textarea
            label="Reason"
            value={reason}
            error={fields.reason}
            onChange={(event) => setReason(event.target.value)}
          />
          {generalError && (
            <p className="ui-error" role="alert">
              {generalError}
            </p>
          )}
        </div>
      </Dialog>
    </div>
  );
}
