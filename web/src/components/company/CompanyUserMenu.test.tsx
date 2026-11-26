import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CompanyUserMenu } from "./CompanyUserMenu";

const logOut = vi.fn();
vi.mock("@/lib/logout", () => ({ logOut: () => logOut() }));
const fetchMock = vi.fn();
vi.mock("next/navigation", () => ({ usePathname: () => "/company/projects/example" }));

const reply = (status: number, body: unknown) =>
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
const sentBody = () => JSON.parse(String((fetchMock.mock.calls.at(-1)?.[1] as RequestInit).body));

async function openForm() {
  const user = userEvent.setup();
  render(<CompanyUserMenu userName="Fake Person" />);
  await user.click(screen.getByRole("button", { name: "User menu" }));
  await user.click(screen.getByRole("menuitem", { name: "Send feedback" }));
  return { user, dialog: await screen.findByRole("dialog", { name: "Send feedback" }) };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Send feedback", () => {
  it("is in the user menu for everyone, next to Profile and Log out", async () => {
    const user = userEvent.setup();
    render(<CompanyUserMenu userName="Fake Person" />);
    await user.click(screen.getByRole("button", { name: "User menu" }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "Profile",
      "Send feedback",
      "Log out",
    ]);
  });

  it("sends the kind, the message and the page it was sent from, then says it was sent", async () => {
    const { user, dialog } = await openForm();
    await user.selectOptions(within(dialog).getByLabelText("Kind"), "idea");
    await user.type(within(dialog).getByLabelText("Message"), "Fake idea");
    reply(201, {});
    await user.click(within(dialog).getByRole("button", { name: "Send" }));

    expect(sentBody()).toEqual({
      kind: "idea",
      message: "Fake idea",
      page: "/company/projects/example",
    });
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/company/feedback/");
    expect(await screen.findByRole("dialog", { name: "Feedback sent" })).toBeTruthy();
  });

  it("starts with an empty message each time", async () => {
    const { user, dialog } = await openForm();
    await user.type(within(dialog).getByLabelText("Message"), "Fake text");
    reply(201, {});
    await user.click(within(dialog).getByRole("button", { name: "Send" }));
    await user.click(await screen.findByRole("button", { name: "Close" }));

    await user.click(screen.getByRole("button", { name: "User menu" }));
    await user.click(screen.getByRole("menuitem", { name: "Send feedback" }));
    const again = await screen.findByRole("dialog", { name: "Send feedback" });
    expect((within(again).getByLabelText("Message") as HTMLTextAreaElement).value).toBe("");
  });

  it("comes back with what was typed and the reason when the message is refused", async () => {
    const { user, dialog } = await openForm();
    await user.type(within(dialog).getByLabelText("Message"), "Fake text");
    reply(400, {
      error: { code: "invalid", message: "Check the form.", fields: { message: "Enter text." } },
    });
    await user.click(within(dialog).getByRole("button", { name: "Send" }));

    const again = await screen.findByRole("dialog", { name: "Send feedback" });
    expect((within(again).getByLabelText("Message") as HTMLTextAreaElement).value).toBe(
      "Fake text",
    );
    expect(within(again).getByText("Enter text.")).toBeTruthy();
    expect(screen.queryByRole("dialog", { name: "Feedback sent" })).toBeNull();
  });

  it("shows the wait in plain words when too much was sent", async () => {
    const { user, dialog } = await openForm();
    await user.type(within(dialog).getByLabelText("Message"), "Fake text");
    reply(429, {
      error: { code: "rate_limited", message: "Too many attempts. Try again in 5 minutes." },
    });
    await user.click(within(dialog).getByRole("button", { name: "Send" }));

    const again = await screen.findByRole("dialog", { name: "Send feedback" });
    expect(within(again).getByRole("alert").textContent).toBe(
      "Too many attempts. Try again in 5 minutes.",
    );
  });

  it("sends nothing when cancelled", async () => {
    const { user, dialog } = await openForm();
    await user.type(within(dialog).getByLabelText("Message"), "Fake text");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("beta feedback", () => {
  const usage = (kind: string | null) => ({
    free_access: kind ? { kind, ends_at: "2030-03-01T00:00:00Z" } : null,
  });
  const serve = (kind: string | null) =>
    fetchMock.mockImplementation(async (path: string) => ({
      ok: true,
      status: path === "/api/company/usage/" ? 200 : 201,
      json: async () => (path === "/api/company/usage/" ? usage(kind) : {}),
    }));
  const posts = () => fetchMock.mock.calls.filter((call) => call[1]?.method === "POST");

  beforeEach(() => {
    window.localStorage.clear();
    logOut.mockReset();
  });

  it("is offered to a beta tester on the first visit of the day, and only then", async () => {
    serve("beta");
    render(<CompanyUserMenu userName="Fake Person" role="owner" />);
    expect(await screen.findByRole("dialog", { name: "Beta feedback" })).toBeTruthy();
    cleanup();
    render(<CompanyUserMenu userName="Fake Person" role="owner" />);
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(1));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("is not offered to a company that is not on beta, or to a member", async () => {
    serve("permitted");
    render(<CompanyUserMenu userName="Fake Person" role="owner" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).toBeNull();
    cleanup();
    fetchMock.mockClear();
    serve("beta");
    render(<CompanyUserMenu userName="Fake Person" role="member" />);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("asks a beta tester for feedback before logging out, and logs out once it is sent", async () => {
    window.localStorage.setItem("bera-beta-feedback-day", new Date().toISOString().slice(0, 10));
    serve("beta");
    const user = userEvent.setup();
    render(<CompanyUserMenu userName="Fake Person" role="owner" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "User menu" }));
    await user.click(screen.getByRole("menuitem", { name: "Log out" }));
    const dialog = await screen.findByRole("dialog", { name: "Before you leave" });
    expect(logOut).not.toHaveBeenCalled();
    await user.type(within(dialog).getByLabelText("Message"), "Works well");
    await user.click(within(dialog).getByRole("button", { name: "Send" }));
    await waitFor(() => expect(logOut).toHaveBeenCalledTimes(1));
    expect(posts()).toHaveLength(1);
  });

  it("logs out without feedback when asked to, and stays signed in when the popup is closed", async () => {
    window.localStorage.setItem("bera-beta-feedback-day", new Date().toISOString().slice(0, 10));
    serve("beta");
    const user = userEvent.setup();
    render(<CompanyUserMenu userName="Fake Person" role="owner" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "User menu" }));
    await user.click(screen.getByRole("menuitem", { name: "Log out" }));
    await user.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(logOut).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "User menu" }));
    await user.click(screen.getByRole("menuitem", { name: "Log out" }));
    await user.click(await screen.findByRole("button", { name: "Log out without feedback" }));
    expect(logOut).toHaveBeenCalledTimes(1);
    expect(posts()).toHaveLength(0);
  });

  it("logs a company that is not on beta out at once", async () => {
    serve(null);
    const user = userEvent.setup();
    render(<CompanyUserMenu userName="Fake Person" role="owner" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "User menu" }));
    await user.click(screen.getByRole("menuitem", { name: "Log out" }));
    expect(logOut).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
