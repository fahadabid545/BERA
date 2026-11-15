import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SharedReportPage, { metadata } from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ error: { code: "report_unavailable", message: "x" } }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("shared report page", () => {
  it("asks for the report named in the address", async () => {
    render(await SharedReportPage({ params: Promise.resolve({ token: "tok" }) }));
    await screen.findByText("This report is no longer available.");
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/reports/tok/");
  });

  it("is kept out of search engines", () => {
    expect(metadata.robots).toEqual({ index: false, follow: false });
  });
});
