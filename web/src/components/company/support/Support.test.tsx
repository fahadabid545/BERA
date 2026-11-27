import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SupportChat } from "./SupportChat";
import { SupportPage } from "./SupportPage";
import { TicketList } from "./TicketList";
import { TicketView } from "./TicketView";
import type { TicketDetail, TicketSummary } from "./words";

let search = "";
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/company/support",
  useSearchParams: () => new URLSearchParams(search),
}));

const fetchMock = vi.fn();
beforeEach(() => {
  search = "";
  replace.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const json = (body: unknown, ok = true) => ({ ok, status: ok ? 200 : 409, json: async () => body });

const summary: TicketSummary = {
  id: "t1",
  number: 7,
  title: "Cannot upload a CV",
  category: "bug",
  status: "open",
  created_at: "2026-11-20T10:00:00Z",
  updated_at: "2026-11-21T10:00:00Z",
};
const detail: TicketDetail = {
  ...summary,
  summary: "The person cannot upload a CV.",
  what_happened: "The upload button does nothing.",
  expected: "The CV is added.",
  steps: "Press Upload.",
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

async function write(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(screen.getByLabelText("Describe your problem"), text);
  await user.click(screen.getByRole("button", { name: "Send" }));
}

describe("SupportChat", () => {
  it("shows what the person wrote and the agent's answer, and keeps the chat going", async () => {
    fetchMock.mockResolvedValue(json({ chat_id: "c1", reply: "Try refreshing.", ticket: null }));
    const user = userEvent.setup();
    render(<SupportChat />);
    await write(user, "It is broken");
    expect(await screen.findByText("Try refreshing.")).toBeTruthy();
    expect(screen.getByText("It is broken")).toBeTruthy();
    await write(user, "Still broken");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ text: "It is broken" });
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      text: "Still broken",
      chat_id: "c1",
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("cannot send an empty message", async () => {
    render(<SupportChat />);
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows a popup with the requested ticket when the agent hands the problem over", async () => {
    fetchMock.mockResolvedValue(json({ chat_id: "c1", reply: "I told the team.", ticket: detail }));
    const user = userEvent.setup();
    render(<SupportChat />);
    await write(user, "Cannot upload");
    const dialog = await screen.findByRole("dialog", { name: "Support ticket requested" });
    expect(within(dialog).getByText("SUP-7")).toBeTruthy();
    expect(within(dialog).getByText("Cannot upload a CV")).toBeTruthy();
    expect(within(dialog).getByText("Open")).toBeTruthy();
    expect(within(dialog).getByText("The upload button does nothing.")).toBeTruthy();
    expect(within(dialog).getByText("Steps to repeat it")).toBeTruthy();
    expect(
      within(dialog).getByRole("link", { name: "View ticket SUP-7" }).getAttribute("href"),
    ).toBe("/company/support/t1");
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByLabelText("Describe your problem")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Start a new chat" }));
    expect(screen.getByLabelText("Describe your problem")).toBeTruthy();
    expect(screen.queryByText("I told the team.")).toBeNull();
  });

  it("shows the server's message when it cannot be sent", async () => {
    fetchMock.mockResolvedValue(json({ error: { code: "x", message: "Try later." } }, false));
    const user = userEvent.setup();
    render(<SupportChat />);
    await write(user, "hello");
    expect((await screen.findByRole("alert")).textContent).toBe("Try later.");
    expect((screen.getByLabelText("Describe your problem") as HTMLTextAreaElement).value).toBe(
      "hello",
    );
  });
});

describe("TicketList", () => {
  it("lists the tickets with their status in words", async () => {
    fetchMock.mockResolvedValue(
      json({ tickets: [summary, { ...summary, id: "t2", number: 8, status: "needs_reply" }] }),
    );
    render(<TicketList />);
    expect(await screen.findByText("SUP-7")).toBeTruthy();
    expect(screen.getByText("Open")).toBeTruthy();
    expect(screen.getByText("Waiting for your reply")).toBeTruthy();
    expect(
      screen.getAllByRole("link", { name: "Cannot upload a CV" })[0].getAttribute("href"),
    ).toBe("/company/support/t1");
  });

  it("says so when there are none, and when it cannot be read", async () => {
    fetchMock.mockResolvedValue(json({ tickets: [] }));
    render(<TicketList />);
    expect(await screen.findByText("No tickets yet.")).toBeTruthy();
    cleanup();
    fetchMock.mockResolvedValue(json({ error: { code: "x", message: "No." } }, false));
    render(<TicketList />);
    expect((await screen.findByRole("alert")).textContent).toBe("No.");
  });
});

describe("TicketView", () => {
  it("shows the ticket's parts and the conversation with the team", async () => {
    fetchMock.mockResolvedValue(json({ ...detail, status: "needs_reply" }));
    render(<TicketView id="t1" />);
    expect(await screen.findByText("The upload button does nothing.")).toBeTruthy();
    expect(screen.getByText("Press Upload.")).toBeTruthy();
    expect(screen.getByText("Which browser?")).toBeTruthy();
    expect(screen.getByText(/Support team/)).toBeTruthy();
    expect(screen.getAllByText("Waiting for your reply").length).toBeGreaterThan(0);
  });

  it("sends a reply and shows the updated ticket", async () => {
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
      init?.method === "POST"
        ? json({
            ...detail,
            status: "working",
            messages: [
              ...detail.messages,
              { id: "m3", author: "user", text: "Firefox", created_at: "2026-11-21T09:05:00Z" },
            ],
          })
        : json(detail),
    );
    const user = userEvent.setup();
    render(<TicketView id="t1" />);
    await user.type(await screen.findByLabelText("Your reply"), "Firefox");
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    expect(await screen.findByText("Firefox")).toBeTruthy();
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(call?.[0]).toBe("/api/company/support/tickets/t1/");
    expect(JSON.parse(call?.[1].body)).toEqual({ text: "Firefox" });
    expect(screen.getByText("Working on it")).toBeTruthy();
    expect((screen.getByLabelText("Your reply") as HTMLTextAreaElement).value).toBe("");
  });

  it("takes no reply once the ticket is closed", async () => {
    fetchMock.mockResolvedValue(json({ ...detail, status: "closed" }));
    render(<TicketView id="t1" />);
    expect(await screen.findByText("Closed")).toBeTruthy();
    expect(screen.queryByLabelText("Your reply")).toBeNull();
  });

  it("says plainly when the ticket cannot be found", async () => {
    fetchMock.mockResolvedValue(
      json({ error: { code: "not_found", message: "Not found." } }, false),
    );
    render(<TicketView id="nope" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Not found.");
  });
});

describe("SupportPage", () => {
  it("has the chat and the tickets as tabs, kept in the address", async () => {
    fetchMock.mockResolvedValue(json({ tickets: [] }));
    const user = userEvent.setup();
    render(<SupportPage />);
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "Ask support",
      "My tickets",
    ]);
    expect(screen.getByLabelText("Describe your problem")).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "My tickets" }));
    expect(replace).toHaveBeenCalledWith("/company/support?tab=tickets", { scroll: false });
  });
});
