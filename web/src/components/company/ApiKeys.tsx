"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Checkbox, Dialog, Input, Table, Tag } from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";

type Key = {
  id: string;
  name: string;
  last_four: string;
  scopes: string[];
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  request_count: number;
};
type Listing = { keys: Key[]; scopes: string[] };
type Created = Key & { key: string };

const URL = "/api/company/api-keys/";
const DATE_LENGTH = 10;
const END_OF_DAY = "T23:59:59Z";

const day = (value: string | null) => (value ? value.slice(0, DATE_LENGTH) : "Never");

function stateOf(key: Key) {
  if (key.revoked_at) return "Revoked";
  if (key.expires_at && new Date(key.expires_at) <= new Date()) return "Expired";
  return "Active";
}

/** The owner's API keys: made with chosen scopes, shown once, revoked at once. A key's scopes
 * cannot be changed afterwards; make a new key instead. */
export function ApiKeys() {
  const [listing, setListing] = useState<Listing | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [expires, setExpires] = useState("");
  const [revoking, setRevoking] = useState<Key | null>(null);
  const [created, setCreated] = useState<Created | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    const result = await getJson<Listing>(URL);
    if (result.ok) setListing(result.data);
    else setError(result.error);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  function startCreating() {
    setError(null);
    setName("");
    setChosen([]);
    setExpires("");
    setCreating(true);
  }

  async function create() {
    setError(null);
    const result = await postJson<Created>(URL, {
      name,
      scopes: chosen,
      expires_at: expires ? `${expires}${END_OF_DAY}` : null,
    });
    if (result.ok) {
      setCreated(result.data);
      return void (await load());
    }
    // The popup closes when confirmed; a refused form comes back with what was typed.
    setError(result.error);
    setCreating(true);
  }

  async function revoke() {
    if (!revoking) return;
    setError(null);
    const result = await postJson(`${URL}${revoking.id}/revoke/`, {});
    if (result.ok) return void (await load());
    setError(result.error);
  }

  if (!listing) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const fields = error?.fields ?? {};
  const alertText = error && Object.keys(fields).length === 0 ? error.message : null;
  return (
    <div className="page-stack">
      {alertText && (
        <p className="ui-error" role="alert">
          {alertText}
        </p>
      )}
      <div className="page-actions">
        <Button onClick={startCreating}>New key</Button>
      </div>
      {listing.keys.length === 0 ? (
        <p role="status">No API keys.</p>
      ) : (
        <Table label="API keys">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Key ends</th>
              <th scope="col">Scopes</th>
              <th scope="col">Created</th>
              <th scope="col">Expires</th>
              <th scope="col">Last used</th>
              <th scope="col">Requests</th>
              <th scope="col">Status</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {listing.keys.map((key) => {
              const state = stateOf(key);
              return (
                <tr key={key.id}>
                  <th scope="row">{key.name}</th>
                  <td>{key.last_four}</td>
                  <td>{key.scopes.join(", ")}</td>
                  <td>{day(key.created_at)}</td>
                  <td>{day(key.expires_at)}</td>
                  <td>{day(key.last_used_at)}</td>
                  <td>{key.request_count}</td>
                  <td>
                    <Tag variant={state === "Active" ? "success" : "neutral"}>{state}</Tag>
                  </td>
                  <td>
                    {!key.revoked_at && (
                      <Button variant="secondary" onClick={() => setRevoking(key)}>
                        Revoke
                      </Button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      )}
      <Dialog
        open={creating}
        onOpenChange={setCreating}
        title="New key"
        confirmLabel="Create"
        onConfirm={() => void create()}
      >
        <div className="page-stack">
          <Input
            label="Name"
            value={name}
            error={fields.name}
            onChange={(event) => setName(event.target.value)}
          />
          {listing.scopes.map((scope) => (
            <Checkbox
              key={scope}
              label={scope}
              checked={chosen.includes(scope)}
              onChange={(event) =>
                setChosen(
                  event.target.checked
                    ? [...chosen, scope]
                    : chosen.filter((each) => each !== scope),
                )
              }
            />
          ))}
          {fields.scopes && (
            <p className="ui-error" role="alert">
              {fields.scopes}
            </p>
          )}
          <Input
            label="Expires on"
            type="date"
            value={expires}
            error={fields.expires_at}
            onChange={(event) => setExpires(event.target.value)}
          />
        </div>
      </Dialog>
      <Dialog
        open={created !== null}
        onOpenChange={(next) => {
          if (!next) setCreated(null);
        }}
        title="Your new key"
      >
        <Input label="Key" value={created?.key ?? ""} readOnly onFocus={(e) => e.target.select()} />
      </Dialog>
      <Dialog
        open={revoking !== null}
        onOpenChange={(next) => {
          if (!next) setRevoking(null);
        }}
        title={`Revoke ${revoking?.name ?? "key"}`}
        confirmLabel="Revoke"
        destructive
        onConfirm={() => void revoke()}
      />
    </div>
  );
}
