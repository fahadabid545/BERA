import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminFeedback } from "./AdminFeedback";

const fetchMock = vi.fn();
const entry = (id: string, over: object = {}) => ({
  id,
  company_id: 1,
  company: "Fake Company",
  user: "Fake Person",
  kind: "bug",
  message: "Fake message",
  page: "/company/projects",
  status: "new",
  note: "",
  created_at: "2026-11-20T10:00:00Z",
  ...over,
});
const LISTING = {
  total: 3,
  items: [
    entry("a", { kind: "idea", message: "Fake idea" }),
    entry("b", { status: "reviewing", note: "Fake note" }),
    entry("c", { status: "wont_fix", kind: "question" }),
  ],
};
const reply = (status: number, body: unknown) =>
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
const rows = () =>
  Array.from(
    screen.getByRole("region", { name: "Feedback" }).querySelectorAll<HTMLElement>("tbody tr"),
  );
const cells = (row: Element) =>
  Array.from(row.querySelectorAll("th, td")).map((cell) => cell.textContent);
const lastUrl = () => String(fetchMock.mock.calls.at(-1)?.[0]);

async function show() {
  reply(200, LISTING);
  render(<AdminFeedback />);
  await screen.findByRole("region", { name: "Feedback" });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Feedback list", () => {
  it("lists company, user, kind, message, date and status in words", async () => {
    await show();
    const listed = rows().map(cells);
    expect(listed[0].slice(0, 6)).toEqual([
      "Fake Company",
      "Fake Person",
      "Idea",
      "Fake idea",
      "2026-11-20",
      "New",
    ]);
    expect(listed[1][5]).toBe("Reviewing");
    expect(listed[2][5]).toBe("Won't fix");
    expect(screen.getByText("Showing 3 of 3")).toBeTruthy();
  });

  it("links the company", async () => {
    await show();
    expect(within(rows()[0]).getByRole("link", { name: "Fake Company" }).getAttribute("href")).toBe(
      "/admin/companies/1",
    );
  });

  it("says so when there is none, and keeps the filters", async () => {
    reply(200, { total: 0, items: [] });
    render(<AdminFeedback />);
    expect(await screen.findByText("No feedback.")).toBeTruthy();
    expect(screen.getByLabelText("Status")).toBeTruthy();
  });

  it("asks the server for the chosen status, kind and dates", async () => {
    const user = userEvent.setup();
    await show();
    reply(200, LISTING);
    await user.selectOptions(screen.getByLabelText("Status"), "fixed");
    await waitFor(() => expect(lastUrl()).toBe("/api/admin/feedback/?status=fixed"));
    reply(200, LISTING);
    await user.selectOptions(screen.getByLabelText("Kind"), "idea");
    await waitFor(() => expect(lastUrl()).toBe("/api/admin/feedback/?status=fixed&kind=idea"));
    reply(200, LISTING);
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-11-01" } });
    await waitFor(() => expect(lastUrl()).toContain("since=2026-11-01"));
    reply(200, LISTING);
    fireEvent.change(screen.getByLabelText("Until"), { target: { value: "2026-11-30" } });
    await waitFor(() => expect(lastUrl()).toContain("until=2026-11-30"));
  });

  it("changes the status and the note in a popup, then loads the list again", async () => {
    const user = userEvent.setup();
    await show();
    await user.click(within(rows()[0]).getByRole("button", { name: "Update" }));
    const dialog = await screen.findByRole("dialog", { name: "Update feedback" });
    await user.selectOptions(within(dialog).getByLabelText("Status"), "fixed");
    await user.type(within(dialog).getByLabelText("Note"), "Fake internal note");
    reply(200, entry("a", { status: "fixed" }));
    reply(200, LISTING);
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("/api/admin/feedback/a/");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({
      status: "fixed",
      note: "Fake internal note",
    });
  });

  it("shows the current note and status when opening the popup", async () => {
    const user = userEvent.setup();
    await show();
    await user.click(within(rows()[1]).getByRole("button", { name: "Update" }));
    const dialog = await screen.findByRole("dialog", { name: "Update feedback" });
    expect((within(dialog).getByLabelText("Status") as HTMLSelectElement).value).toBe("reviewing");
    expect((within(dialog).getByLabelText("Note") as HTMLTextAreaElement).value).toBe("Fake note");
  });

  it("comes back with the reason when a change is refused", async () => {
    const user = userEvent.setup();
    await show();
    await user.click(within(rows()[0]).getByRole("button", { name: "Update" }));
    const dialog = await screen.findByRole("dialog", { name: "Update feedback" });
    reply(400, {
      error: { code: "invalid", message: "Check the form.", fields: { note: "This is too long." } },
    });
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    const again = await screen.findByRole("dialog", { name: "Update feedback" });
    expect(within(again).getByText("This is too long.")).toBeTruthy();
  });

  it("shows a failed load in plain words", async () => {
    reply(500, { error: { code: "server_error", message: "Something went wrong." } });
    render(<AdminFeedback />);
    expect((await screen.findByRole("alert")).textContent).toBe("Something went wrong.");
  });
});
