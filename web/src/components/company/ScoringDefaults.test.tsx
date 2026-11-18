import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FACTORS } from "./ExtraFactors";
import { ScoringDefaults } from "./ScoringDefaults";

const fetchMock = vi.fn();
const URL = "/api/company/scoring-defaults/";
const DEFAULTS = {
  must_weight_percent: 70,
  nice_weight_percent: 30,
  recommendation_threshold: 75,
  top_n: 10,
  cap_on_missing_must_have: false,
  top_n_cap: 20,
  factors: Object.fromEntries(FACTORS.map(({ name }) => [name, { enabled: false, weight: 50 }])),
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

describe("scoring defaults", () => {
  it("shows the current defaults with the nice-to-have weight as what is left", async () => {
    reply(200, DEFAULTS);
    render(<ScoringDefaults />);
    await screen.findByDisplayValue("75");
    expect(fetchMock.mock.calls[0][0]).toBe(URL);
    expect(field("Must-have weight (%)").value).toBe("70");
    expect(field("Nice-to-have weight (%)").value).toBe("30");
    expect(field("Nice-to-have weight (%)").readOnly).toBe(true);
    expect(screen.getByLabelText("Top list size (up to 20)")).toBeTruthy();
    for (const { label } of FACTORS) expect(screen.getByLabelText(label)).toBeTruthy();
  });

  it("changing the must-have weight updates the other so they total 100", async () => {
    reply(200, DEFAULTS);
    render(<ScoringDefaults />);
    await screen.findByDisplayValue("75");
    await userEvent.clear(field("Must-have weight (%)"));
    await userEvent.type(field("Must-have weight (%)"), "55");
    expect(field("Nice-to-have weight (%)").value).toBe("45");
  });

  it("saves every value and the factors, then confirms in a popup", async () => {
    reply(200, DEFAULTS);
    reply(200, { ...DEFAULTS, top_n: 5 });
    render(<ScoringDefaults />);
    await screen.findByDisplayValue("75");
    await userEvent.clear(field(/Top list size/));
    await userEvent.type(field(/Top list size/), "5");
    await userEvent.click(screen.getByLabelText("Recency of relevant work"));
    await userEvent.clear(field("Recency of relevant work weight (%)"));
    await userEvent.type(field("Recency of relevant work weight (%)"), "30");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Scoring defaults saved")).toBeTruthy();
    expect(fetchMock.mock.calls[1][0]).toBe(URL);
    expect(fetchMock.mock.calls[1][1].method).toBe("PUT");
    const body = sent();
    expect(body).toMatchObject({
      must_weight_percent: 70,
      nice_weight_percent: 30,
      recommendation_threshold: 75,
      top_n: 5,
      cap_on_missing_must_have: false,
    });
    expect(body.factors.recency).toEqual({ enabled: true, weight: 30 });
    expect(body.factors.education).toEqual({ enabled: false, weight: 50 });
  });

  it("shows a refused value next to its field and no popup", async () => {
    reply(200, DEFAULTS);
    reply(400, {
      error: {
        code: "invalid",
        message: "Check the form.",
        fields: { recommendation_threshold: "The threshold is a percent from 0 to 100." },
      },
    });
    render(<ScoringDefaults />);
    await screen.findByDisplayValue("75");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("The threshold is a percent from 0 to 100.")).toBeTruthy();
    expect(screen.queryByText("Scoring defaults saved")).toBeNull();
  });

  it("shows the server's message when the top list is above the plan", async () => {
    reply(200, DEFAULTS);
    reply(409, { error: { code: "limit_reached", message: "Your plan allows a top list of 20." } });
    render(<ScoringDefaults />);
    await screen.findByDisplayValue("75");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect((await screen.findByRole("alert")).textContent).toContain("top list of 20");
  });

  it("shows only the error when the person may not see the defaults", async () => {
    reply(403, { error: { code: "forbidden", message: "You do not have access." } });
    render(<ScoringDefaults />);
    expect((await screen.findByRole("alert")).textContent).toContain("do not have access");
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });
});
