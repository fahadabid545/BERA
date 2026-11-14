import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AiModels } from "./AiModels";

const fetchMock = vi.fn();
const MODEL = {
  input_price_per_million: "1.0000",
  output_price_per_million: "2.0000",
  enabled: true,
  chosen_for: [],
  projects: { reading: 0, scoring: 0 },
};
const OVERVIEW = {
  models: [
    { ...MODEL, id: 1, name: "reader-1", chosen_for: ["reading"] },
    { ...MODEL, id: 2, name: "scorer-1", chosen_for: ["scoring"] },
    { ...MODEL, id: 3, name: "spare", enabled: false },
  ],
  choice: { reading: "reader-1", scoring: "scorer-1" },
};

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}
const call = (index: number) => ({
  url: fetchMock.mock.calls[index][0] as string,
  init: fetchMock.mock.calls[index][1],
  body: JSON.parse((fetchMock.mock.calls[index][1].body as string) ?? "{}"),
});

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function shown() {
  reply(200, OVERVIEW);
  render(<AiModels />);
  await screen.findByText("spare");
}

describe("models list", () => {
  it("lists every model with its prices and whether it is on", async () => {
    await shown();
    const table = screen.getByRole("region", { name: "Models" });
    expect(within(table).getByText("reader-1")).toBeTruthy();
    expect(within(table).getAllByText("On")).toHaveLength(2);
    expect(within(table).getByText("Off")).toBeTruthy();
  });

  it("offers only models that are on in the two dropdowns, with the current choice selected", async () => {
    await shown();
    const reading = screen.getByLabelText("Reading model") as HTMLSelectElement;
    expect(reading.value).toBe("1");
    expect(Array.from(reading.options).map((option) => option.text)).toEqual([
      "reader-1",
      "scorer-1",
    ]);
    expect((screen.getByLabelText("Scoring model") as HTMLSelectElement).value).toBe("2");
  });

  it("shows an error when the list cannot be loaded", async () => {
    reply(403, { error: { code: "forbidden", message: "You do not have access." } });
    render(<AiModels />);
    expect((await screen.findByRole("alert")).textContent).toBe("You do not have access.");
  });
});

describe("choosing the models", () => {
  it("asks for a reason in a popup, then saves both choices", async () => {
    await shown();
    await userEvent.selectOptions(screen.getByLabelText("Reading model"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Save choice" }));
    await userEvent.type(screen.getByLabelText("Reason"), "Cheaper");
    reply(200, { choice: { reading: "scorer-1", scoring: "scorer-1" } });
    reply(200, OVERVIEW);
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Save choice" }),
    );
    const saved = call(1);
    expect(saved.url).toBe("/api/admin/ai/models/selection/");
    expect(saved.init.method).toBe("PUT");
    expect(saved.body).toEqual({ reason: "Cheaper", reading_model: 2, scoring_model: 2 });
  });

  it("shows the server's refusal in plain words", async () => {
    await shown();
    await userEvent.click(screen.getByRole("button", { name: "Save choice" }));
    reply(400, { error: { code: "nothing_changed", message: "Nothing was changed." } });
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Save choice" }),
    );
    expect((await screen.findByRole("alert")).textContent).toBe("Nothing was changed.");
  });
});

describe("adding and pricing models", () => {
  it("adds a model with its two prices", async () => {
    await shown();
    await userEvent.click(screen.getByRole("button", { name: "Add model" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Model name"), "gpt-new");
    await userEvent.type(within(dialog).getByLabelText("Input price per million tokens"), "0.15");
    await userEvent.type(within(dialog).getByLabelText("Output price per million tokens"), "0.6");
    reply(201, {});
    reply(200, OVERVIEW);
    await userEvent.click(within(dialog).getByRole("button", { name: "Add model" }));
    expect(call(1).url).toBe("/api/admin/ai/models/");
    expect(call(1).body).toEqual({
      name: "gpt-new",
      input_price_per_million: "0.15",
      output_price_per_million: "0.6",
    });
  });

  it("edits the prices of one model with a reason", async () => {
    await shown();
    await userEvent.click(screen.getByRole("button", { name: "Edit prices of reader-1" }));
    const dialog = screen.getByRole("dialog");
    const input = within(dialog).getByLabelText(
      "Input price per million tokens",
    ) as HTMLInputElement;
    expect(input.value).toBe("1.0000");
    await userEvent.clear(input);
    await userEvent.type(input, "3");
    await userEvent.type(within(dialog).getByLabelText("Reason"), "New price list");
    reply(200, {});
    reply(200, OVERVIEW);
    await userEvent.click(within(dialog).getByRole("button", { name: "Save prices" }));
    expect(call(1).url).toBe("/api/admin/ai/models/1/");
    expect(call(1).init.method).toBe("PATCH");
    expect(call(1).body).toMatchObject({ reason: "New price list", input_price_per_million: "3" });
  });
});

describe("switching a model off", () => {
  it("switches a model that is not in use off after a reason", async () => {
    await shown();
    await userEvent.click(screen.getByRole("button", { name: "Switch on spare" }));
    await userEvent.type(screen.getByLabelText("Reason"), "Needed again");
    reply(200, {});
    reply(200, OVERVIEW);
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Continue" }),
    );
    expect(call(1).body).toEqual({ reason: "Needed again", enabled: true });
  });

  it("warns when the model is in use and offers a replacement", async () => {
    await shown();
    await userEvent.click(screen.getByRole("button", { name: "Switch off reader-1" }));
    await userEvent.type(screen.getByLabelText("Reason"), "Retired");
    reply(409, {
      error: {
        code: "model_in_use",
        message: "This model is in use. Choose a replacement to disable it.",
        details: { replacements: [{ id: 2, name: "scorer-1" }] },
      },
    });
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Continue" }),
    );
    const warning = await screen.findByRole("dialog");
    expect(within(warning).getByText("This model is in use")).toBeTruthy();
    expect(within(warning).getByText(/reader-1 is the reading model/)).toBeTruthy();
    expect((within(warning).getByLabelText("Replacement") as HTMLSelectElement).value).toBe("2");

    await userEvent.type(within(warning).getByLabelText("Reason"), "Retired");
    reply(200, {});
    reply(200, OVERVIEW);
    await userEvent.click(within(warning).getByRole("button", { name: "Switch off and replace" }));
    expect(call(2).body).toEqual({ reason: "Retired", enabled: false, replacement: 2 });
  });
});
