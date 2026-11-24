"use client";

import { useCallback, useEffect, useState } from "react";

import {
  Button,
  Dialog,
  Input,
  Select,
  Table,
  Tag,
  Textarea,
  type TagVariant,
} from "@/components/ui";
import { getJson, postJson, type ApiError, type ApiResult } from "@/lib/api";

type Role = "super" | "support";
type Admin = {
  id: number;
  name: string;
  email: string;
  role: Role;
  status: "active" | "blocked";
  two_step_enabled: boolean;
};
type Invitation = {
  id: number;
  name: string;
  email: string;
  role: Role;
  status: "pending" | "expired";
};
type Team = { admins: Admin[]; invitations: Invitation[] };
type Open =
  | { kind: "invite" }
  | { kind: "role"; admin: Admin }
  | { kind: "status"; admin: Admin }
  | { kind: "revoke"; invitation: Invitation };

const BASE = "/api/admin/admin-users/";
const ROLE_WORDS: Record<Role, string> = { super: "Super admin", support: "Support" };
const ROLES = Object.keys(ROLE_WORDS) as Role[];
const STATUS_TAGS: Record<Admin["status"], TagVariant> = { active: "success", blocked: "danger" };
const STATUS_WORDS: Record<Admin["status"], string> = { active: "Active", blocked: "Disabled" };
const EMPTY = { name: "", email: "", role: "support" as Role, reason: "" };

/** The admin team: who is an admin, their role and whether they can sign in, and the invitations
 * still waiting. Super admins only (the server refuses everyone else). Two-step verification is
 * required of every admin, so it is shown, never switched. */
export function AdminUsers() {
  const [team, setTeam] = useState<Team | null>(null);
  const [open, setOpen] = useState<Open | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    const result = await getJson<Team>(BASE);
    if (result.ok) setTeam(result.data);
    else setError(result.error);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  function show(next: Open) {
    setError(null);
    setForm(next.kind === "role" ? { ...EMPTY, role: next.admin.role } : EMPTY);
    setOpen(next);
  }

  async function finish(result: ApiResult<Team>, reopen: Open | null) {
    if (result.ok) return setTeam(result.data);
    setError(result.error);
    // The popup closes when confirmed; a refused form comes back with what was typed.
    setOpen(reopen);
  }

  async function confirm() {
    if (!open) return;
    setError(null);
    if (open.kind === "invite") {
      await finish(await postJson<Team>(`${BASE}invitations/`, form), open);
    } else if (open.kind === "role") {
      await finish(
        await postJson<Team>(`${BASE}${open.admin.id}/role/`, {
          role: form.role,
          reason: form.reason,
        }),
        open,
      );
    } else if (open.kind === "status") {
      await finish(
        await postJson<Team>(`${BASE}${open.admin.id}/status/`, {
          status: open.admin.status === "active" ? "blocked" : "active",
          reason: form.reason,
        }),
        open,
      );
    } else {
      await finish(
        await postJson<Team>(`${BASE}invitations/${open.invitation.id}/revoke/`, {}),
        null,
      );
    }
  }

  async function resend(invitation: Invitation) {
    setError(null);
    await finish(await postJson<Team>(`${BASE}invitations/${invitation.id}/resend/`, {}), null);
  }

  if (!team) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const fields = error?.fields ?? {};
  const alertText = error && Object.keys(fields).length === 0 ? error.message : null;
  const roleOptions = ROLES.map((role) => ({ value: role, label: ROLE_WORDS[role] }));
  const reasonField = (
    <Textarea
      label="Reason"
      value={form.reason}
      error={fields.reason}
      onChange={(event) => setForm({ ...form, reason: event.target.value })}
    />
  );
  const titles = {
    invite: "Invite admin",
    role: "Change role",
    status:
      open?.kind === "status" && open.admin.status === "active" ? "Disable admin" : "Enable admin",
    revoke: "Revoke this invitation?",
  };

  return (
    <div className="page-stack">
      {alertText && !open && (
        <p className="ui-error" role="alert">
          {alertText}
        </p>
      )}
      <div className="page-actions">
        <Button onClick={() => show({ kind: "invite" })}>Invite admin</Button>
      </div>
      <Table label="Admins">
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Email</th>
            <th scope="col">Role</th>
            <th scope="col">Status</th>
            <th scope="col">Two-step</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {team.admins.map((admin) => (
            <tr key={admin.id}>
              <th scope="row">{admin.name}</th>
              <td>{admin.email}</td>
              <td>{ROLE_WORDS[admin.role]}</td>
              <td>
                <Tag variant={STATUS_TAGS[admin.status]}>{STATUS_WORDS[admin.status]}</Tag>
              </td>
              <td>{admin.two_step_enabled ? "On" : "Not set up yet"}</td>
              <td>
                <div className="page-actions">
                  <Button variant="secondary" onClick={() => show({ kind: "role", admin })}>
                    Change role
                  </Button>
                  <Button variant="secondary" onClick={() => show({ kind: "status", admin })}>
                    {admin.status === "active" ? "Disable" : "Enable"}
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      {team.invitations.length > 0 && (
        <Table label="Invitations">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Email</th>
              <th scope="col">Role</th>
              <th scope="col">Status</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {team.invitations.map((invitation) => (
              <tr key={invitation.id}>
                <th scope="row">{invitation.name}</th>
                <td>{invitation.email}</td>
                <td>{ROLE_WORDS[invitation.role]}</td>
                <td>
                  <Tag variant={invitation.status === "pending" ? "neutral" : "warning"}>
                    {invitation.status === "pending" ? "Pending" : "Expired"}
                  </Tag>
                </td>
                <td>
                  <div className="page-actions">
                    <Button variant="secondary" onClick={() => void resend(invitation)}>
                      Resend
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => show({ kind: "revoke", invitation })}
                    >
                      Revoke
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <Dialog
        open={open !== null}
        onOpenChange={(next) => {
          if (!next) setOpen(null);
        }}
        title={open ? titles[open.kind] : ""}
        confirmLabel={
          open?.kind === "revoke" ? "Revoke" : open?.kind === "invite" ? "Send invitation" : "Save"
        }
        destructive={
          open?.kind === "revoke" || (open?.kind === "status" && open.admin.status === "active")
        }
        onConfirm={() => void confirm()}
      >
        {open?.kind === "invite" && (
          <div className="page-stack">
            <Input
              label="Name"
              value={form.name}
              error={fields.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
            <Input
              label="Email"
              type="email"
              value={form.email}
              error={fields.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
            />
            <Select
              label="Role"
              value={form.role}
              error={fields.role}
              onChange={(event) => setForm({ ...form, role: event.target.value as Role })}
              options={roleOptions}
            />
            {reasonField}
          </div>
        )}
        {open?.kind === "role" && (
          <div className="page-stack">
            <Select
              label="Role"
              value={form.role}
              error={fields.role}
              onChange={(event) => setForm({ ...form, role: event.target.value as Role })}
              options={roleOptions}
            />
            {reasonField}
          </div>
        )}
        {open?.kind === "status" && <div className="page-stack">{reasonField}</div>}
        {alertText && open && (
          <p className="ui-error" role="alert">
            {alertText}
          </p>
        )}
      </Dialog>
    </div>
  );
}
