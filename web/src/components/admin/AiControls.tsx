"use client";

import { useEffect, useState } from "react";

import { Button, Dialog, Input } from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";

type State = {
  paused: boolean;
  paused_by_admin: boolean;
  paused_automatically: boolean;
  resumes_at: string | null;
  message: string;
};

const BASE = "/api/admin/ai/controls/";

function status(state: State) {
  if (state.paused_by_admin) return "AI work is paused by an admin.";
  if (state.paused_automatically) return "AI work is paused automatically.";
  return "AI work is running.";
}

/** The switch that pauses all AI work at once and resumes it. Both need a reason, which goes
 * in the audit log. An automatic pause after repeated failures shows here too. */
export function AiControls() {
  const [state, setState] = useState<State | null>(null);
  const [open, setOpen] = useState<"pause" | "resume" | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    void getJson<State>(BASE).then((result) => {
      if (result.ok) setState(result.data);
      else setError(result.error);
    });
  }, []);

  async function confirm() {
    if (!open) return;
    setError(null);
    const result = await postJson<State>(`${BASE}${open}/`, { reason });
    if (result.ok) {
      setState(result.data);
      setReason("");
      return setOpen(null);
    }
    setError(result.error);
  }

  if (!state) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  return (
    <div className="page-stack">
      <p role="status">{status(state)}</p>
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      <div className="page-actions">
        <Button variant="danger" disabled={state.paused_by_admin} onClick={() => setOpen("pause")}>
          Pause all AI
        </Button>
        <Button variant="secondary" disabled={!state.paused} onClick={() => setOpen("resume")}>
          Resume AI
        </Button>
      </div>
      <Dialog
        open={open !== null}
        onOpenChange={(next) => !next && setOpen(null)}
        title={open === "pause" ? "Pause all AI" : "Resume AI"}
        confirmLabel={open === "pause" ? "Pause all AI" : "Resume AI"}
        destructive={open === "pause"}
        onConfirm={() => void confirm()}
      >
        <Input label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
      </Dialog>
    </div>
  );
}
