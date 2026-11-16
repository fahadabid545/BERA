import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ComparePage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/company/projects/p1/compare",
  useSearchParams: () => new URLSearchParams(""),
}));

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

describe("compare page", () => {
  it("shows the matrix of the project named in the address", async () => {
    render(await ComparePage({ params: Promise.resolve({ project: "p1" }) }));
    await screen.findByRole("alert");
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/company/projects/p1/matrix/?page=1");
  });
});
