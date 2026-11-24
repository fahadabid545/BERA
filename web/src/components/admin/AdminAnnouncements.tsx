"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Checkbox, Dialog, Input, Select, Table, Tag, Textarea } from "@/components/ui";
import type { TagVariant } from "@/components/ui";
import { deleteJson, getJson, postJson, putJson, type ApiError, type ApiResult } from "@/lib/api";

import { useAdminRole } from "./role";

type Target = "everyone" | "plan" | "companies";
type Status = "scheduled" | "live" | "expired";
type Item = {
  id: number;
  message: string;
  starts_at: string;
  ends_at: string;
  target: Target;
  plan_id: number | null;
  plan: string | null;
  company_ids: number[];
  status: Status;
};
type Named = { id: number; name: string };
type Listing = { items: Item[]; plans: Named[]; companies: Named[] };
type Form = {
  message: string;
  starts: string;
  ends: string;
  target: Target;
  plan: string;
  companies: number[];
};
type Open = { kind: "form"; id: number | null } | { kind: "delete"; item: Item };

const BASE = "/api/admin/announcements/";
const TARGET_WORDS: Record<Target, string> = {
  everyone: "Everyone",
  plan: "A plan",
  companies: "Chosen companies",
};
const STATUS_WORDS: Record<Status, string> = {
  scheduled: "Scheduled",
  live: "Live",
  expired: "Expired",
};
const STATUS_TAGS: Record<Status, TagVariant> = {
  scheduled: "neutral",
  live: "live",
  expired: "warning",
};
const EMPTY_FORM: Form = {
  message: "",
  starts: "",
  ends: "",
  target: "everyone",
  plan: "",
  companies: [],
};
const TWO_DIGITS = 2;

/** A date and time as the page's date field wants it: the person's own time, to the minute. */
function toFieldValue(iso: string) {
  const date = new Date(iso);
  const part = (value: number) => String(value).padStart(TWO_DIGITS, "0");
  return `${date.getFullYear()}-${part(date.getMonth() + 1)}-${part(date.getDate())}T${part(date.getHours())}:${part(date.getMinutes())}`;
}
const toIso = (fieldValue: string) => (fieldValue ? new Date(fieldValue).toISOString() : "");
const shown = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

/** The banners shown in the company panel. Support may look; only a super admin may write, and
 * the server refuses support whatever the page shows. */
