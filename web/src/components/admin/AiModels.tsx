"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Dialog, Input, Select, Table, Tag } from "@/components/ui";
import { getJson, patchJson, postJson, putJson, type ApiError, type ApiResult } from "@/lib/api";

type Roles = "reading" | "scoring";
type Model = {
  id: number;
  name: string;
  input_price_per_million: string;
  output_price_per_million: string;
  enabled: boolean;
  chosen_for: Roles[];
  projects: Record<Roles, number>;
};
type Overview = { models: Model[]; choice: Record<Roles, string> };
type Replacement = { id: number; name: string };
type Open =
  | { kind: "add" }
  | { kind: "prices"; model: Model }
  | { kind: "choose" }
  | { kind: "switch"; model: Model }
  | { kind: "replace"; model: Model; replacements: Replacement[] };

const ROLE_LABEL: Record<Roles, string> = { reading: "reading", scoring: "scoring" };

/** The models list: add a model, price it, switch it on or off, and choose the reading and
 * scoring model that new projects start with. Existing projects keep the model they were
 * created with, except when a model in use is switched off and replaced. */
export function AiModels() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [open, setOpen] = useState<Open | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [reason, setReason] = useState("");
  const [name, setName] = useState("");
  const [inputPrice, setInputPrice] = useState("");
  const [outputPrice, setOutputPrice] = useState("");
  const [readingId, setReadingId] = useState("");
  const [scoringId, setScoringId] = useState("");
  const [replacementId, setReplacementId] = useState("");

  const load = useCallback(async () => {
    const result = await getJson<Overview>("/api/admin/ai/models/");
    if (!result.ok) return setError(result.error);
    setOverview(result.data);
    const byName = (wanted: string) =>
      String(result.data.models.find((model) => model.name === wanted)?.id ?? "");
    setReadingId(byName(result.data.choice.reading));
    setScoringId(byName(result.data.choice.scoring));
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  function show(next: Open) {
    setError(null);
    setReason("");
    if (next.kind === "add") {
      setName("");
      setInputPrice("");
      setOutputPrice("");
    }
    if (next.kind === "prices") {
      setInputPrice(next.model.input_price_per_million);
      setOutputPrice(next.model.output_price_per_million);
    }
    if (next.kind === "replace") setReplacementId(String(next.replacements[0]?.id ?? ""));
    setOpen(next);
  }

  async function finish(result: ApiResult<unknown>) {
    if (!result.ok) {
      setError(result.error);
      return false;
    }
    await load();
    return true;
  }

  async function confirm() {
    if (!open) return;
    const base = "/api/admin/ai/models/";
    if (open.kind === "add") {
      await finish(
        await postJson(base, {
          name,
          input_price_per_million: inputPrice,
          output_price_per_million: outputPrice,
        }),
      );
    } else if (open.kind === "prices") {
      await finish(
        await patchJson(`${base}${open.model.id}/`, {
          reason,
          input_price_per_million: inputPrice,
          output_price_per_million: outputPrice,
        }),
      );
    } else if (open.kind === "choose") {
      await finish(
        await putJson(`${base}selection/`, {
          reason,
          reading_model: Number(readingId),
          scoring_model: Number(scoringId),
        }),
      );
    } else if (open.kind === "switch") {
      const result = await patchJson<Model>(`${base}${open.model.id}/`, {
        reason,
        enabled: !open.model.enabled,
      });
      if (!result.ok && result.error.code === "model_in_use") {
        const replacements = (result.error.details?.replacements ?? []) as Replacement[];
        return show({ kind: "replace", model: open.model, replacements });
      }
      await finish(result);
    } else if (open.kind === "replace") {
      await finish(
        await patchJson(`${base}${open.model.id}/`, {
          reason,
          enabled: false,
          replacement: Number(replacementId),
        }),
      );
    }
    setOpen(null);
  }

  if (!overview) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const fields = error?.fields ?? {};
  const switchedOn = overview.models
    .filter((model) => model.enabled)
    .map((model) => ({ value: String(model.id), label: model.name }));
  const titles: Record<Open["kind"], string> = {
    add: "Add model",
    prices: "Edit prices",
    choose: "Save model choice",
    switch: "Switch model",
    replace: "This model is in use",
  };
  const labels: Record<Open["kind"], string> = {
    add: "Add model",
    prices: "Save prices",
    choose: "Save choice",
    switch: "Continue",
    replace: "Switch off and replace",
  };

  return (
    <div className="page-stack">
      <div className="page-form">
        <Select
          label="Reading model"
          options={switchedOn}
          value={readingId}
          onChange={(event) => setReadingId(event.target.value)}
        />
        <Select
          label="Scoring model"
          options={switchedOn}
          value={scoringId}
          onChange={(event) => setScoringId(event.target.value)}
        />
        <div className="page-actions">
          <Button onClick={() => show({ kind: "choose" })}>Save choice</Button>
          <Button variant="secondary" onClick={() => show({ kind: "add" })}>
            Add model
          </Button>
        </div>
      </div>
      {error && !open && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      <Table label="Models">
        <thead>
          <tr>
            <th>Model</th>
            <th>Input price per million tokens</th>
            <th>Output price per million tokens</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {overview.models.map((model) => (
            <tr key={model.id}>
              <td>{model.name}</td>
              <td>{model.input_price_per_million}</td>
              <td>{model.output_price_per_million}</td>
              <td>
                <Tag variant={model.enabled ? "success" : "neutral"}>
                  {model.enabled ? "On" : "Off"}
                </Tag>
              </td>
              <td>
                <Button
                  variant="secondary"
                  aria-label={`Edit prices of ${model.name}`}
                  onClick={() => show({ kind: "prices", model })}
                >
                  Edit prices
                </Button>{" "}
                <Button
                  variant="secondary"
                  aria-label={`${model.enabled ? "Switch off" : "Switch on"} ${model.name}`}
                  onClick={() => show({ kind: "switch", model })}
                >
                  {model.enabled ? "Switch off" : "Switch on"}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Dialog
        open={open !== null}
        onOpenChange={(next) => !next && setOpen(null)}
        title={open ? titles[open.kind] : ""}
        confirmLabel={open ? labels[open.kind] : undefined}
        onConfirm={() => void confirm()}
      >
        {open?.kind === "replace" && (
          <>
            <p>
              {open.model.name} is the{" "}
              {open.model.chosen_for.map((role) => ROLE_LABEL[role]).join(" and ")} model for new
              projects and is used by {open.model.projects.reading + open.model.projects.scoring}{" "}
              project settings.
            </p>
            <Select
              label="Replacement"
              options={open.replacements.map((item) => ({
                value: String(item.id),
                label: item.name,
              }))}
              value={replacementId}
              onChange={(event) => setReplacementId(event.target.value)}
            />
          </>
        )}
        {open?.kind === "add" && (
          <>
            <Input
              label="Model name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              error={fields.name}
            />
          </>
        )}
        {(open?.kind === "add" || open?.kind === "prices") && (
          <>
            <Input
              label="Input price per million tokens"
              value={inputPrice}
              onChange={(event) => setInputPrice(event.target.value)}
              error={fields.input_price_per_million}
            />
            <Input
              label="Output price per million tokens"
              value={outputPrice}
              onChange={(event) => setOutputPrice(event.target.value)}
              error={fields.output_price_per_million}
            />
          </>
        )}
        {open && open.kind !== "add" && (
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
    </div>
  );
}
