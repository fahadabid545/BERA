"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Button, Dialog, Input, Table } from "@/components/ui";
import { deleteJson, getJson, postJson, type ApiError } from "@/lib/api";

const BASE = "/api/company/team/invites/";

type Invite = {
  id: string;
  email: string;
  status: "pending" | "expired";
  expires_at: string | null;
};

/** Invite members, and the invitations still waiting, with Resend and Revoke. */
export function TeamInvites() {
  const [invites, setInvites] = useState<Invite[]>([]);
  const [inviting, setInviting] = useState(false);
  const [sending, setSending] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);
  const [listError, setListError] = useState<ApiError | null>(null);
  const [sent, setSent] = useState(false);

  const load = useCallback(async () => {
    const result = await getJson<Invite[]>(BASE);
    if (result.ok) setInvites(result.data);
    else setListError(result.error);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const email = String(new FormData(event.currentTarget).get("email") ?? "");
    setSending(true);
    setFormError(null);
    const result = await postJson(BASE, { email });
    setSending(false);
    if (!result.ok) return setFormError(result.error);
    setInviting(false);
    setSent(true);
    await load();
  }

  async function resend(id: string) {
    setListError(null);
    const result = await postJson(`${BASE}${id}/resend/`, {});
    if (result.ok) {
      setSent(true);
      await load();
    } else setListError(result.error);
  }

  async function revoke(id: string) {
    setListError(null);
    const result = await deleteJson(`${BASE}${id}/`);
    if (result.ok) await load();
    else setListError(result.error);
  }

  const fields = formError?.fields ?? {};
  const generalError = formError && Object.keys(fields).length === 0 ? formError.message : null;
  return (
    <div className="page-stack">
      <div className="page-actions">
        <Button
          onClick={() => {
            setFormError(null);
            setInviting(true);
          }}
        >
          Invite member
        </Button>
      </div>
      {listError && (
        <p className="ui-error" role="alert">
          {listError.message}
        </p>
      )}
      {invites.length > 0 && (
        <Table label="Pending invitations">
          <thead>
            <tr>
              <th scope="col">Email</th>
              <th scope="col">Status</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {invites.map((invite) => (
              <tr key={invite.id}>
                <td>{invite.email}</td>
                <td>{invite.status === "expired" ? "Expired" : "Pending"}</td>
                <td>
                  <div className="page-actions">
                    <Button
                      variant="secondary"
                      aria-label={`Resend invitation to ${invite.email}`}
                      onClick={() => resend(invite.id)}
                    >
                      Resend
                    </Button>
                    <Dialog
                      trigger={
                        <Button
                          variant="secondary"
                          aria-label={`Revoke invitation to ${invite.email}`}
                        >
                          Revoke
                        </Button>
                      }
                      title="Revoke invitation"
                      description={`The invitation to ${invite.email} will stop working.`}
                      confirmLabel="Revoke"
                      onConfirm={() => revoke(invite.id)}
                      destructive
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <Dialog open={inviting} onOpenChange={setInviting} title="Invite member">
        <form className="page-form" onSubmit={invite} noValidate>
          <Input label="Email" name="email" type="email" autoComplete="off" error={fields.email} />
          {generalError && (
            <p className="ui-error" role="alert">
              {generalError}
            </p>
          )}
          <div className="page-actions">
            <Button type="submit" disabled={sending}>
              Send invitation
            </Button>
          </div>
        </form>
      </Dialog>
      <Dialog open={sent} onOpenChange={setSent} title="Invitation sent" />
    </div>
  );
}
