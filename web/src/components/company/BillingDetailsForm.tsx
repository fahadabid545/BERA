"use client";

import { useEffect, useState } from "react";

import { useCompanyRole } from "@/components/company/role";
import { Button, Dialog, Input, Select } from "@/components/ui";
import { getJson, putJson, type ApiError } from "@/lib/api";
import { COUNTRY_CODES } from "@/lib/countries";

const DETAILS_URL = "/api/company/billing/details/";

type Details = {
  name: string;
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  tax_number: string;
  complete: boolean;
};
type Form = Omit<Details, "complete">;

const EMPTY: Form = {
  name: "",
  address_line1: "",
  address_line2: "",
  city: "",
  state: "",
  postal_code: "",
  country: "",
  tax_number: "",
};

const regionNames = new Intl.DisplayNames(["en"], { type: "region" });
const COUNTRY_OPTIONS = [
  { value: "", label: "Choose a country" },
  ...COUNTRY_CODES.map((code) => ({ value: code, label: regionNames.of(code) ?? code })).sort(
    (first, second) => first.label.localeCompare(second.label),
  ),
];

/** The name, address and tax number invoices are made out to. Only the owner sees this. The
 * billing country is its own choice and never changes the company's sign-up country. */
export function BillingDetailsForm() {
  const isOwner = useCompanyRole() === "owner";
  const [saved, setSaved] = useState<Form | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [error, setError] = useState<ApiError | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!isOwner) return;
    void getJson<Details>(DETAILS_URL).then((result) => {
      if (!result.ok) return setError(result.error);
      const { complete: _complete, ...values } = result.data;
      setSaved(values);
      setForm(values);
    });
  }, [isOwner]);

  if (!isOwner) return null;

  const change = (name: keyof Form) => (event: { target: { value: string } }) =>
    setForm((current) => ({ ...current, [name]: event.target.value }));
  const fieldError = (name: keyof Form) => error?.fields?.[name];
  const unchanged = saved !== null && JSON.stringify(saved) === JSON.stringify(form);

  async function save() {
    const result = await putJson<Details>(DETAILS_URL, form);
    if (!result.ok) return setError(result.error);
    const { complete: _complete, ...values } = result.data;
    setError(null);
    setSaved(values);
    setForm(values);
    setDone(true);
  }

  return (
    <>
      <form className="page-form" onSubmit={(event) => event.preventDefault()}>
        <h2>Billing details</h2>
        <Input
          label="Billing name"
          autoComplete="organization"
          value={form.name}
          error={fieldError("name")}
          onChange={change("name")}
        />
        <Input
          label="Address line 1"
          autoComplete="address-line1"
          value={form.address_line1}
          error={fieldError("address_line1")}
          onChange={change("address_line1")}
        />
        <Input
          label="Address line 2"
          autoComplete="address-line2"
          value={form.address_line2}
          error={fieldError("address_line2")}
          onChange={change("address_line2")}
        />
        <Input
          label="City"
          autoComplete="address-level2"
          value={form.city}
          error={fieldError("city")}
          onChange={change("city")}
        />
        <Input
          label="State or region"
          autoComplete="address-level1"
          value={form.state}
          error={fieldError("state")}
          onChange={change("state")}
        />
        <Input
          label="Postal code"
          autoComplete="postal-code"
          value={form.postal_code}
          error={fieldError("postal_code")}
          onChange={change("postal_code")}
        />
        <Select
          label="Billing country"
          value={form.country}
          error={fieldError("country")}
          options={COUNTRY_OPTIONS}
          onChange={change("country")}
        />
        <Input
          label="Tax number (optional)"
          autoComplete="off"
          value={form.tax_number}
          error={fieldError("tax_number")}
          onChange={change("tax_number")}
        />
        {error && Object.keys(error.fields ?? {}).length === 0 && (
          <p className="ui-error" role="alert">
            {error.message}
          </p>
        )}
        <div className="page-actions">
          <Dialog
            open={confirming}
            onOpenChange={setConfirming}
            trigger={
              <Button type="button" disabled={unchanged}>
                Save
              </Button>
            }
            title="Save billing details"
            description="New invoices use these details. Invoices already issued do not change."
            confirmLabel="Save"
            onConfirm={() => void save()}
          />
        </div>
      </form>
      <Dialog open={done} onOpenChange={setDone} title="Billing details saved" />
    </>
  );
}
