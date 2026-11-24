"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { Button, Checkbox, Dialog, Input, Select, Table } from "@/components/ui";
import { getJson, postJson, putJson, type ApiError, type ApiResult } from "@/lib/api";

type Kind = "number" | "boolean" | "list" | "text";
type Value = number | boolean | string | (string | number)[] | null;
export type Setting = {
  key: string;
  group: string;
  kind: Kind;
  value: Value;
  default: Value;
  is_default: boolean;
};
type Listing = {
  items: Setting[];
  admin_two_step?: { required: boolean; set_up: number; not_set_up: number };
};
type Open = { kind: "change"; setting: Setting } | { kind: "reset"; setting: Setting };

const BASE = "/api/admin/settings/";
const ALL = "";

/** "uploads.max_file_size_mb" as "Max file size mb": the name the setting has in the code, made
 * readable. The owner supplies any final wording. */
export function labelOf(key: string) {
  const name = key.slice(key.indexOf(".") + 1).replaceAll("_", " ");
  return name.charAt(0).toUpperCase() + name.slice(1);
}

function shown(value: Value): string {
  if (value === null) return "Not set";
  if (typeof value === "boolean") return value ? "On" : "Off";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

/** What the person typed, as the value the server expects for this kind of setting. A number that
 * is not one is sent as typed so the server can say so. */
function parsed(setting: Setting, text: string, checked: boolean): Value {
  if (setting.kind === "boolean") return checked;
  if (setting.kind === "number") {
    const number = Number(text);
    return text.trim() === "" || Number.isNaN(number) ? text : number;
  }
  if (setting.kind === "list") {
    const words = text
      .split(",")
      .map((word) => word.trim())
      .filter(Boolean);
    const numeric = Array.isArray(setting.default) && typeof setting.default[0] === "number";
    return numeric
      ? words.map((word) => (Number.isNaN(Number(word)) ? word : Number(word)))
      : words;
  }
  return text;
}

/** A list of platform settings with their defaults, each changeable and resettable to its
 * default. `page` picks one of the curated pages (General, Limits, Rate limiting, Security);
 * without it every editable value is listed, grouped. Changes apply at once and are audited. */
export function AdminSettingsTable({
  page,
  children,
}: {
  page?: string;
  /** Shown above the table once it has loaded, e.g. the admin two-step status. */
  children?: (listing: Listing) => ReactNode;
}) {
  const [listing, setListing] = useState<Listing | null>(null);
  const [group, setGroup] = useState(ALL);
  const [open, setOpen] = useState<Open | null>(null);
  const [text, setText] = useState("");
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    const result = await getJson<Listing>(page ? `${BASE}?page=${page}` : BASE);
    if (result.ok) setListing(result.data);
    else setError(result.error);
  }, [page]);
  useEffect(() => {
    void load();
  }, [load]);

  function show(next: Open) {
    setError(null);
    const { setting } = next;
    setText(Array.isArray(setting.value) ? setting.value.join(", ") : String(setting.value ?? ""));
    setChecked(setting.value === true);
    setOpen(next);
  }

  async function finish(result: ApiResult<unknown>, reopen: Open) {
    if (result.ok) return load();
    setError(result.error);
    // The popup closes when confirmed; a refused value comes back with what was typed.
    setOpen(reopen);
  }

  async function confirm() {
    if (!open) return;
    setError(null);
    const { setting } = open;
    if (open.kind === "reset") {
      await finish(await postJson(`${BASE}${setting.key}/reset/`, {}), open);
    } else {
      const value = parsed(setting, text, checked);
      await finish(await putJson(BASE, { values: { [setting.key]: value } }), open);
    }
  }

  if (!listing) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const groups = Array.from(new Set(listing.items.map((item) => item.group)));
  const rows = listing.items.filter((item) => group === ALL || item.group === group);
  const fieldError = open ? error?.fields?.[open.setting.key] : undefined;
  const generalError = error && !fieldError ? error.message : null;

  return (
    <div className="page-stack">
      {children?.(listing)}
      {generalError && !open && (
        <p className="ui-error" role="alert">
          {generalError}
        </p>
      )}
      {!page && (
        <div className="page-actions">
          <Select
            label="Group"
            value={group}
            onChange={(event) => setGroup(event.target.value)}
            options={[
              { value: ALL, label: "All groups" },
              ...groups.map((each) => ({ value: each, label: labelOf(`x.${each}`) })),
            ]}
          />
        </div>
      )}
      <Table label="Settings">
        <thead>
          <tr>
            {!page && <th scope="col">Group</th>}
            <th scope="col">Setting</th>
            <th scope="col">Value</th>
            <th scope="col">Default</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((setting) => (
            <tr key={setting.key}>
              {!page && <td>{labelOf(`x.${setting.group}`)}</td>}
              <th scope="row">{labelOf(setting.key)}</th>
              <td>{shown(setting.value)}</td>
              <td>{shown(setting.default)}</td>
              <td>
                <div className="page-actions">
                  <Button variant="secondary" onClick={() => show({ kind: "change", setting })}>
                    Change
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={setting.is_default}
                    onClick={() => show({ kind: "reset", setting })}
                  >
                    Reset
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Dialog
        open={open !== null}
        onOpenChange={(next) => {
          if (!next) setOpen(null);
        }}
        title={
          open ? `${open.kind === "reset" ? "Reset" : "Change"}: ${labelOf(open.setting.key)}` : ""
        }
        confirmLabel={open?.kind === "reset" ? "Reset to default" : "Save"}
        onConfirm={() => void confirm()}
      >
        {open?.kind === "change" && open.setting.kind === "boolean" && (
          <Checkbox
            label={labelOf(open.setting.key)}
            checked={checked}
            onChange={(event) => setChecked(event.target.checked)}
          />
        )}
        {open?.kind === "change" && open.setting.kind !== "boolean" && (
          <Input
            label={labelOf(open.setting.key)}
            hint={open.setting.kind === "list" ? "Separate the values with commas." : undefined}
            value={text}
            error={fieldError}
            onChange={(event) => setText(event.target.value)}
          />
        )}
        {open && generalError && (
          <p className="ui-error" role="alert">
            {generalError}
          </p>
        )}
        {open?.kind === "reset" && (
          <p>
            {labelOf(open.setting.key)} goes back to {shown(open.setting.default)}.
          </p>
        )}
      </Dialog>
    </div>
  );
}
