import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Page from "./page";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (path: string) => ({
    ok: true,
    status: 200,
    json: async () => (path === "/api/admin/plans/" ? [] : { codes: [] }),
  }));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Discount codes page", () => {
  it("shows the list", async () => {
    render(<Page />);
    expect(await screen.findByRole("region", { name: "Discount codes" })).toBeTruthy();
  });
});
