import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatLauncher, ChatSearchBar } from "./ChatEntryPoints";
import { ChatProvider } from "./ChatProvider";

const pathname = vi.hoisted(() => ({ current: "/" }));
vi.mock("next/navigation", () => ({ usePathname: () => pathname.current }));

const fetchMock = vi.fn();
const ON = {
  enabled: true,
  max_question_length: 300,
  max_history_messages: 4,
  history_hours: 2,
  max_saved_chats: 20,
};
let status: unknown = ON;
let answers: Array<unknown> = [];

function reply(body: unknown, ok = true, code = 200) {
  return { ok, status: code, json: async () => body };
}

beforeEach(() => {
  pathname.current = "/";
  status = ON;
  answers = [];
  window.localStorage.clear();
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string) => {
    if (url === "/api/chatbot/status/") return reply(status);
    const next = answers.shift() ?? { answer: "Plans are billed monthly." };
    if ((next as { error?: unknown }).error) return reply(next, false, 503);
    return reply(next);
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function page() {
  return render(
    <ChatProvider>
      <ChatSearchBar />
      <ChatLauncher />
    </ChatProvider>,
  );
}

function asked() {
  return fetchMock.mock.calls
    .filter(([url]) => url === "/api/chatbot/ask/")
    .map(([, init]) => JSON.parse(init.body));
}

async function askFromBar(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(await screen.findByLabelText("Ask a question"), text);
  await user.click(screen.getByRole("button", { name: "Ask" }));
  return screen.findByRole("dialog", { name: "Chat" });
}

describe("when the chat is off", () => {
  it("shows nothing when the server says it is off", async () => {
    status = { enabled: false };
    page();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByLabelText("Ask a question")).toBeNull();
    expect(screen.queryByRole("button", { name: "Chat" })).toBeNull();
  });

  it("shows nothing when the server cannot be reached", async () => {
    fetchMock.mockRejectedValue(new Error("down"));
    page();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByLabelText("Ask a question")).toBeNull();
  });
});

describe("the home page search bar", () => {
  it("opens the chat with the question and shows the answer as plain text", async () => {
    answers = [{ answer: "<b>Plans</b> are billed monthly." }];
    const user = userEvent.setup();
    page();
    const window_ = await askFromBar(user, "How are plans billed?");
    expect(await within(window_).findByText("<b>Plans</b> are billed monthly.")).toBeTruthy();
    // The question shows in the conversation and, as the chat's name, in the list.
    expect(within(window_).getAllByText("How are plans billed?")).toHaveLength(2);
    expect(asked()).toEqual([{ question: "How are plans billed?", history: [] }]);
    expect((screen.getByLabelText("Ask a question") as HTMLInputElement).value).toBe("");
  });

  it("cannot send an empty question and limits the length", async () => {
    const user = userEvent.setup();
    page();
    const input = (await screen.findByLabelText("Ask a question")) as HTMLInputElement;
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
    await user.type(input, "   ");
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
    expect(input.maxLength).toBe(300);
  });

  it("is not on pages other than the home page, where the Chat button is", async () => {
    pathname.current = "/pricing";
    const user = userEvent.setup();
    page();
    const button = await screen.findByRole("button", { name: "Chat" });
    await user.click(button);
    const dialog = await screen.findByRole("dialog", { name: "Chat" });
    expect(within(dialog).queryByText(/billed/)).toBeNull();
    expect(asked()).toEqual([]);
  });

  it("hides the Chat button on the home page", async () => {
    page();
    await screen.findByLabelText("Ask a question");
    expect(screen.queryByRole("button", { name: "Chat" })).toBeNull();
  });
});

