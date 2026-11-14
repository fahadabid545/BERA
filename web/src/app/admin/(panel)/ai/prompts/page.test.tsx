import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AiPromptsPage from "./page";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AI Prompts page", () => {
  it("shows the prompt versions", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ reading: [], scoring: [] }),
    });
    render(<AiPromptsPage />);
    expect(await screen.findByRole("button", { name: "New version" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Reading versions" })).toBeTruthy();
  });
});
