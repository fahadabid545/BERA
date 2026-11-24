import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import MaintenancePage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ enabled: false, message: "Fake message" }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the settings of its page", async () => {
  render(<MaintenancePage />);
  expect(await screen.findByText("Fake message")).toBeTruthy();
});