describe("a conversation", () => {
  it("sends only the last messages as history and keeps the chat in the sidebar", async () => {
    answers = [{ answer: "One." }, { answer: "Two." }, { answer: "Three." }];
    const user = userEvent.setup();
    page();
    const dialog = await askFromBar(user, "Q1");
    await within(dialog).findByText("One.");
    const box = within(dialog).getByLabelText("Message");
    for (const [index, text] of ["Q2", "Q3"].entries()) {
      await user.type(box, text);
      await user.click(within(dialog).getByRole("button", { name: "Send" }));
      await within(dialog).findByText(["Two.", "Three."][index]);
    }
    const sent = asked();
    expect(sent[1]).toEqual({
      question: "Q2",
      history: [
        { role: "user", text: "Q1" },
        { role: "assistant", text: "One." },
      ],
    });
    // max_history_messages is 4: only the last four earlier messages go.
    expect(sent[2].history).toHaveLength(4);
    expect(sent[2].history[0]).toEqual({ role: "user", text: "Q1" });
    const chats = within(dialog).getByRole("list");
    expect(within(chats).getAllByRole("listitem")).toHaveLength(1);
    expect(within(chats).getByRole("button", { name: "Q1" })).toBeTruthy();
  });

  it("sends no history at all when the server allows none", async () => {
    status = { ...ON, max_history_messages: 0 };
    const user = userEvent.setup();
    page();
    const dialog = await askFromBar(user, "Q1");
    await within(dialog).findByText("Plans are billed monthly.");
    await user.type(within(dialog).getByLabelText("Message"), "Q2");
    await user.click(within(dialog).getByRole("button", { name: "Send" }));
    await waitFor(() => expect(asked()).toHaveLength(2));
    expect(asked()[1].history).toEqual([]);
  });

  it("starts a new chat and goes back to an earlier one", async () => {
    answers = [{ answer: "First answer." }, { answer: "Second answer." }];
    const user = userEvent.setup();
    page();
    const dialog = await askFromBar(user, "First question");
    await within(dialog).findByText("First answer.");
    await user.click(within(dialog).getByRole("button", { name: "New chat" }));
    expect(within(dialog).queryByText("First answer.")).toBeNull();
    await user.type(within(dialog).getByLabelText("Message"), "Other question");
    await user.click(within(dialog).getByRole("button", { name: "Send" }));
    await within(dialog).findByText("Second answer.");
    expect(asked()[1].history).toEqual([]); // a new chat carries nothing over
    const list = within(dialog).getByRole("list");
    expect(within(list).getAllByRole("button")).toHaveLength(2);
    await user.click(within(list).getByRole("button", { name: "First question" }));
    expect(within(dialog).getByText("First answer.")).toBeTruthy();
    expect(within(dialog).queryByText("Second answer.")).toBeNull();
    expect(
      within(list).getByRole("button", { name: "First question" }).getAttribute("aria-current"),
    ).toBe("true");
  });

  it("shows the server's message when it cannot answer and keeps the question", async () => {
    answers = [{ error: { code: "chatbot_unavailable", message: "The chat is not available." } }];
    const user = userEvent.setup();
    page();
    const dialog = await askFromBar(user, "Hello there");
    expect((await within(dialog).findByRole("alert")).textContent).toBe(
      "The chat is not available.",
    );
    expect(within(dialog).getAllByText("Hello there")).toHaveLength(2);
  });

  it("disables sending while an answer is awaited", async () => {
    let finish: (value: unknown) => void = () => {};
    fetchMock.mockImplementation(async (url: string) => {
      if (url === "/api/chatbot/status/") return reply(status);
      await new Promise((resolve) => (finish = resolve));
      return reply({ answer: "Done." });
    });
    const user = userEvent.setup();
    page();
    const dialog = await askFromBar(user, "Slow one");
    expect(await within(dialog).findByText("Thinking")).toBeTruthy();
    await user.type(within(dialog).getByLabelText("Message"), "More");
    expect(
      (within(dialog).getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    finish(null);
    await within(dialog).findByText("Done.");
    expect(within(dialog).queryByText("Thinking")).toBeNull();
  });
});

describe("history in the browser", () => {
  const KEY = "public-chat-history";

  it("keeps the chat for the next visit", async () => {
    const user = userEvent.setup();
    const first = page();
    const dialog = await askFromBar(user, "Remember me");
    await within(dialog).findByText("Plans are billed monthly.");
    first.unmount();
    expect(Object.keys(window.localStorage)).toEqual([KEY]);

    pathname.current = "/pricing";
    page();
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    const list = within(await screen.findByRole("dialog", { name: "Chat" })).getByRole("list");
    await user.click(within(list).getByRole("button", { name: "Remember me" }));
    expect(screen.getByText("Plans are billed monthly.")).toBeTruthy();
  });

  it("drops chats older than the hours the server allows", async () => {
    const old = Date.now() - 3 * 3_600_000;
    window.localStorage.setItem(
      KEY,
      JSON.stringify([{ id: "old", updatedAt: old, messages: [{ role: "user", text: "Stale" }] }]),
    );
    pathname.current = "/pricing";
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    const dialog = await screen.findByRole("dialog", { name: "Chat" });
    expect(within(dialog).queryByText("Stale")).toBeNull();
  });

  it("keeps no more chats than the server allows", async () => {
    status = { ...ON, max_saved_chats: 1 };
    answers = [{ answer: "A." }, { answer: "B." }];
    const user = userEvent.setup();
    page();
    const dialog = await askFromBar(user, "First");
    await within(dialog).findByText("A.");
    await user.click(within(dialog).getByRole("button", { name: "New chat" }));
    await user.type(within(dialog).getByLabelText("Message"), "Second");
    await user.click(within(dialog).getByRole("button", { name: "Send" }));
    await within(dialog).findByText("B.");
    expect(JSON.parse(window.localStorage.getItem(KEY) ?? "[]")).toHaveLength(1);
  });

  it("still answers when the browser blocks storage", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const user = userEvent.setup();
    page();
    const dialog = await askFromBar(user, "Works anyway");
    expect(await within(dialog).findByText("Plans are billed monthly.")).toBeTruthy();
  });
});

describe("the window", () => {
  it("closes with Escape and with the Close button", async () => {
    const user = userEvent.setup();
    page();
    await askFromBar(user, "Hello");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.type(screen.getByLabelText("Ask a question"), "Again");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await user.click(await screen.findByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps the keyboard focus inside while it is open", async () => {
    const user = userEvent.setup();
    page();
    const dialog = await askFromBar(user, "Hello");
    await within(dialog).findByText("Plans are billed monthly.");
    for (let press = 0; press < 12; press += 1) {
      await user.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
  });
});