export function AdminAnnouncements() {
  const mayWrite = useAdminRole() === "super";
  const [listing, setListing] = useState<Listing | null>(null);
  const [open, setOpen] = useState<Open | null>(null);
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    const result = await getJson<Listing>(BASE);
    if (result.ok) setListing(result.data);
    else setError(result.error);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  function openForm(item: Item | null) {
    setError(null);
    setForm(
      item
        ? {
            message: item.message,
            starts: toFieldValue(item.starts_at),
            ends: toFieldValue(item.ends_at),
            target: item.target,
            plan: item.plan_id === null ? "" : String(item.plan_id),
            companies: item.company_ids,
          }
        : EMPTY_FORM,
    );
    setOpen({ kind: "form", id: item?.id ?? null });
  }

  function body() {
    return {
      message: form.message,
      starts_at: toIso(form.starts),
      ends_at: toIso(form.ends),
      target: form.target,
      ...(form.target === "plan" ? { plan: Number(form.plan) } : {}),
      ...(form.target === "companies" ? { companies: form.companies } : {}),
    };
  }

  async function finish(result: ApiResult<Listing>, reopen: Open) {
    if (result.ok) {
      setListing(result.data);
      return;
    }
    setError(result.error);
    // The popup closes when it is confirmed; a refused form comes back with what was typed.
    if (reopen.kind === "form") setOpen(reopen);
  }

  async function save() {
    if (open?.kind !== "form") return;
    setError(null);
    const result =
      open.id === null
        ? await postJson<Listing>(BASE, body())
        : await putJson<Listing>(`${BASE}${open.id}/`, body());
    await finish(result, open);
  }

  async function remove(item: Item) {
    setError(null);
    await finish(await deleteJson<Listing>(`${BASE}${item.id}/`), { kind: "delete", item });
  }

  if (!listing) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const fields = error?.fields ?? {};
  const names = new Map(listing.companies.map((company) => [company.id, company.name]));
  const targetText = (item: Item) =>
    item.target === "plan"
      ? `Plan: ${item.plan ?? ""}`
      : item.target === "companies"
        ? `Companies: ${item.company_ids.map((id) => names.get(id) ?? "").join(", ")}`
        : TARGET_WORDS.everyone;

  return (
    <div className="page-stack">
      {error && !open && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      {mayWrite && (
        <div className="page-actions">
          <Button onClick={() => openForm(null)}>New announcement</Button>
        </div>
      )}
      {listing.items.length === 0 ? (
        <p role="status">No announcements.</p>
      ) : (
        <Table label="Announcements">
          <thead>
            <tr>
              <th scope="col">Message</th>
              <th scope="col">Shown to</th>
              <th scope="col">Starts</th>
              <th scope="col">Ends</th>
              <th scope="col">Status</th>
              {mayWrite && <th scope="col">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {listing.items.map((item) => (
              <tr key={item.id}>
                <th scope="row">{item.message}</th>
                <td>{targetText(item)}</td>
                <td>{shown(item.starts_at)}</td>
                <td>{shown(item.ends_at)}</td>
                <td>
                  <Tag variant={STATUS_TAGS[item.status]}>{STATUS_WORDS[item.status]}</Tag>
                </td>
                {mayWrite && (
                  <td>
                    <div className="page-actions">
                      <Button variant="secondary" onClick={() => openForm(item)}>
                        Edit
                      </Button>
                      <Button variant="secondary" onClick={() => setOpen({ kind: "delete", item })}>
                        Delete
                      </Button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <Dialog
        open={open?.kind === "form"}
        onOpenChange={(next) => {
          if (!next) setOpen(null);
        }}
        title={open?.kind === "form" && open.id !== null ? "Edit announcement" : "New announcement"}
        confirmLabel="Save"
        onConfirm={() => void save()}
      >
        <div className="page-stack">
          {error && !fields.message && Object.keys(fields).length === 0 && (
            <p className="ui-error" role="alert">
              {error.message}
            </p>
          )}
          <Textarea
            label="Message"
            value={form.message}
            error={fields.message}
            onChange={(event) => setForm({ ...form, message: event.target.value })}
          />
          <Input
            label="Starts"
            type="datetime-local"
            value={form.starts}
            error={fields.starts_at}
            onChange={(event) => setForm({ ...form, starts: event.target.value })}
          />
          <Input
            label="Ends"
            type="datetime-local"
            value={form.ends}
            error={fields.ends_at}
            onChange={(event) => setForm({ ...form, ends: event.target.value })}
          />
          <Select
            label="Shown to"
            value={form.target}
            error={fields.target}
            onChange={(event) => setForm({ ...form, target: event.target.value as Target })}
            options={(Object.keys(TARGET_WORDS) as Target[]).map((value) => ({
              value,
              label: TARGET_WORDS[value],
            }))}
          />
          {form.target === "plan" && (
            <Select
              label="Plan"
              value={form.plan}
              error={fields.plan}
              onChange={(event) => setForm({ ...form, plan: event.target.value })}
              options={[
                { value: "", label: "Choose a plan" },
                ...listing.plans.map((plan) => ({ value: String(plan.id), label: plan.name })),
              ]}
            />
          )}
          {form.target === "companies" && (
            <fieldset>
              <legend className="ui-label">Companies</legend>
              {listing.companies.map((company) => (
                <Checkbox
                  key={company.id}
                  label={company.name}
                  checked={form.companies.includes(company.id)}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      companies: event.target.checked
                        ? [...form.companies, company.id]
                        : form.companies.filter((id) => id !== company.id),
                    })
                  }
                />
              ))}
              {fields.companies && <p className="ui-error">{fields.companies}</p>}
            </fieldset>
          )}
        </div>
      </Dialog>
      <Dialog
        open={open?.kind === "delete"}
        onOpenChange={(next) => {
          if (!next) setOpen(null);
        }}
        title="Delete this announcement?"
        confirmLabel="Delete"
        destructive
        onConfirm={() => open?.kind === "delete" && void remove(open.item)}
      />
    </div>
  );
}
