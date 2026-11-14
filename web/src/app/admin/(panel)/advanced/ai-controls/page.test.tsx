import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import AiControlsPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        paused: false,
        paused_by_admin: false,
        paused_automatically: false,
        resumes_at: null,
        message: "",
      }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the AI switch", async () => {
  render(<AiControlsPage />);
  expect(await screen.findByRole("button", { name: "Pause all AI" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Resume AI" })).toBeTruthy();
});
