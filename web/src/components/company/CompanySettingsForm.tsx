"use client";

import { useState } from "react";

import { Button, Dialog, Input } from "@/components/ui";
import { OTHER_COUNTRY } from "@/lib/countries";

import { useCompanySettings } from "./companySettings";

const countryName = (code: string) =>
  code === OTHER_COUNTRY
    ? "Other"
    : (new Intl.DisplayNames(["en"], { type: "region" }).of(code) ?? code);

/** The owner changes the company's name. The billing country is shown and locked. */
export function CompanySettingsForm() {
  const { settings, error, saved, setSaved, save } = useCompanySettings();
  const [name, setName] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  if (!settings) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const shown = name ?? settings.name;
  const fieldError = error?.fields?.name;
  return (
    <>
      <form className="page-form" onSubmit={(event) => event.preventDefault()}>
        <Input
          label="Company name"
          autoComplete="organization"
          value={shown}
          error={fieldError}
          onChange={(event) => setName(event.target.value)}
        />
        <Input label="Billing country" value={countryName(settings.country)} disabled readOnly />
        {error && !fieldError && (
          <p className="ui-error" role="alert">
            {error.message}
          </p>
        )}
        <div className="page-actions">
          <Dialog
            open={confirming}
            onOpenChange={setConfirming}
            trigger={
              <Button type="button" disabled={shown.trim() === settings.name}>
                Save
              </Button>
            }
            title="Save company"
            description="The company name changes for everyone in your company."
            confirmLabel="Save"
            onConfirm={() => void save({ name: shown }).then(() => setName(null))}
          />
        </div>
      </form>
      <Dialog open={saved} onOpenChange={setSaved} title="Company saved" />
    </>
  );
}
