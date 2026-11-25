"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Button, Dialog, Input, Textarea, TextLink } from "@/components/ui";
import { FOOTER_LINKS } from "@/components/website/links";
import { getJson, postJson, type ApiError } from "@/lib/api";

const FORM_URL = "/api/contact/form/";
const SEND_URL = "/api/contact/";
const PRIVACY_LINK = FOOTER_LINKS.find((link) => link.href === "/privacy");
const SECONDS = 1000;

type FormInfo = { privacy_note: string; form_token: string; refresh_after_seconds: number };

/** The public contact form. The server hands out the privacy notice and a signed "form opened"
 * token (one of its spam checks); a hidden field that people never fill is the other. */
export function ContactForm() {
  const [info, setInfo] = useState<FormInfo | null>(null);
  const [loadProblem, setLoadProblem] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [thankYou, setThankYou] = useState<string | null>(null);

  const loadForm = useCallback(async () => {
    const result = await getJson<FormInfo>(FORM_URL);
    if (result.ok) {
      setInfo(result.data);
      setLoadProblem(null);
    } else {
      setLoadProblem(result.error.message);
    }
  }, []);

  useEffect(() => {
    void loadForm();
  }, [loadForm]);

  // A form left open gets a fresh token before the old one expires.
  useEffect(() => {
    if (!info) return;
    const timer = setTimeout(() => void loadForm(), info.refresh_after_seconds * SECONDS);
    return () => clearTimeout(timer);
  }, [info, loadForm]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!info || sending) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    setSending(true);
    setError(null);
    const result = await postJson<{ message: string }>(SEND_URL, {
      name: values.get("name"),
      email: values.get("email"),
      message: values.get("message"),
      website: values.get("website"),
      form_token: info.form_token,
    });
    setSending(false);
    if (!result.ok) return setError(result.error);
    form.reset();
    setThankYou(result.data.message);
    void loadForm();
  }

  return (
    <>
      <form className="page-form" onSubmit={submit} noValidate>
        <Input label="Name" name="name" autoComplete="name" error={error?.fields?.name} />
        <Input
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          error={error?.fields?.email}
        />
        <Textarea label="Message" name="message" error={error?.fields?.message} />
        <div className="contact-trap" aria-hidden="true">
          <input name="website" type="text" tabIndex={-1} autoComplete="off" defaultValue="" />
        </div>
        {(loadProblem || (error && !Object.keys(error.fields ?? {}).length)) && (
          <p className="ui-error" role="alert">
            {loadProblem ?? error?.message}
          </p>
        )}
        {info && (
          <p>
            {info.privacy_note}
            {PRIVACY_LINK && (
              <>
                {" "}
                See our <TextLink href={PRIVACY_LINK.href}>Privacy page</TextLink>.
              </>
            )}
          </p>
        )}
        <div className="page-actions">
          <Button type="submit" disabled={sending || !info}>
            Send
          </Button>
        </div>
      </form>
      <Dialog
        open={thankYou !== null}
        onOpenChange={(open) => !open && setThankYou(null)}
        title="Thank you"
        description={thankYou ?? undefined}
      />
    </>
  );
}
