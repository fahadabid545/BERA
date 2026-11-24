import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import AdminUsersPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ admins: [], invitations: [] }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the admin team page with Invite admin", async () => {
  render(<AdminUsersPage />);
  expect(await screen.findByRole("button", { name: "Invite admin" })).toBeTruthy();
});
