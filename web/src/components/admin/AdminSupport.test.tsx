import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminSupport } from "./AdminSupport";

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const json = (body: unknown, ok = true) => ({ ok, status: ok ? 200 : 400, json: async () => body });

const item = {
  id: "t1",
  number: 7,
  title: "Cannot upload a CV",
  category: "bug",
  status: "open",
  created_at: "2026-11-20T10:00:00Z",
  updated_at: "2026-11-21T10:00:00Z",
  company_id: 3,
  company: "Fake Test Company",
  user: "Fake Owner",
};
const detail = {
  ...item,
  summary: "The person cannot upload a CV.",
  what_happened: "The upload button does nothing.",
  expected: "The CV is added.",
  steps: "Press Upload.",
  handled_by: null,
  messages: [],
};
const urls = () => fetchMock.mock.calls.map(([url]) => String(url));

function serve(over: Record<string, unknown> = {}) {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method === "PATCH") return json(over.patched ?? detail);
    if (/tickets\/t1\/$/.test(url)) return json(detail);
    return json(over.list ?? { total: 1, open_count: 1, items: [item] });
  });
}

describe("AdminSupport", () => {
  it("lists the tickets in hand with company, person, category and status", async () => {
    serve();
    render(<AdminSupport />);
    const table = await screen.findByRole("region", { name: "Support tickets" });
    expect(within(table).getByText("SUP-7")).toBeTruthy();
    expect(within(table).getByText("Cannot upload a CV")).toBeTruthy();
    expect(
      within(table).getByRole("link", { name: "Fake Test Company" }).getAttribute("href"),
    ).toBe("/admin/companies/3");
    expect(within(table).getByText("Bug")).toBeTruthy();
    expect(within(table).getAllByText("Open")).toHaveLength(2); // the status and the button
    expect(screen.getByText(/1 not yet picked up/)).toBeTruthy();
    expect(urls()[0]).toBe("/api/admin/support/tickets/");
  });

  it("asks again for a chosen status and category", async () => {
    serve();
    const user = userEvent.setup();
    render(<AdminSupport />);
    await screen.findByRole("region", { name: "Support tickets" });
    await user.selectOptions(screen.getByLabelText("Status"), "completed");
    await user.selectOptions(screen.getByLabelText("Category"), "billing");
    await waitFor(() =>
      expect(urls().at(-1)).toBe("/api/admin/support/tickets/?status=completed&category=billing"),
    );
  });

  it("says so when there are no tickets", async () => {
    serve({ list: { total: 0, open_count: 0, items: [] } });
    render(<AdminSupport />);
    expect(await screen.findByText("No tickets.")).toBeTruthy();
  });

  it("opens a ticket in full with what the agent wrote", async () => {
    serve();
    const user = userEvent.setup();
    render(<AdminSupport />);
    await user.click(await screen.findByRole("button", { name: "Open" }));
    const dialog = await screen.findByRole("dialog", { name: "Ticket SUP-7" });
    expect(within(dialog).getByText("The upload button does nothing.")).toBeTruthy();
    expect(within(dialog).getByText("Press Upload.")).toBeTruthy();
    expect(within(dialog).getByText(/Fake Test Company · Fake Owner/)).toBeTruthy();
  });

  it("asks the person a question and shows the updated conversation", async () => {
    const patched = {
      ...detail,
      status: "needs_reply",
      handled_by: "Fake Admin",
      messages: [
        { id: "m1", author: "admin", text: "Which browser?", created_at: "2026-11-21T09:00:00Z" },
        {
          id: "m2",
          author: "system",
          text: "Waiting for your reply",
          created_at: "2026-11-21T09:00:01Z",
        },
      ],
    };
    serve({ patched });
    const user = userEvent.setup();
    render(<AdminSupport />);
    await user.click(await screen.findByRole("button", { name: "Open" }));
    const dialog = await screen.findByRole("dialog");
    const save = within(dialog).getByRole("button", { name: "Save" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    await user.type(within(dialog).getByLabelText("Message to the person"), "Which browser?");
    expect(within(dialog).getByLabelText("Set status").textContent).toContain(
      "Waiting for a reply",
    );
    await user.click(save);
    expect(await within(dialog).findByText("Which browser?")).toBeTruthy();
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(call?.[0]).toBe("/api/admin/support/tickets/t1/");
    expect(JSON.parse(call?.[1].body)).toEqual({ message: "Which browser?" });
    expect(within(dialog).getByText(/Handled by Fake Admin/)).toBeTruthy();
    expect(
      (within(dialog).getByLabelText("Message to the person") as HTMLTextAreaElement).value,
    ).toBe("");
  });

  it("changes the status to working, completed or closed", async () => {
    serve({ patched: { ...detail, status: "working" } });
    const user = userEvent.setup();
    render(<AdminSupport />);
    await user.click(await screen.findByRole("button", { name: "Open" }));
    const dialog = await screen.findByRole("dialog");
    const options = within(within(dialog).getByLabelText("Set status")).getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual([
      "Keep as it is",
      "Working on it",
      "Waiting for your reply",
      "Completed",
      "Closed",
    ]);
    await user.selectOptions(within(dialog).getByLabelText("Set status"), "working");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
      expect(JSON.parse(call?.[1].body)).toEqual({ status: "working" });
    });
    expect(within(dialog).getAllByText("Working on it").length).toBeGreaterThan(0);
  });

  it("shows the server's message when a change is refused, keeping what was typed", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
      init?.method === "PATCH"
        ? json({ error: { code: "x", message: "Not now." } }, false)
        : /tickets\/t1\/$/.test(url)
          ? json(detail)
          : json({ total: 1, open_count: 1, items: [item] }),
    );
    const user = userEvent.setup();
    render(<AdminSupport />);
    await user.click(await screen.findByRole("button", { name: "Open" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Message to the person"), "Hello");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    expect((await within(dialog).findByRole("alert")).textContent).toBe("Not now.");
    expect(
      (within(dialog).getByLabelText("Message to the person") as HTMLTextAreaElement).value,
    ).toBe("Hello");
  });

  it("shows a refusal to read the list", async () => {
    fetchMock.mockResolvedValue(json({ error: { code: "x", message: "No access." } }, false));
    render(<AdminSupport />);
    expect((await screen.findByRole("alert")).textContent).toBe("No access.");
  });
});
