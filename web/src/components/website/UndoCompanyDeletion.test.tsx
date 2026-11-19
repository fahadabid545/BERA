import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { UndoCompanyDeletion } from "./UndoCompanyDeletion";

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

describe("undoing the deletion of a company", () => {
  it("changes nothing until the button is pressed", () => {
    render(<UndoCompanyDeletion token="t1" />);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Undo the deletion" })).toBeTruthy();
  });

  it("sends the token and says the company will not be deleted", async () => {
    fetchMock.mockResolvedValue(reply({ status: "restored" }));
    render(<UndoCompanyDeletion token="t1" />);
    await userEvent.click(screen.getByRole("button", { name: "Undo the deletion" }));
    expect((await screen.findByRole("status")).textContent).toContain("will not be deleted");
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/auth/company/undo-deletion/");
    expect(JSON.parse(init.body)).toEqual({ token: "t1" });
    expect(screen.getByRole("link", { name: "Log in" })).toBeTruthy();
  });

  it("shows the server's reason when the link was used or has run out", async () => {
    fetchMock.mockResolvedValue(
      reply({ error: { code: "link_used", message: "This link has already been used." } }, 400),
    );
    render(<UndoCompanyDeletion token="t1" />);
    await userEvent.click(screen.getByRole("button", { name: "Undo the deletion" }));
    expect((await screen.findByRole("alert")).textContent).toBe("This link has already been used.");
  });

  it("refuses at once when there is no token", () => {
    render(<UndoCompanyDeletion token={null} />);
    expect(screen.getByRole("alert").textContent).toBe("This link is not valid.");
    expect(screen.queryByRole("button")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
