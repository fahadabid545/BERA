import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import AiPlaygroundPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        models: ["model-a"],
        prompts: {
          reading: [{ number: 1, current: true }],
          scoring: [{ number: 1, current: true }],
        },
        budget: {
          month: "2026-11",
          limit: "10.000000",
          spent: "0.000000",
          remaining: "10.000000",
          used_up: false,
        },
      }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the playground form", async () => {
  render(<AiPlaygroundPage />);
  expect(await screen.findByRole("button", { name: "Run test" })).toBeTruthy();
  expect((screen.getByLabelText("CV file") as HTMLInputElement).type).toBe("file");
});
