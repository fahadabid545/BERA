import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmEmailChange } from "./ConfirmEmailChange";

const fetchMock = vi.fn();
const reply = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
});

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("confirming a new email address", () => {
  it("changes nothing until the button is pressed", () => {
    render(<ConfirmEmailChange token="t1" />);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Confirm email address" })).toBeTruthy();
  });

  it("sends the token and says the address was changed", async () => {
    fetchMock.mockResolvedValue(reply({ status: "changed" }));
    render(<ConfirmEmailChange token="t1" />);
    await userEvent.click(screen.getByRole("button", { name: "Confirm email address" }));
    expect((await screen.findByRole("status")).textContent).toContain("was changed");
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/auth/company/confirm-email-change/");
    expect(JSON.parse(init.body)).toEqual({ token: "t1" });
    expect(screen.getByRole("link", { name: "Log in" })).toBeTruthy();
  });

  it("shows the server's message for a link that cannot be used", async () => {
    fetchMock.mockResolvedValue(
      reply({ error: { code: "link_used", message: "This link has already been used." } }, 400),
    );
    render(<ConfirmEmailChange token="t1" />);
    await userEvent.click(screen.getByRole("button", { name: "Confirm email address" }));
    expect((await screen.findByRole("alert")).textContent).toBe("This link has already been used.");
  });

  it("refuses a page opened without a token", () => {
    render(<ConfirmEmailChange token={null} />);
    expect(screen.getByRole("alert").textContent).toBe("This link is not valid.");
    expect(screen.queryByRole("button")).toBeNull();
  });
});
