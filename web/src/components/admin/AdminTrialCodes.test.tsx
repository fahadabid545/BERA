import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminTrialCodes } from "./AdminTrialCodes";

const fetchMock = vi.fn();
const PLANS = [
  { id: 3, name: "Fake Starter", status: "active" },
  { id: 4, name: "Fake Hidden", status: "hidden" },
];
const code = (over: object = {}) => ({
  id: 1,
  name: "Fake campaign",
  plan: { id: 3, name: "Fake Starter" },
  days: 14,
  cv_limit: 50,
  expires_at: "2026-12-31T00:00:00Z",
  enabled: true,
  status: "unused",
  redeemed_company: null,
  ...over,
});
let codes: object[];

function reply(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body };
}
const posts = () =>
  fetchMock.mock.calls.filter((call) => call[1]?.method && call[1].method !== "GET");

beforeEach(() => {
  codes = [code()];
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === "POST")
      return reply({ ...code({ id: 2 }), code: "TRIAL-AAAA-BBBB-CCCC" }, 201);
    if (init?.method === "PATCH") return reply(code({ enabled: false, status: "off" }));
    if (path === "/api/admin/plans/") return reply(PLANS);
    return reply({ codes });
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("trial codes", () => {
  it("lists the codes with their status and who used them", async () => {
    codes = [
      code(),
      code({
        id: 2,
        name: "Used one",
        status: "redeemed",
        redeemed_company: { id: 9, name: "Fake Co" },
      }),
    ];
    render(<AdminTrialCodes />);
    const table = await screen.findByRole("region", { name: "Trial codes" });
    expect(within(table).getByText("Fake campaign")).toBeTruthy();
    expect(within(table).getByText("Unused")).toBeTruthy();
    expect(within(table).getByText("Fake Co")).toBeTruthy();
    expect(within(table).queryByRole("button", { name: "Switch off Used one" })).toBeNull();
  });

  it("makes a code and shows it once", async () => {
    const user = userEvent.setup();
    render(<AdminTrialCodes />);
    await user.click(await screen.findByRole("button", { name: "New trial code" }));
    const dialog = await screen.findByRole("dialog", { name: "New trial code" });
    await user.type(within(dialog).getByLabelText("Name"), "Spring");
    await user.type(within(dialog).getByLabelText("Days"), "7");
    await user.type(within(dialog).getByLabelText("CVs"), "30");
    await user.type(within(dialog).getByLabelText("Code expires on"), "2026-12-31");
    expect(within(dialog).queryByRole("option", { name: "Fake Hidden" })).toBeNull();
    await user.click(within(dialog).getByRole("button", { name: "Create code" }));
    expect(await screen.findByLabelText("New trial code")).toBeTruthy();
    expect(screen.getByText("TRIAL-AAAA-BBBB-CCCC")).toBeTruthy();
    const body = JSON.parse(posts()[0][1].body as string);
    expect(body).toEqual({
      name: "Spring",
      plan_id: 3,
      days: 7,
      cv_limit: 30,
      expires_at: "2026-12-31T23:59:59Z",
    });
  });

  it("switches a code off", async () => {
    const user = userEvent.setup();
    render(<AdminTrialCodes />);
    await user.click(await screen.findByRole("button", { name: "Switch off Fake campaign" }));
    await waitFor(() => expect(posts()[0][0]).toBe("/api/admin/trials/codes/1/"));
    expect(JSON.parse(posts()[0][1].body as string)).toEqual({ enabled: false });
  });

  it("shows the server's reason when a code is refused", async () => {
    fetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST")
        return reply(
          { error: { code: "invalid_trial", message: "Check the trial's days and CVs." } },
          400,
        );
      if (path === "/api/admin/plans/") return reply(PLANS);
      return reply({ codes });
    });
    const user = userEvent.setup();
    render(<AdminTrialCodes />);
    await user.click(await screen.findByRole("button", { name: "New trial code" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Create code" }),
    );
    expect(await screen.findByText("Check the trial's days and CVs.")).toBeTruthy();
  });
});
