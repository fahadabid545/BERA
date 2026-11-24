import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import AdminSecurityPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        items: [
          {
            key: "passwords.min_length",
            group: "passwords",
            kind: "number",
            value: 12,
            default: 12,
            is_default: true,
          },
        ],
        admin_two_step: { required: true, set_up: 1, not_set_up: 0 },
      }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the settings of its page", async () => {
  render(<AdminSecurityPage />);
  expect(await screen.findByText("Min length")).toBeTruthy();
});
