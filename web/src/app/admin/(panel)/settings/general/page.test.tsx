import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import GeneralSettingsPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        items: [
          {
            key: "general.app_name",
            group: "general",
            kind: "text",
            value: "Bera",
            default: "Bera",
            is_default: true,
          },
        ],
      }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the settings of its page", async () => {
  render(<GeneralSettingsPage />);
  expect(await screen.findByText("App name")).toBeTruthy();
});
