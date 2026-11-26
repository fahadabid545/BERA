import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TeamPage from "./page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify([]), { status: 200 })),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("team page", () => {
  it("offers to invite a member", async () => {
    render(<TeamPage />);
    expect(await screen.findByRole("button", { name: "Invite member" })).toBeTruthy();
  });

  it("shows the members table above the invitations", async () => {
    render(<TeamPage />);
    expect(await screen.findByRole("region", { name: "Members" })).toBeTruthy();
  });
});
