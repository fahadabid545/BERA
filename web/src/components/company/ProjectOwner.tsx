"use client";

import { useEffect, useState } from "react";

import { Button, Dialog, Select } from "@/components/ui";
import { getJson, putJson, type ApiError } from "@/lib/api";

type Member = { id: number; name: string; status: string };

/** Hands the project to another active team member. Only the company's owner is offered it. */
export function ProjectOwner({
  projectId,
  ownerId,
  onChanged,
}: {
  projectId: string;
  ownerId: number;
  onChanged: () => void;
}) {
  const [members, setMembers] = useState<Member[]>([]);
  const [chosen, setChosen] = useState("");
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    void getJson<Member[]>("/api/company/team/members/").then((result) => {
      if (result.ok) setMembers(result.data.filter((member) => member.status === "active"));
      else setError(result.error);
    });
  }, []);

  async function change() {
    setError(null);
    const result = await putJson(`/api/company/projects/${projectId}/owner/`, {
      owner_id: Number(chosen),
    });
    if (result.ok) {
      setChosen("");
      onChanged();
    } else setError(result.error);
  }

  const options = members.filter((member) => member.id !== ownerId);
  const current = members.find((member) => member.id === ownerId);
  const newOwner = options.find((member) => String(member.id) === chosen);
  return (
    <div className="page-form">
      <Select
        label="Project owner"
        value={chosen}
        onChange={(event) => setChosen(event.target.value)}
        options={[
          { value: "", label: current?.name ?? "Current owner" },
          ...options.map((member) => ({ value: String(member.id), label: member.name })),
        ]}
      />
      {error && (
        <p className="ui-error" role="alert">
          {error.fields?.owner_id ?? error.message}
        </p>
      )}
      <div className="page-actions">
        <Dialog
          trigger={
            <Button variant="secondary" disabled={!newOwner}>
              Change owner
            </Button>
          }
          title="Change owner"
          description={newOwner ? `Hand this project to ${newOwner.name}?` : undefined}
          confirmLabel="Change owner"
          onConfirm={() => void change()}
        />
      </div>
    </div>
  );
}
