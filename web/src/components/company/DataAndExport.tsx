"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Button, Checkbox, Dialog, Input } from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";

import { useCompanySettings } from "./companySettings";
import { requestCompanyExport } from "./downloads";

type Overview = { subscription: { active: boolean; state: string; period_end: string | null } };
type Scheduled = { due_at: string };

const DELETION = "/api/company/deletion/";
const LOGIN_HREF = "/login";
const DATE_LENGTH = 10;

/** Exporting the company's data and deleting the company. Deleting asks for the company name,
 * offers the export first, warns about an active subscription, and only starts a grace period
 * in which it can still be undone from the email. */
export function DataAndExport() {
  const router = useRouter();
  const { settings } = useCompanySettings();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [scheduled, setScheduled] = useState<Scheduled | null>(null);

  useEffect(() => {
    void getJson<Overview>(DELETION).then((result) => {
      if (result.ok) setOverview(result.data);
      else setError(result.error);
    });
  }, []);

  async function exportData() {
    setError(null);
    const result = await requestCompanyExport();
    if (result.ok) router.push(`/company/downloads/${result.data.id}`);
    else setError(result.error);
  }

  async function remove(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const typed = String(new FormData(event.currentTarget).get("confirm_name") ?? "");
    setError(null);
    const result = await postJson<Scheduled>(DELETION, {
      confirm_name: typed,
      acknowledge_subscription: acknowledged,
    });
    if (!result.ok) return setError(result.error);
    setDeleting(false);
    setScheduled(result.data);
  }

  const subscriptionActive = overview?.subscription.active ?? false;
  const fields = error?.fields ?? {};
  const generalError = error && Object.keys(fields).length === 0 ? error.message : null;
  return (
    <>
      <div className="page-actions">
        <Button variant="secondary" onClick={() => void exportData()}>
          Export data
        </Button>
        <Button variant="danger" onClick={() => setDeleting(true)}>
          Delete company
        </Button>
      </div>
      {generalError && !deleting && (
        <p className="ui-error" role="alert">
          {generalError}
        </p>
      )}
      <Dialog open={deleting} onOpenChange={setDeleting} title="Delete company">
        <form className="page-form" onSubmit={remove} noValidate>
          <div className="page-actions">
            <Button type="button" variant="secondary" onClick={() => void exportData()}>
              Export data first
            </Button>
          </div>
          {subscriptionActive && (
            <Checkbox
              label="My active subscription ends with the company"
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
            />
          )}
          <Input
            label={`Type "${settings?.name ?? ""}" to confirm`}
            name="confirm_name"
            autoComplete="off"
            error={fields.confirm_name}
          />
          {generalError && (
            <p className="ui-error" role="alert">
              {generalError}
            </p>
          )}
          <div className="page-actions">
            <Button type="submit" variant="danger">
              Delete company
            </Button>
          </div>
        </form>
      </Dialog>
      <Dialog
        open={scheduled !== null}
        onOpenChange={(open) => !open && router.push(LOGIN_HREF)}
        title="Company scheduled for deletion"
        description={
          scheduled
            ? `Everything is removed on ${scheduled.due_at.slice(0, DATE_LENGTH)}. Use the link in the email we sent you to undo it before then.`
            : undefined
        }
      />
    </>
  );
}
