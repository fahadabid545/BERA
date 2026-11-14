import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ScoringSettings } from "./ScoringSettings";

const fetchMock = vi.fn();
const BASE = "/api/company/projects/p1/scoring/";
const SCORING = {
  must_weight_percent: 70,
  nice_weight_percent: 30,
  recommendation_threshold: 75,
  top_n: 10,
  cap_on_missing_must_have: false,
  top_n_cap: 20,
};

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}
const sent = () => JSON.parse(fetchMock.mock.calls[1][1].body as string);
const field = (label: string | RegExp) => screen.getByLabelText(label) as HTMLInputElement;

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("scoring settings", () => {
  it("shows the current values with the nice-to-have weight as what is left", async () => {
    reply(200, SCORING);
    render(<ScoringSettings projectId="p1" />);
    await screen.findByDisplayValue("75");
    expect(field("Must-have weight (%)").value).toBe("70");
    expect(field("Nice-to-have weight (%)").value).toBe("30");
    expect(field("Nice-to-have weight (%)").readOnly).toBe(true);
    expect(field(/Top list size/).value).toBe("10");
    expect(screen.getByLabelText("Top list size (up to 20)")).toBeTruthy();
  });

  it("changing the must-have weight updates the other so they total 100", async () => {
    reply(200, SCORING);
    render(<ScoringSettings projectId="p1" />);
    await screen.findByDisplayValue("75");
    await userEvent.clear(field("Must-have weight (%)"));
    await userEvent.type(field("Must-have weight (%)"), "55");
    expect(field("Nice-to-have weight (%)").value).toBe("45");
  });

  it("saves every value and confirms in a popup", async () => {
    reply(200, SCORING);
    reply(200, { ...SCORING, must_weight_percent: 60, nice_weight_percent: 40, top_n: 5 });
    render(<ScoringSettings projectId="p1" />);
    await screen.findByDisplayValue("75");
    await userEvent.clear(field("Must-have weight (%)"));
    await userEvent.type(field("Must-have weight (%)"), "60");
    await userEvent.clear(field(/Top list size/));
    await userEvent.type(field(/Top list size/), "5");
    await userEvent.click(screen.getByRole("button", { name: "Save scoring settings" }));
    expect(await screen.findByText("Scoring settings saved")).toBeTruthy();
    expect(fetchMock.mock.calls[1][0]).toBe(BASE);
    expect(sent()).toEqual({
      must_weight_percent: 60,
      nice_weight_percent: 40,
      recommendation_threshold: 75,
      top_n: 5,
      cap_on_missing_must_have: false,
    });
  });

  it("saves the cap switch when it is ticked", async () => {
    reply(200, SCORING);
    reply(200, { ...SCORING, cap_on_missing_must_have: true });
    render(<ScoringSettings projectId="p1" />);
    await screen.findByDisplayValue("75");
    await userEvent.click(screen.getByLabelText("Cap the score when a must-have is missing"));
    await userEvent.click(screen.getByRole("button", { name: "Save scoring settings" }));
    expect(await screen.findByText("Scoring settings saved")).toBeTruthy();
    expect(sent().cap_on_missing_must_have).toBe(true);
  });

  it("shows the cap switch as saved", async () => {
    reply(200, { ...SCORING, cap_on_missing_must_have: true });
    render(<ScoringSettings projectId="p1" />);
    await screen.findByDisplayValue("75");
    const box = screen.getByLabelText("Cap the score when a must-have is missing");
    expect((box as HTMLInputElement).checked).toBe(true);
  });

  it("shows an impossible combination's message next to the field", async () => {
    reply(200, SCORING);
    reply(400, {
      error: {
        code: "validation_error",
        message: "Check.",
        fields: { recommendation_threshold: "The threshold is a percent from 0 to 100." },
      },
    });
    render(<ScoringSettings projectId="p1" />);
    await screen.findByDisplayValue("75");
    await userEvent.click(screen.getByRole("button", { name: "Save scoring settings" }));
    expect(await screen.findByText("The threshold is a percent from 0 to 100.")).toBeTruthy();
    expect(screen.queryByText("Scoring settings saved")).toBeNull();
  });

  it("a top list above the plan's cap opens the Upgrade popup", async () => {
    reply(200, SCORING);
    reply(409, {
      error: {
        code: "top_n_limit_exceeded",
        message: "Your plan allows a top list of at most 20.",
        details: { limit: 20, prompt: "upgrade" },
      },
    });
    render(<ScoringSettings projectId="p1" />);
    await screen.findByDisplayValue("75");
    await userEvent.click(screen.getByRole("button", { name: "Save scoring settings" }));
    expect(await screen.findByText("Upgrade your plan")).toBeTruthy();
  });

  it("says plainly when the settings cannot be loaded", async () => {
    reply(404, { error: { code: "not_found", message: "Not found." } });
    render(<ScoringSettings projectId="p1" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Not found.");
  });
});
