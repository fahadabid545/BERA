import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminAnnouncements } from "./AdminAnnouncements";
import { AdminRoleProvider } from "./role";
import type { AdminRole } from "./navigation";

const fetchMock = vi.fn();
const item = (id: number, over: object = {}) => ({
  id,
  message: `Fake notice ${id}`,
  starts_at: "2026-01-01T09:00:00Z",
  ends_at: "2026-01-02T09:00:00Z",
  target: "everyone",
  plan_id: null,
  plan: null,
  company_ids: [],
  status: "live",
  ...over,
});
const LISTING = {
  items: [
    item(1),
    item(2, { target: "plan", plan_id: 7, plan: "Fake Plan", status: "scheduled" }),
    item(3, { target: "companies", company_ids: [5], status: "expired" }),
  ],
  plans: [{ id: 7, name: "Fake Plan" }],
  companies: [
    { id: 5, name: "Fake Company" },
    { id: 6, name: "Other Company" },
  ],
};
const reply = (status: number, body: unknown) =>
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
const rows = () =>
  Array.from(screen.getByRole("region", { name: "Announcements" }).querySelectorAll("tbody tr"));
const cells = (row: Element) =>
  Array.from(row.querySelectorAll("th, td")).map((c) => c.textContent);

function show(role: AdminRole = "super") {
  reply(200, LISTING);
  render(
    <AdminRoleProvider value={role}>
      <AdminAnnouncements />
    </AdminRoleProvider>,
  );
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Announcements (admin)", () => {
  it("lists each banner with who sees it and its state in words", async () => {
    show();
    await screen.findByRole("region", { name: "Announcements" });
    const listed = rows().map(cells);
    expect([listed[0][0], listed[0][1], listed[0][4]]).toEqual([
      "Fake notice 1",
      "Everyone",
      "Live",
    ]);
    expect([listed[1][1], listed[1][4]]).toEqual(["Plan: Fake Plan", "Scheduled"]);
    expect([listed[2][1], listed[2][4]]).toEqual(["Companies: Fake Company", "Expired"]);
  });

  it("shows No announcements when there are none", async () => {
    reply(200, { items: [], plans: [], companies: [] });
    render(
      <AdminRoleProvider value="super">
        <AdminAnnouncements />
      </AdminRoleProvider>,
    );
    expect(await screen.findByText("No announcements.")).toBeTruthy();
  });

  it("hides every way to change a banner from support", async () => {
    show("support");
    await screen.findByRole("region", { name: "Announcements" });
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("creates a banner for chosen companies", async () => {
    show();
    await screen.findByRole("region", { name: "Announcements" });
    await userEvent.click(screen.getByRole("button", { name: "New announcement" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Message"), "Fake hello");
    await userEvent.type(within(dialog).getByLabelText("Starts"), "2030-01-01T09:00");
    await userEvent.type(within(dialog).getByLabelText("Ends"), "2030-01-02T09:00");
    await userEvent.selectOptions(within(dialog).getByLabelText("Shown to"), "companies");
    await userEvent.click(within(dialog).getByRole("checkbox", { name: "Other Company" }));
    reply(201, { ...LISTING, items: [] });
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [path, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect([path, init.method]).toEqual(["/api/admin/announcements/", "POST"]);
    const sent = JSON.parse(String(init.body));
    expect(sent).toMatchObject({ message: "Fake hello", target: "companies", companies: [6] });
    expect(sent.plan).toBeUndefined();
  });

  it("aims a banner at a plan", async () => {
    show();
    await screen.findByRole("region", { name: "Announcements" });
    await userEvent.click(screen.getByRole("button", { name: "New announcement" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.selectOptions(within(dialog).getByLabelText("Shown to"), "plan");
    await userEvent.selectOptions(within(dialog).getByLabelText("Plan"), "7");
    reply(201, LISTING);
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const sent = JSON.parse(String((fetchMock.mock.calls[1] as [string, RequestInit])[1].body));
    expect(sent).toMatchObject({ target: "plan", plan: 7 });
    expect(sent.companies).toBeUndefined();
  });

  it("brings the form back with the server's messages when it is refused", async () => {
    show();
    await screen.findByRole("region", { name: "Announcements" });
    await userEvent.click(screen.getByRole("button", { name: "New announcement" }));
    await userEvent.type(screen.getByLabelText("Message"), "Fake hello");
    reply(400, {
      error: {
        code: "validation_error",
        message: "Please check the form and try again.",
        fields: { ends_at: "The end must be in the future." },
      },
    });
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("The end must be in the future.")).toBeTruthy();
    expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toBe("Fake hello");
  });

  it("edits a banner with its own values filled in", async () => {
    show();
    await screen.findByRole("region", { name: "Announcements" });
    await userEvent.click(within(rows()[0] as HTMLElement).getByRole("button", { name: "Edit" }));
    const dialog = screen.getByRole("dialog");
    expect((within(dialog).getByLabelText("Message") as HTMLTextAreaElement).value).toBe(
      "Fake notice 1",
    );
    reply(200, LISTING);
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [path, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect([path, init.method]).toEqual(["/api/admin/announcements/1/", "PUT"]);
  });

  it("asks in a popup before deleting, and deletes only when confirmed", async () => {
    show();
    await screen.findByRole("region", { name: "Announcements" });
    await userEvent.click(within(rows()[0] as HTMLElement).getByRole("button", { name: "Delete" }));
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await userEvent.click(within(rows()[0] as HTMLElement).getByRole("button", { name: "Delete" }));
    reply(200, { ...LISTING, items: [] });
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }),
    );
    expect(await screen.findByText("No announcements.")).toBeTruthy();
    const [path, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect([path, init.method]).toEqual(["/api/admin/announcements/1/", "DELETE"]);
  });

  it("shows the server's message when the page cannot load", async () => {
    reply(403, {
      error: { code: "not_allowed", message: "You do not have permission to do this." },
    });
    render(<AdminAnnouncements />);
    expect((await screen.findByRole("alert")).textContent).toBe(
      "You do not have permission to do this.",
    );
  });
});
