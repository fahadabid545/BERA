import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminSettingsTable, labelOf, type Setting } from "./AdminSettingsTable";

const fetchMock = vi.fn();
const setting = (key: string, over: Partial<Setting> = {}): Setting => ({
  key,
  group: key.split(".")[0],
  kind: "number",
  value: 10,
  default: 10,
  is_default: true,
  ...over,
});
const LISTING = {
  items: [
    setting("uploads.max_file_size_mb", { value: 20, is_default: false }),
    setting("uploads.allowed_file_types", {
      kind: "list",
      value: ["pdf", "docx"],
      default: ["pdf", "docx"],
    }),
    setting("passwords.block_common_passwords", { kind: "boolean", value: true, default: true }),
    setting("general.app_name", { kind: "text", value: "Bera", default: "Bera" }),
    setting("dashboard.period_choices_days", { kind: "list", value: [7, 30], default: [7, 30] }),
  ],
};
const reply = (status: number, body: unknown) =>
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
const rows = () =>
  Array.from(screen.getByRole("region", { name: "Settings" }).querySelectorAll("tbody tr"));
const rowOf = (name: string) =>
  rows().find((row) => row.querySelector("th")?.textContent === name) as HTMLElement;
const last = () => fetchMock.mock.calls.at(-1) as [string, RequestInit];

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("labelOf", () => {
  it("makes a setting's name readable", () => {
    expect(labelOf("uploads.max_file_size_mb")).toBe("Max file size mb");
  });
});

describe("Settings table", () => {
  it("lists each setting with its value and default, grouped, when no page is given", async () => {
    reply(200, LISTING);
    render(<AdminSettingsTable />);
    await screen.findByRole("region", { name: "Settings" });
    expect(cells(rowOf("Max file size mb"))).toEqual(["Uploads", "Max file size mb", "20", "10"]);
    expect(cells(rowOf("Block common passwords")).slice(2, 4)).toEqual(["On", "On"]);
    expect(cells(rowOf("Allowed file types")).slice(2, 4)).toEqual(["pdf, docx", "pdf, docx"]);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/admin/settings/");
  });

  it("asks only for its own page and shows no group column", async () => {
    reply(200, { items: [LISTING.items[3]] });
    render(<AdminSettingsTable page="general" />);
    await screen.findByRole("region", { name: "Settings" });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/admin/settings/?page=general");
    expect(screen.queryByRole("columnheader", { name: "Group" })).toBeNull();
  });

  it("filters by group", async () => {
    reply(200, LISTING);
    render(<AdminSettingsTable />);
    await screen.findByRole("region", { name: "Settings" });
    await userEvent.selectOptions(screen.getByLabelText("Group"), "passwords");
    expect(rows()).toHaveLength(1);
  });

  it("changes a number and sends it as a number", async () => {
    reply(200, LISTING);
    render(<AdminSettingsTable />);
    await screen.findByRole("region", { name: "Settings" });
    await userEvent.click(
      within(rowOf("Max file size mb")).getByRole("button", { name: "Change" }),
    );
    const field = screen.getByLabelText("Max file size mb");
    await userEvent.clear(field);
    await userEvent.type(field, "30");
    reply(200, LISTING);
    reply(200, LISTING);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [path, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect([path, init.method]).toEqual(["/api/admin/settings/", "PUT"]);
    expect(JSON.parse(String(init.body))).toEqual({ values: { "uploads.max_file_size_mb": 30 } });
  });

  it("sends a list as a list, and a numeric list as numbers", async () => {
    reply(200, LISTING);
    render(<AdminSettingsTable />);
    await screen.findByRole("region", { name: "Settings" });
    await userEvent.click(
      within(rowOf("Allowed file types")).getByRole("button", { name: "Change" }),
    );
    const field = screen.getByLabelText("Allowed file types");
    await userEvent.clear(field);
    await userEvent.type(field, "pdf, txt");
    reply(200, LISTING);
    reply(200, LISTING);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(JSON.parse(String(fetchMock.mock.calls[1][1].body)).values).toEqual({
      "uploads.allowed_file_types": ["pdf", "txt"],
    });

    await userEvent.click(
      within(rowOf("Period choices days")).getByRole("button", { name: "Change" }),
    );
    const numbers = screen.getByLabelText("Period choices days");
    await userEvent.clear(numbers);
    await userEvent.type(numbers, "7, 14");
    reply(200, LISTING);
    reply(200, LISTING);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
    expect(JSON.parse(String(fetchMock.mock.calls[3][1].body)).values).toEqual({
      "dashboard.period_choices_days": [7, 14],
    });
  });

  it("switches a yes-or-no setting", async () => {
    reply(200, LISTING);
    render(<AdminSettingsTable />);
    await screen.findByRole("region", { name: "Settings" });
    await userEvent.click(
      within(rowOf("Block common passwords")).getByRole("button", { name: "Change" }),
    );
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("checkbox"));
    reply(200, LISTING);
    reply(200, LISTING);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(JSON.parse(String(fetchMock.mock.calls[1][1].body)).values).toEqual({
      "passwords.block_common_passwords": false,
    });
  });

  it("brings the popup back with the server's message when a value is refused", async () => {
    reply(200, LISTING);
    render(<AdminSettingsTable />);
    await screen.findByRole("region", { name: "Settings" });
    await userEvent.click(
      within(rowOf("Max file size mb")).getByRole("button", { name: "Change" }),
    );
    reply(400, {
      error: {
        code: "validation_error",
        message: "Please check the form and try again.",
        fields: { "uploads.max_file_size_mb": "This value is not allowed." },
      },
    });
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("This value is not allowed.")).toBeTruthy();
    expect((screen.getByLabelText("Max file size mb") as HTMLInputElement).value).toBe("20");
  });

  it("asks in a popup before resetting, and only a changed value can be reset", async () => {
    reply(200, LISTING);
    render(<AdminSettingsTable />);
    await screen.findByRole("region", { name: "Settings" });
    expect(
      (within(rowOf("App name")).getByRole("button", { name: "Reset" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    await userEvent.click(within(rowOf("Max file size mb")).getByRole("button", { name: "Reset" }));
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await userEvent.click(within(rowOf("Max file size mb")).getByRole("button", { name: "Reset" }));
    reply(200, LISTING);
    reply(200, LISTING);
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Reset to default" }),
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [path, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect([path, init.method]).toEqual([
      "/api/admin/settings/uploads.max_file_size_mb/reset/",
      "POST",
    ]);
  });

  it("shows the server's message when the page cannot load", async () => {
    reply(403, {
      error: { code: "not_allowed", message: "You do not have permission to do this." },
    });
    render(<AdminSettingsTable />);
    expect((await screen.findByRole("alert")).textContent).toBe(
      "You do not have permission to do this.",
    );
    expect(last()[0]).toBe("/api/admin/settings/");
  });
});

function cells(row: Element) {
  return Array.from(row.querySelectorAll("th, td"))
    .map((cell) => cell.textContent)
    .slice(0, 4);
}
