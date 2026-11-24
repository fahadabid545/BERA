import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminDataRequests } from "./AdminDataRequests";

const fetchMock = vi.fn();
const request = (id: number, over: object = {}) => ({
  id,
  company_id: 1,
  company: "Fake Company",
  company_exists: true,
  kind: "export",
  requested_by: "Fake Requester",
  received_on: "2026-11-01",
  due_on: "2026-12-01",
  status: "open",
  completed_on: null,
  note: "Fake note",
  overdue: false,
  ...over,
});
const LISTING = {
  total: 3,
  items: [
    request(1, { kind: "deletion", due_on: "2026-10-01", overdue: true }),
    request(2, { status: "in_progress" }),
    request(3, { status: "completed", completed_on: "2026-11-10", company_exists: false }),
  ],
  companies: [{ id: 1, name: "Fake Company" }],
};
const reply = (status: number, body: unknown) =>
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
const rows = () =>
  Array.from(screen.getByRole("region", { name: "Data requests" }).querySelectorAll("tbody tr"));
const cells = (row: Element) =>
  Array.from(row.querySelectorAll("th, td")).map((cell) => cell.textContent);

async function show() {
  reply(200, LISTING);
  render(<AdminDataRequests />);
  await screen.findByRole("region", { name: "Data requests" });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Data requests", () => {
  it("lists company, type, status and due date, and marks an overdue request in words", async () => {
    await show();
    const listed = rows().map(cells);
    expect([listed[0][0], listed[0][1], listed[0][4], listed[0][5]]).toEqual([
      "Fake Company",
      "Deletion",
      "2026-10-01 Overdue",
      "Open",
    ]);
    expect(listed[1][4]).toBe("2026-12-01 ");
    expect(listed[1][5]).toBe("In progress");
    expect(listed[2][5]).toBe("Completed");
    expect(screen.getByText("Showing 3 of 3")).toBeTruthy();
  });

  it("links a company that exists and shows only the name of one that was deleted", async () => {
    await show();
    expect(
      within(rows()[0] as HTMLElement)
        .getByRole("link")
        .getAttribute("href"),
    ).toBe("/admin/companies/1");
    expect(within(rows()[2] as HTMLElement).queryByRole("link")).toBeNull();
  });

  it("shows No data requests when there are none", async () => {
    reply(200, { total: 0, items: [], companies: [] });
    render(<AdminDataRequests />);
    expect(await screen.findByText("No data requests.")).toBeTruthy();
  });

  it("filters by status", async () => {
    await show();
    reply(200, LISTING);
    await userEvent.selectOptions(screen.getByLabelText("Status"), "completed");
    await waitFor(() =>
      expect(String(fetchMock.mock.calls.at(-1)?.[0])).toBe(
        "/api/admin/data-requests/?status=completed",
      ),
    );
  });

  it("logs a new request", async () => {
    await show();
    await userEvent.click(screen.getByRole("button", { name: "New request" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.selectOptions(within(dialog).getByLabelText("Company"), "1");
    await userEvent.selectOptions(within(dialog).getByLabelText("Type"), "deletion");
    await userEvent.type(within(dialog).getByLabelText("Requested by"), "Fake Requester");
    reply(201, LISTING);
    reply(200, LISTING);
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [path, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect([path, init.method]).toEqual(["/api/admin/data-requests/", "POST"]);
    expect(JSON.parse(String(init.body))).toMatchObject({
      company: 1,
      kind: "deletion",
      requested_by: "Fake Requester",
    });
  });

  it("brings the form back with the server's messages when it is refused", async () => {
    await show();
    await userEvent.click(screen.getByRole("button", { name: "New request" }));
    reply(400, {
      error: {
        code: "validation_error",
        message: "Please check the form and try again.",
        fields: { company: "Choose a company from the list." },
      },
    });
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Choose a company from the list.")).toBeTruthy();
  });

  it("offers only the current and later statuses when updating", async () => {
    await show();
    await userEvent.click(within(rows()[1] as HTMLElement).getByRole("button", { name: "Update" }));
    const options = within(screen.getByRole("dialog"))
      .getAllByRole("option")
      .map((option) => option.textContent);
    expect(options).toEqual(["In progress", "Completed"]);
  });

  it("completes a request", async () => {
    await show();
    await userEvent.click(within(rows()[0] as HTMLElement).getByRole("button", { name: "Update" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.selectOptions(within(dialog).getByLabelText("Status"), "completed");
    reply(200, LISTING);
    reply(200, LISTING);
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [path, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect([path, init.method]).toEqual(["/api/admin/data-requests/1/", "PATCH"]);
    expect(JSON.parse(String(init.body))).toEqual({ status: "completed", note: "Fake note" });
  });

  it("shows the server's message when the page cannot load", async () => {
    reply(403, {
      error: { code: "not_allowed", message: "You do not have permission to do this." },
    });
    render(<AdminDataRequests />);
    expect((await screen.findByRole("alert")).textContent).toBe(
      "You do not have permission to do this.",
    );
  });
});
