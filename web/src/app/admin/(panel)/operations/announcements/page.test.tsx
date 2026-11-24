import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { AdminRoleProvider } from "@/components/admin/role";

import AnnouncementsPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [], plans: [], companies: [] }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows New announcement to a super admin", async () => {
  render(
    <AdminRoleProvider value="super">
      <AnnouncementsPage />
    </AdminRoleProvider>,
  );
  expect(await screen.findByRole("button", { name: "New announcement" })).toBeTruthy();
});
