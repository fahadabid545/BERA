import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SharedReports } from "./SharedReports";

const fetchMock = vi.fn();
const BASE = "/api/company/projects/p1/reports/";
const DAYS = { choices: [1, 7, 30], default: 7 };
const report = (over: object = {}) => ({
  id: "r1",
  created_at: "2026-11-14T10:00:00Z",
  expires_at: "2026-11-21T10:00:00Z",
  hide_contact: false,
  candidates: 3,
  views: 4,
  status: "active",
  ...over,
});
let reports: object[] = [];

beforeEach(() => {
  reports = [];
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === "POST" && path === BASE) {
      return { ok: true, status: 201, json: async () => ({ ...report(), token: "SECRETTOKEN" }) };
    }
    if (init?.method === "POST") return { ok: true, status: 200, json: async () => report() };
    return { ok: true, status: 200, json: async () => ({ days: DAYS, reports }) };
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const posts = () => fetchMock.mock.calls.filter((call) => call[1]?.method === "POST");

describe("shared reports", () => {
  it("creates a link with the default time and shows it once", async () => {
    const user = userEvent.setup();
    render(<SharedReports projectId="p1" />);
    await user.click(screen.getByRole("button", { name: "Share report" }));
    const dialog = await screen.findByRole("dialog", { name: "Share report" });
    expect((within(dialog).getByLabelText("Link expires after") as HTMLSelectElement).value).toBe(
      "7",
    );
    await user.click(within(dialog).getByRole("button", { name: "Create link" }));
    const shown = await screen.findByRole("dialog", { name: "Report link" });
    expect((within(shown).getByLabelText("Link") as HTMLInputElement).value).toBe(
      `${window.location.origin}/r/SECRETTOKEN`,
    );
    expect(JSON.parse(posts()[0][1].body)).toEqual({ days: 7, hide_contact: false });
  });

  it("offers the times the server allows and can hide contact details", async () => {
    const user = userEvent.setup();
    render(<SharedReports projectId="p1" />);
    await user.click(screen.getByRole("button", { name: "Share report" }));
    const dialog = await screen.findByRole("dialog", { name: "Share report" });
    const times = within(dialog)
      .getAllByRole("option")
      .map((option) => option.textContent);
    expect(times).toEqual(["1 day", "7 days", "30 days"]);
    await user.selectOptions(within(dialog).getByLabelText("Link expires after"), "30");
    await user.click(within(dialog).getByRole("checkbox", { name: "Hide contact details" }));
    await user.click(within(dialog).getByRole("button", { name: "Create link" }));
    await screen.findByRole("dialog", { name: "Report link" });
    expect(JSON.parse(posts()[0][1].body)).toEqual({ days: 30, hide_contact: true });
  });

  it("shows the server's message when nothing can be shared", async () => {
    fetchMock.mockImplementation(async (_path: string, init?: RequestInit) =>
      init?.method === "POST"
        ? {
            ok: false,
            status: 400,
            json: async () => ({
              error: {
                code: "nothing_to_share",
                message: "There are no scored candidates to share yet.",
              },
            }),
          }
        : { ok: true, status: 200, json: async () => ({ days: DAYS, reports: [] }) },
    );
    const user = userEvent.setup();
    render(<SharedReports projectId="p1" />);
    await user.click(screen.getByRole("button", { name: "Share report" }));
    await user.click(await screen.findByRole("button", { name: "Create link" }));
    expect((await screen.findByRole("alert")).textContent).toContain("no scored candidates");
  });

  it("lists the links with status and views, and revokes after a confirmation", async () => {
    reports = [report(), report({ id: "r2", status: "revoked", views: 0 })];
    const user = userEvent.setup();
    render(<SharedReports projectId="p1" />);
    await user.click(screen.getByRole("button", { name: "Shared links" }));
    const table = await screen.findByRole("region", { name: "Shared links" });
    expect(within(table).getByText("Active")).toBeTruthy();
    expect(within(table).getByText("Revoked")).toBeTruthy();
    expect(within(table).getAllByRole("button", { name: "Revoke" })).toHaveLength(1);
    await user.click(within(table).getByRole("button", { name: "Revoke" }));
    expect(posts()).toHaveLength(0);
    const confirm = await screen.findByRole("dialog", { name: "Revoke link" });
    await user.click(within(confirm).getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0][0]).toBe(`${BASE}r1/revoke/`);
  });
});
