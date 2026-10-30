"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button, ButtonLink, Checkbox, Dialog, Input, Select, TextLink } from "@/components/ui";
import { ACCOUNT_LINKS, FOOTER_LINKS } from "@/components/website/links";
import { postJson, getJson, type ApiError } from "@/lib/api";
import { countryOptions, isCountryCode, OTHER_COUNTRY } from "@/lib/countries";

const TERMS_LINK = FOOTER_LINKS.find((link) => link.label === "Terms")!;
const PRIVACY_LINK = FOOTER_LINKS.find((link) => link.label === "Privacy")!;
const COUNTRIES = countryOptions();

export function SignUpForm() {
  const [country, setCountry] = useState(OTHER_COUNTRY);
  const chosenByVisitor = useRef(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [doneMessage, setDoneMessage] = useState<string | null>(null);

  // Suggest the visitor's country, unless they have already chosen one themselves.
  useEffect(() => {
    getJson<{ country: string }>("/api/auth/company/signup/country/").then((result) => {
      if (result.ok && isCountryCode(result.data.country) && !chosenByVisitor.current) {
        setCountry(result.data.country);
      }
    });
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSending(true);
    setError(null);
    const result = await postJson<{ message: string }>("/api/auth/company/signup/", {
      company_name: form.get("company_name"),
      name: form.get("name"),
      email: form.get("email"),
      password: form.get("password"),
      country,
      accept_terms: form.get("accept_terms") === "on",
    });
    setSending(false);
    if (result.ok) setDoneMessage(result.data.message);
    else setError(result.error);
  }

  const fields = error?.fields ?? {};
  // A mistake that belongs to no field (such as "too many attempts") is shown above the button.
  const generalError = error && Object.keys(fields).length === 0 ? error.message : null;

  return (
    <>
      <form className="page-form" onSubmit={submit} noValidate>
        <Input
          label="Company name"
          name="company_name"
          autoComplete="organization"
          error={fields.company_name}
        />
        <Input label="Your name" name="name" autoComplete="name" error={fields.name} />
        <Input label="Email" name="email" type="email" autoComplete="email" error={fields.email} />
        <Input
          label="Password"
          name="password"
          type="password"
          autoComplete="new-password"
          error={fields.password}
        />
        <Select
          label="Country"
          name="country"
          options={COUNTRIES}
          value={country}
          onChange={(event) => {
            chosenByVisitor.current = true;
            setCountry(event.target.value);
          }}
          error={fields.country}
        />
        <Checkbox
          name="accept_terms"
          label={
            <>
              I accept the <TextLink href={TERMS_LINK.href}>Terms</TextLink> and{" "}
              <TextLink href={PRIVACY_LINK.href}>Privacy Policy</TextLink>
            </>
          }
        />
        {fields.accept_terms && (
          <p className="ui-error" role="alert">
            {fields.accept_terms}
          </p>
        )}
        {generalError && (
          <p className="ui-error" role="alert">
            {generalError}
          </p>
        )}
        <div className="page-actions">
          <Button type="submit" disabled={sending}>
            Create account
          </Button>
        </div>
        <div className="page-links">
          <TextLink href={ACCOUNT_LINKS.logIn.href}>Already have an account? Log in</TextLink>
        </div>
      </form>
      <Dialog
        open={doneMessage !== null}
        onOpenChange={(open) => !open && setDoneMessage(null)}
        title="Check your email"
        description={doneMessage ?? undefined}
        actions={<ButtonLink href={ACCOUNT_LINKS.logIn.href}>Log in</ButtonLink>}
      />
    </>
  );
}
