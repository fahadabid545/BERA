import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AiModelsPage from "./page";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AI Models page", () => {
  it("shows the models list", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ models: [], choice: { reading: "", scoring: "" } }),
    });
    render(<AiModelsPage />);
    expect(await screen.findByRole("button", { name: "Add model" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Models" })).toBeTruthy();
  });
});
