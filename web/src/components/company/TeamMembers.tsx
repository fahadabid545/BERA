"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Button, Dialog, Input, Table } from "@/components/ui";
import { deleteJson, getJson, postJson, type ApiError } from "@/lib/api";

const BASE = "/api/company/team/";

type Member = {
  id: number;
  name: string;
  email: string;
  role: "owner" | "member";
  status: "active" | "blocked";
};

const words = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** The people in the company. The owner can remove a member or hand the company to one. */
export function TeamMembers() {
  const router = useRouter();
  const [members, setMembers] = useState<Member[]>([]);
  const [handingTo, setHandingTo] = useState<Member | null>(null);
  const [sending, setSending] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);
  const [listError, setListError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    const result = await getJson<Member[]>(`${BASE}members/`);
    if (result.ok) setMembers(result.data);
    else setListError(result.error);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function remove(member: Member) {
    setListError(null);
    const result = await deleteJson(`${BASE}members/${member.id}/`);
    if (result.ok) await load();
    else setListError(result.error);
  }

  async function handOver(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!handingTo) return;
    const password = String(new FormData(event.currentTarget).get("password") ?? "");
    setSending(true);
    setFormError(null);
    const result = await postJson(`${BASE}transfer-ownership/`, {
      member_id: handingTo.id,
      password,
    });
    setSending(false);
    if (!result.ok) return setFormError(result.error);
    setHandingTo(null);
    // The role changed for this person too, so the menu and the pages are read again.
    router.refresh();
    await load();
  }

  const fields = formError?.fields ?? {};
  const generalError = formError && Object.keys(fields).length === 0 ? formError.message : null;
  return (
    <div className="page-stack">
      {listError && (
        <p className="ui-error" role="alert">
          {listError.message}
        </p>
      )}
      <Table label="Members">
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
          {members.map((member) => (
            <tr key={member.id}>
              <td>{member.name}</td>
              <td>{member.email}</td>
              <td>{words(member.role)}</td>
              <td>{words(member.status)}</td>
              <td>
                {member.role !== "owner" && (
                  <div className="page-actions">
                    {member.status === "active" && (
                      <Button
                        variant="secondary"
                        aria-label={`Make ${member.name} the owner`}
                        onClick={() => {
                          setFormError(null);
                          setHandingTo(member);
                        }}
                      >
                        Make owner
                      </Button>
                    )}
                    <Dialog
                      trigger={
                        <Button variant="secondary" aria-label={`Remove ${member.name}`}>
                          Remove
                        </Button>
                      }
                      title="Remove member"
                      description={`${member.name} will be removed and signed out. Their work stays with the company.`}
                      confirmLabel="Remove"
                      onConfirm={() => remove(member)}
                      destructive
                    />
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Dialog
        open={handingTo !== null}
        onOpenChange={(open) => !open && setHandingTo(null)}
        title="Make owner"
        description={
          handingTo ? `${handingTo.name} becomes the owner and you become a member.` : undefined
        }
      >
        <form className="page-form" onSubmit={handOver} noValidate>
          <Input
            label="Your password"
            name="password"
            type="password"
            autoComplete="current-password"
            error={fields.password}
          />
          {generalError && (
            <p className="ui-error" role="alert">
              {generalError}
            </p>
          )}
          <div className="page-actions">
            <Button type="submit" disabled={sending}>
              Make owner
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
