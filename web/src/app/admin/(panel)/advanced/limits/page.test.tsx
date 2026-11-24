import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import LimitsSettingsPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        items: [
          {
            key: "uploads.max_file_size_mb",
            group: "uploads",
            kind: "number",
            value: 10,
            default: 10,
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
  render(<LimitsSettingsPage />);
  expect(await screen.findByText("Max file size mb")).toBeTruthy();
});
