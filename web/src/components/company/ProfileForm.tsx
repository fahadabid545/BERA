"use client";

import { useEffect, useState } from "react";

import { Button, Dialog, Input } from "@/components/ui";
import { getJson, patchJson, type ApiError } from "@/lib/api";

type Profile = { name: string; email: string; role: string; company_name: string };

/** The person's own name, and the email they sign in with (shown here; changed in its own form
 * because the new address has to be confirmed). */
export function ProfileForm() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    void getJson<Profile>("/api/company/profile/").then((result) => {
      if (result.ok) {
        setProfile(result.data);
        setName(result.data.name);
      } else setError(result.error);
    });
  }, []);

  async function save() {
    const result = await patchJson<Profile>("/api/company/profile/", { name });
    if (result.ok) {
      setError(null);
      setProfile(result.data);
      setName(result.data.name);
      setSaved(true);
    } else setError(result.error);
  }

  const fieldError = error?.fields?.name;
  const generalError = error && !fieldError ? error.message : null;
  return (
    <>
      <form className="page-form" onSubmit={(event) => event.preventDefault()}>
        <Input
          label="Name"
          autoComplete="name"
          value={name}
          error={fieldError}
          onChange={(event) => setName(event.target.value)}
        />
        <Input label="Email" type="email" readOnly value={profile?.email ?? ""} />
        {generalError && (
          <p className="ui-error" role="alert">
            {generalError}
          </p>
        )}
        <div className="page-actions">
          <Dialog
            open={confirming}
            onOpenChange={setConfirming}
            trigger={
              <Button type="button" disabled={!profile || name.trim() === profile.name}>
                Save
              </Button>
            }
            title="Save profile"
            description="Your name changes for everyone in your company."
            confirmLabel="Save"
            onConfirm={() => void save()}
          />
        </div>
      </form>
      <Dialog open={saved} onOpenChange={setSaved} title="Profile saved" />
    </>
  );
}
