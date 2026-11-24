import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuditLogViewer } from "./AuditLogViewer";

const fetchMock = vi.fn();
const entry = (id: number, over: object = {}) => ({
  id,
  at: "2026-03-10T12:00:00Z",
  action: "auth.login",
  person: { kind: "admin", id: 1, name: "Fake Admin" },
  company_id: 5,
  company: "Fake Company",
  target_kind: "",
  target_id: "",
  reason: "",
  details: {},
  ...over,
});
const PAGE: { items: unknown[]; next: string | null; actions: string[] } = {
  items: [
    entry(2, {
      action: "admin.status_changed",
      reason: "Fake reason.",
      details: { status_after: "blocked" },
    }),
    entry(1, { person: { kind: "none", id: null, name: "" }, company_id: null, company: "" }),
  ],
  next: null,
  actions: ["auth.login", "admin.status_changed"],
};
const reply = (status: number, body: unknown) =>
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
const rows = () =>
  Array.from(screen.getByRole("region", { name: "Audit log" }).querySelectorAll("tbody tr"));
const cells = (row: Element) =>
  Array.from(row.querySelectorAll("th, td")).map((cell) => cell.textContent);
const last = () => String(fetchMock.mock.calls.at(-1)?.[0]);

async function show(page = PAGE) {
  reply(200, page);
  render(<AuditLogViewer />);
  await screen.findByRole("region", { name: "Audit log" });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Audit log viewer", () => {
  it("lists each entry with time, action, person, company, reason and details", async () => {
    await show();
    expect(cells(rows()[0])).toEqual([
      "2026-03-10 12:00",
      "admin.status_changed",
      "Fake Admin",
      "Fake Company",
      "",
      "Fake reason.",
      "status_after: blocked",
    ]);
    expect(cells(rows()[1])[2]).toBe("System");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/admin/audit-log/");
  });

  it("shows No entries when nothing matches", async () => {
    reply(200, { items: [], next: null, actions: [] });
    render(<AuditLogViewer />);
    expect(await screen.findByText("No entries.")).toBeTruthy();
  });

  it("filters by person, company, action and date", async () => {
    await show();
    await userEvent.type(screen.getByLabelText("Person"), "zelda");
    await userEvent.type(screen.getByLabelText("Company ID"), "5");
    await userEvent.selectOptions(screen.getByLabelText("Action"), "auth.login");
    await userEvent.type(screen.getByLabelText("From"), "2026-03-01");
    await userEvent.type(screen.getByLabelText("To"), "2026-03-31");
    reply(200, PAGE);
    await userEvent.click(screen.getByRole("button", { name: "Filter" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const query = new URLSearchParams(last().split("?")[1]);
    expect(Object.fromEntries(query)).toEqual({
      person: "zelda",
      company: "5",
      action: "auth.login",
      from_date: "2026-03-01",
      to_date: "2026-03-31",
    });
  });

  it("loads the next page after the first and keeps what was shown", async () => {
    await show({ ...PAGE, next: "marker|1" });
    reply(200, { ...PAGE, items: [entry(0, { action: "invite.sent" })], next: null });
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() => expect(rows()).toHaveLength(3));
    expect(last()).toBe("/api/admin/audit-log/?cursor=marker%7C1");
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });

  it("shows the server's message for a bad filter", async () => {
    await show();
    reply(400, {
      error: {
        code: "validation_error",
        message: "Please check the form and try again.",
        fields: { person: "Type at least 3 letters." },
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "Filter" }));
    expect(await screen.findByText("Type at least 3 letters.")).toBeTruthy();
  });

  it("exports with the filters that are applied", async () => {
    await show();
    await userEvent.selectOptions(screen.getByLabelText("Action"), "auth.login");
    reply(200, PAGE);
    await userEvent.click(screen.getByRole("button", { name: "Filter" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const blob = new Blob(["a,b"]);
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, blob: async () => blob });
    const create = vi.fn().mockReturnValue("blob:fake");
    vi.stubGlobal("URL", { createObjectURL: create, revokeObjectURL: vi.fn() });
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => expect(create).toHaveBeenCalledWith(blob));
    expect(last()).toBe("/api/admin/audit-log/export/?action=auth.login");
  });

  it("says in plain words when the export is too large", async () => {
    await show();
    reply(400, {
      error: {
        code: "audit_export_too_large",
        message: "More than 50000 entries match. Narrow the dates or filters and try again.",
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Narrow the dates");
  });

  it("shows the server's message when the page cannot load", async () => {
    reply(403, {
      error: { code: "not_allowed", message: "You do not have permission to do this." },
    });
    render(<AuditLogViewer />);
    expect((await screen.findByRole("alert")).textContent).toBe(
      "You do not have permission to do this.",
    );
  });
});
