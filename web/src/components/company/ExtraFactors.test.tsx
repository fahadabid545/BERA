import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExtraFactors } from "./ExtraFactors";

const fetchMock = vi.fn();
const BASE = "/api/company/projects/p1/factors/";
const NAMES = [
  "experience_years",
  "education",
  "seniority",
  "recency",
  "gaps_and_changes",
  "readability",
  "confidence",
];
const LABELS = [
  "Experience years match",
  "Education match",
  "Seniority fit",
  "Recency of relevant work",
  "Career gaps and job changes",
  "CV readability",
  "Confidence level",
];
const FACTORS = {
  required_years: null,
  required_education: null,
  seniority: null,
  factors: Object.fromEntries(NAMES.map((name) => [name, { enabled: false, weight: 50 }])),
  max_required_years: 60,
};

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}
const sent = () => JSON.parse(fetchMock.mock.calls[1][1].body as string);

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("extra scoring factors", () => {
  it("shows each of the seven factors with a switch and a weight", async () => {
    reply(200, FACTORS);
    render(<ExtraFactors projectId="p1" />);
    await screen.findByLabelText("Years of experience needed");
    for (const label of LABELS) {
      expect((screen.getByLabelText(label) as HTMLInputElement).checked).toBe(false);
      expect((screen.getByLabelText(`${label} weight (%)`) as HTMLInputElement).value).toBe("50");
    }
  });

  it("switches one factor on, weights it and saves everything with a popup", async () => {
    reply(200, FACTORS);
    const saved = {
      ...FACTORS,
      required_years: 5,
      required_education: "master",
      seniority: "senior",
      factors: { ...FACTORS.factors, recency: { enabled: true, weight: 80 } },
    };
    reply(200, saved);
    render(<ExtraFactors projectId="p1" />);
    await screen.findByLabelText("Years of experience needed");
    await userEvent.click(screen.getByLabelText("Recency of relevant work"));
    const weight = screen.getByLabelText("Recency of relevant work weight (%)");
    await userEvent.clear(weight);
    await userEvent.type(weight, "80");
    await userEvent.type(screen.getByLabelText("Years of experience needed"), "5");
    await userEvent.selectOptions(screen.getByLabelText("Education needed"), "master");
    await userEvent.selectOptions(screen.getByLabelText("Seniority needed"), "senior");
    await userEvent.click(screen.getByRole("button", { name: "Save scoring factors" }));
    expect(await screen.findByText("Scoring factors saved")).toBeTruthy();
    expect(fetchMock.mock.calls[1][0]).toBe(BASE);
    expect(fetchMock.mock.calls[1][1].method).toBe("PUT");
    expect(sent()).toMatchObject({
      required_years: 5,
      required_education: "master",
      seniority: "senior",
    });
    expect(sent().factors.recency).toEqual({ enabled: true, weight: 80 });
    expect(sent().factors.education).toEqual({ enabled: false, weight: 50 });
  });

  it("sends nothing for job fields that are left empty", async () => {
    reply(200, FACTORS);
    reply(200, FACTORS);
    render(<ExtraFactors projectId="p1" />);
    await screen.findByLabelText("Years of experience needed");
    await userEvent.click(screen.getByRole("button", { name: "Save scoring factors" }));
    await screen.findByText("Scoring factors saved");
    expect(sent()).toMatchObject({
      required_years: null,
      required_education: null,
      seniority: null,
    });
  });

  it("shows a refused weight next to its field and no popup", async () => {
    reply(200, FACTORS);
    reply(400, {
      error: {
        code: "validation_error",
        message: "Check.",
        fields: { "factors.recency": "A weight is a percent from 0 to 100." },
      },
    });
    render(<ExtraFactors projectId="p1" />);
    await screen.findByLabelText("Years of experience needed");
    await userEvent.click(screen.getByRole("button", { name: "Save scoring factors" }));
    expect(await screen.findByText("A weight is a percent from 0 to 100.")).toBeTruthy();
    expect(screen.queryByText("Scoring factors saved")).toBeNull();
  });

  it("says plainly when the factors cannot be loaded", async () => {
    reply(404, { error: { code: "not_found", message: "Not found." } });
    render(<ExtraFactors projectId="p1" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Not found.");
  });
});
