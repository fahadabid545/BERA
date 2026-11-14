"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Dialog, Input, Select, Table, Tabs, Tag, Textarea } from "@/components/ui";
import { deleteJson, getJson, postJson, putJson, type ApiError, type ApiResult } from "@/lib/api";

type Kind = "reading" | "scoring";
type Version = {
  kind: Kind;
  number: number;
  created_at: string;
  text: string;
  current: boolean;
  projects: number;
};
type Overview = Record<Kind, Version[]>;
type Row = { left: string; right: string; changed: boolean };
type Open =
  | { kind: "create" }
  | { kind: "current"; version: Version }
  | { kind: "delete"; version: Version }
  | { kind: "move" };

const KINDS: { value: Kind; label: string }[] = [
  { value: "reading", label: "Reading" },
  { value: "scoring", label: "Scoring" },
];
const BASE = "/api/admin/ai/prompts/";

/** The numbered instructions given to the AI, for reading CVs and for scoring. A new version
 * changes no project; an admin makes a version current for new projects, moves a project to
 * another version, or deletes a version nothing uses. */
export function AiPrompts() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [kind, setKind] = useState<Kind>("reading");
  const [open, setOpen] = useState<Open | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [reason, setReason] = useState("");
  const [text, setText] = useState("");
  const [projectId, setProjectId] = useState("");
  const [moveTo, setMoveTo] = useState("");
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const [rows, setRows] = useState<Row[] | null>(null);

  const load = useCallback(async () => {
    const result = await getJson<Overview>(BASE);
    if (!result.ok) return setError(result.error);
    setOverview(result.data);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const versions = overview?.[kind] ?? [];
  useEffect(() => {
    const numbers = versions.map((version) => String(version.number));
    setLeft((value) => (numbers.includes(value) ? value : (numbers[0] ?? "")));
    setRight((value) => (numbers.includes(value) ? value : (numbers[numbers.length - 1] ?? "")));
    setRows(null);
  }, [overview, kind]); // eslint-disable-line react-hooks/exhaustive-deps

  function show(next: Open) {
    setError(null);
    setReason("");
    if (next.kind === "create") {
      setText(versions.find((version) => version.current)?.text ?? "");
    }
    if (next.kind === "move") {
      setProjectId("");
      setMoveTo(String(versions.find((version) => version.current)?.number ?? ""));
    }
    setOpen(next);
  }

  async function finish(result: ApiResult<unknown>) {
    if (!result.ok) return setError(result.error);
    await load();
  }

  async function confirm() {
    if (!open) return;
    if (open.kind === "create") {
      await finish(await postJson(BASE, { kind, text }));
    } else if (open.kind === "current") {
      await finish(await putJson(`${BASE}current/`, { kind, number: open.version.number, reason }));
    } else if (open.kind === "delete") {
      await finish(await deleteJson(`${BASE}${kind}/${open.version.number}/`, { reason }));
    } else {
      await finish(
        await postJson(`${BASE}move-project/`, {
          project_id: projectId.trim(),
          kind,
          number: Number(moveTo),
          reason,
        }),
      );
    }
    setOpen(null);
  }

  async function compare() {
    setError(null);
    const result = await getJson<{ rows: Row[] }>(
      `${BASE}compare/?kind=${kind}&left=${left}&right=${right}`,
    );
    if (!result.ok) return setError(result.error);
    setRows(result.data.rows);
  }

  if (!overview) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const fields = error?.fields ?? {};
  const options = versions.map((version) => ({
    value: String(version.number),
    label: `Version ${version.number}`,
  }));
  const titles = {
    create: "New version",
    current: "Make version current",
    delete: "Delete version",
    move: "Move project",
  };
  const labels = {
    create: "Create version",
    current: "Make current",
    delete: "Delete version",
    move: "Move project",
  };

  const panel = (
    <div className="page-stack">
      <div className="page-actions">
        <Button onClick={() => show({ kind: "create" })}>New version</Button>
        <Button variant="secondary" onClick={() => show({ kind: "move" })}>
          Move project
        </Button>
      </div>
      {error && !open && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      <Table label={`${kind === "reading" ? "Reading" : "Scoring"} versions`}>
        <thead>
          <tr>
            <th>Version</th>
            <th>Created</th>
            <th>Projects using it</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {versions.map((version) => (
            <tr key={version.number}>
              <td>{version.number}</td>
              <td>{version.created_at.slice(0, 10)}</td>
              <td>{version.projects}</td>
              <td>{version.current ? <Tag variant="success">Current</Tag> : null}</td>
              <td>
                <Button
                  variant="secondary"
                  aria-label={`Make version ${version.number} current`}
                  disabled={version.current}
                  onClick={() => show({ kind: "current", version })}
                >
                  Make current
                </Button>{" "}
                <Button
                  variant="secondary"
                  aria-label={`Delete version ${version.number}`}
                  disabled={version.current || version.projects > 0}
                  onClick={() => show({ kind: "delete", version })}
                >
                  Delete
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      <div className="page-form">
        <Select
          label="Compare"
          options={options}
          value={left}
          onChange={(event) => setLeft(event.target.value)}
        />
        <Select
          label="With"
          options={options}
          value={right}
          onChange={(event) => setRight(event.target.value)}
        />
        <div className="page-actions">
          <Button variant="secondary" onClick={() => void compare()}>
            Compare versions
          </Button>
        </div>
      </div>
      {rows && (
        <Table label="Comparison">
          <thead>
            <tr>
              <th>Version {left}</th>
              <th>Version {right}</th>
              <th>Difference</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, position) => (
              <tr key={position}>
                <td>{row.left}</td>
                <td>{row.right}</td>
                <td>{row.changed ? "Changed" : ""}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );

  return (
    <>
      <Tabs
        label="Prompt kind"
        value={kind}
        onValueChange={(value) => setKind(value as Kind)}
        tabs={KINDS.map((item) => ({
          value: item.value,
          label: item.label,
          content: item.value === kind ? panel : null,
        }))}
      />
      <Dialog
        open={open !== null}
        onOpenChange={(next) => !next && setOpen(null)}
        title={open ? titles[open.kind] : ""}
        confirmLabel={open ? labels[open.kind] : undefined}
        onConfirm={() => void confirm()}
        destructive={open?.kind === "delete"}
      >
        {open?.kind === "create" && (
          <Textarea
            label="Instructions"
            value={text}
            onChange={(event) => setText(event.target.value)}
            error={fields.text}
          />
        )}
        {open?.kind === "move" && (
          <>
            <Input
              label="Project ID"
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
              error={fields.project_id}
            />
            <Select
              label="Version"
              options={options}
              value={moveTo}
              onChange={(event) => setMoveTo(event.target.value)}
            />
          </>
        )}
        {open && open.kind !== "create" && (
          <Input
            label="Reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            error={fields.reason}
          />
        )}
        {error && open && (
          <p className="ui-error" role="alert">
            {error.message}
          </p>
        )}
      </Dialog>
    </>
  );
}
