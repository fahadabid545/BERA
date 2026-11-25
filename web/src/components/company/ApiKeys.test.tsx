import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiKeys } from "./ApiKeys";

const fetchMock = vi.fn();
const SCOPES = ["projects:read", "cvs:upload", "candidates:read"];
const key = (id: string, over: object = {}) => ({
  id,
  name: "Fake key",
  last_four: "ab12",
  scopes: ["projects:read"],
  created_at: "2026-11-01T10:00:00Z",
  expires_at: null,
  revoked_at: null,
  last_used_at: "2026-11-20T10:00:00Z",
  request_count: 7,
  ...over,
});
const LISTING = {
  keys: [
    key("a"),
    key("b", { name: "Old", revoked_at: "2026-11-10T10:00:00Z" }),
    key("c", { name: "Lapsed", expires_at: "2020-01-01T00:00:00Z" }),
  ],
  scopes: SCOPES,
};
const reply = (status: number, body: unknown) =>
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
const rows = () =>
  Array.from(
    screen.getByRole("region", { name: "API keys" }).querySelectorAll<HTMLElement>("tbody tr"),
  );
const cells = (row: Element) =>
  Array.from(row.querySelectorAll("th, td")).map((cell) => cell.textContent);

async function show(listing: unknown = LISTING) {
  reply(200, listing);
  render(<ApiKeys />);
  await screen.findByRole("button", { name: "New key" });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("API keys", () => {
  it("lists name, scopes, dates, use and a status in words, never the key", async () => {
    await show();
    const listed = rows().map(cells);
    expect(listed[0].slice(0, 8)).toEqual([
      "Fake key",
      "ab12",
      "projects:read",
      "2026-11-01",
      "Never",
      "2026-11-20",
      "7",
      "Active",
    ]);
    expect(listed[1][7]).toBe("Revoked");
    expect(listed[2][7]).toBe("Expired");
  });

  it("offers Revoke only for keys that are not revoked", async () => {
    await show();
    expect(within(rows()[0]).getByRole("button", { name: "Revoke" })).toBeTruthy();
    expect(within(rows()[1]).queryByRole("button", { name: "Revoke" })).toBeNull();
  });

  it("says so when there are no keys", async () => {
    await show({ keys: [], scopes: SCOPES });
    expect(screen.getByText("No API keys.")).toBeTruthy();
  });

  it("makes a key with the chosen scopes and shows it once", async () => {
    const user = userEvent.setup();
    await show();
    await user.click(screen.getByRole("button", { name: "New key" }));
    const dialog = await screen.findByRole("dialog", { name: "New key" });
    await user.type(within(dialog).getByLabelText("Name"), "Fake name");
    await user.click(within(dialog).getByLabelText("projects:read"));
    await user.click(within(dialog).getByLabelText("candidates:read"));
    reply(201, { ...key("n", { name: "Fake name" }), key: "bera_live_FAKEKEYTEXT" });
    reply(200, LISTING);
    await user.click(within(dialog).getByRole("button", { name: "Create" }));

    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("/api/company/api-keys/");
    expect(JSON.parse(String(init.body))).toEqual({
      name: "Fake name",
      scopes: ["projects:read", "candidates:read"],
      expires_at: null,
    });
    const shown = await screen.findByRole("dialog", { name: "Your new key" });
    expect((within(shown).getByLabelText("Key") as HTMLInputElement).value).toBe(
      "bera_live_FAKEKEYTEXT",
    );
    await user.click(within(shown).getByRole("button", { name: "Close" }));
    expect(screen.queryByDisplayValue("bera_live_FAKEKEYTEXT")).toBeNull();
  });

  it("sends the chosen expiry as the end of that day", async () => {
    const user = userEvent.setup();
    await show();
    await user.click(screen.getByRole("button", { name: "New key" }));
    const dialog = await screen.findByRole("dialog", { name: "New key" });
    await user.type(within(dialog).getByLabelText("Name"), "Fake name");
    await user.click(within(dialog).getByLabelText("cvs:upload"));
    await user.type(within(dialog).getByLabelText("Expires on"), "2030-01-31");
    reply(201, { ...key("n"), key: "bera_live_X" });
    reply(200, LISTING);
    await user.click(within(dialog).getByRole("button", { name: "Create" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const body = JSON.parse(String((fetchMock.mock.calls[1] as [string, RequestInit])[1].body));
    expect(body.expires_at).toBe("2030-01-31T23:59:59Z");
  });

  it("comes back with what was typed and the reasons when the key is refused", async () => {
    const user = userEvent.setup();
    await show();
    await user.click(screen.getByRole("button", { name: "New key" }));
    const dialog = await screen.findByRole("dialog", { name: "New key" });
    await user.type(within(dialog).getByLabelText("Name"), "Fake name");
    reply(400, {
      error: {
        code: "validation_error",
        message: "Please check the form and try again.",
        fields: { scopes: "This list may not be empty." },
      },
    });
    await user.click(within(dialog).getByRole("button", { name: "Create" }));
    const again = await screen.findByRole("dialog", { name: "New key" });
    expect((within(again).getByLabelText("Name") as HTMLInputElement).value).toBe("Fake name");
    expect(within(again).getByText("This list may not be empty.")).toBeTruthy();
    expect(screen.queryByRole("dialog", { name: "Your new key" })).toBeNull();
  });

  it("revokes a key after a confirmation, then loads the list again", async () => {
    const user = userEvent.setup();
    await show();
    await user.click(within(rows()[0]).getByRole("button", { name: "Revoke" }));
    const dialog = await screen.findByRole("dialog", { name: "Revoke Fake key" });
    reply(200, key("a", { revoked_at: "2026-11-25T10:00:00Z" }));
    reply(200, LISTING);
    await user.click(within(dialog).getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(String(fetchMock.mock.calls[1][0])).toBe("/api/company/api-keys/a/revoke/");
  });

  it("revokes nothing when cancelled", async () => {
    const user = userEvent.setup();
    await show();
    await user.click(within(rows()[0]).getByRole("button", { name: "Revoke" }));
    const dialog = await screen.findByRole("dialog", { name: "Revoke Fake key" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows a failed load in plain words", async () => {
    reply(403, {
      error: { code: "not_allowed", message: "You do not have permission to do this." },
    });
    render(<ApiKeys />);
    expect((await screen.findByRole("alert")).textContent).toBe(
      "You do not have permission to do this.",
    );
  });
});
