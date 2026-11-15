import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SharedReportView } from "./SharedReportView";

const fetchMock = vi.fn();
const entry = (over: object = {}) => ({
  rank: 1,
  candidate: "Candidate 1",
  score: "90.0",
  grade: "A",
  strengths: ["Strong Python"],
  risks: ["Short tenure"],
  ...over,
});

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function serve(ok: boolean, body: unknown) {
  fetchMock.mockResolvedValue({ ok, status: ok ? 200 : 404, json: async () => body });
}

describe("shared report page", () => {
  it("asks for the report once, with the token from the address", async () => {
    serve(true, {
      title: "Backend",
      expires_at: "2026-11-21T10:00:00Z",
      hide_contact: false,
      entries: [entry()],
    });
    render(<SharedReportView token="abc_DEF-123" />);
    await screen.findByText("Backend");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/reports/abc_DEF-123/");
  });

  it("shows rank, score, grade, strengths and risks, and the contact details when shared", async () => {
    serve(true, {
      title: "Backend",
      expires_at: "2026-11-21T10:00:00Z",
      hide_contact: false,
      entries: [
        entry({
          contact: { name: "Anna Example", email: "anna@example.com", phone: "+1 555 0100" },
        }),
      ],
    });
    render(<SharedReportView token="t" />);
    expect(await screen.findByText("1. Anna Example")).toBeTruthy();
    expect(screen.getByText(/Score 90.0/)).toBeTruthy();
    expect(screen.getByText("Grade A")).toBeTruthy();
    expect(screen.getByText("Strong Python")).toBeTruthy();
    expect(screen.getByText("Short tenure")).toBeTruthy();
    expect(screen.getByText("anna@example.com · +1 555 0100")).toBeTruthy();
  });

  it("shows only the position when contact details are hidden", async () => {
    serve(true, {
      title: "Backend",
      expires_at: "2026-11-21T10:00:00Z",
      hide_contact: true,
      entries: [entry()],
    });
    render(<SharedReportView token="t" />);
    expect(await screen.findByText("1. Candidate 1")).toBeTruthy();
    expect(screen.queryByText(/@/)).toBeNull();
  });

  it("says the report is no longer available for any refusal", async () => {
    serve(false, {
      error: { code: "report_unavailable", message: "This report is no longer available." },
    });
    render(<SharedReportView token="t" />);
    expect((await screen.findByRole("status")).textContent).toBe(
      "This report is no longer available.",
    );
  });
});
