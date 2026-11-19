import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CompanyDetailPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ error: { code: "not_found", message: "Not found." } }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("company detail page", () => {
  it("asks for the company named in the address", async () => {
    render(await CompanyDetailPage({ params: Promise.resolve({ company: "7" }) }));
    await screen.findByRole("alert");
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/admin/companies/7/");
  });
});
