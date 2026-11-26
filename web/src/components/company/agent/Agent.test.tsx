import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgentBar } from "./AgentBar";
import { AGENT_SUGGESTIONS } from "./labels";
import { AgentProvider } from "./AgentProvider";

const fetchMock = vi.fn();
const CANDIDATE = "1a2b3c4d-0000-4000-8000-000000000001";
const OTHER = "9f8e7d6c-0000-4000-8000-000000000002";
const card = {
  candidate_id: CANDIDATE,
  project_id: "p1",
  project_title: "Designer",
  name: "Zed Quokka",
  email: "quokka@example.com",
  phone: "+1 555 010 4242",
  years_of_experience: 6,
  score: "90.0",
  grade: "A",
  label: "recommended",
  ats_score: 70,
  stage: "new",
};
const second = {
  ...card,
  candidate_id: OTHER,
  name: "Other Fake",
  email: "",
  phone: "",
  ats_score: null,
};

let chats: Array<{ id: string; title: string; updated_at: string; mine: boolean }> = [];
let answers: Array<unknown> = [];
let opened: Record<string, unknown> = {};

function reply(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body };
}

beforeEach(() => {
  chats = [];
  answers = [];
  opened = {};
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    if (url === "/api/company/assistant/chats/") return reply({ chats });
    if (url.startsWith("/api/company/assistant/chats/") && method === "DELETE") {
      const id = url.split("/")[5];
      chats = chats.filter((chat) => chat.id !== id);
      return reply({ deleted: true });
    }
    if (url.startsWith("/api/company/assistant/chats/")) {
      return reply(opened[url.split("/")[5]]);
    }
    if (url === "/api/company/assistant/ask/") {
      const next = answers.shift() as { error?: unknown } | undefined;
      if (next?.error) return reply(next, false, 409);
      return reply(
        next ?? {
          chat_id: "chat-1",
          answer: "Nothing to say.",
          refused: false,
          suggestions: [],
          candidates: [],
        },
      );
    }
    throw new Error(`unexpected ${method} ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function page() {
  return render(
    <AgentProvider>
      <AgentBar />
    </AgentProvider>,
  );
}

function asked() {
  return fetchMock.mock.calls
    .filter(([url, init]) => url === "/api/company/assistant/ask/" && init?.method === "POST")
    .map(([, init]) => JSON.parse(init.body));
}

async function ask(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(screen.getByLabelText("Ask a question"), text);
  await user.click(screen.getByRole("button", { name: "Ask" }));
  return screen.findByRole("dialog", { name: "Assistant" });
}

describe("the talk bar", () => {
  it("suggests a different question every few seconds while it is empty", () => {
    vi.useFakeTimers();
    try {
      page();
      const input = () => screen.getByLabelText("Ask a question") as HTMLInputElement;
      expect(input().placeholder).toBe(AGENT_SUGGESTIONS[0]);
      act(() => vi.advanceTimersByTime(4000));
      expect(input().placeholder).toBe(AGENT_SUGGESTIONS[1]);
      act(() => vi.advanceTimersByTime(4000 * AGENT_SUGGESTIONS.length));
      expect(input().placeholder).toBe(AGENT_SUGGESTIONS[1]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops changing the suggestion while something is typed", async () => {
    const user = userEvent.setup();
    page();
    const input = screen.getByLabelText("Ask a question") as HTMLInputElement;
    await user.type(input, "Hi");
    expect(input.value).toBe("Hi");
    expect(input.placeholder).toBe(AGENT_SUGGESTIONS[0]);
  });

  it("cannot send an empty question", async () => {
    const user = userEvent.setup();
    page();
    const button = screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    await user.type(screen.getByLabelText("Ask a question"), "   ");
    expect(button.disabled).toBe(true);
  });

  it("opens the window with the question and shows the candidate beside the answer", async () => {
    answers = [
      {
        chat_id: "chat-1",
        answer: "[c_1a2b3c4d] is best, then [c_9f8e7d6c]. [c_deadbeef] is gone.",
        refused: false,
        suggestions: ["More on the first?"],
        candidates: [card, second],
      },
    ];
    const user = userEvent.setup();
    page();
    const dialog = await ask(user, "Who is best?");
    const link = await within(dialog).findAllByRole("link", { name: "Zed Quokka" });
    expect(link[0].getAttribute("href")).toBe("/company/projects/p1/candidates/" + CANDIDATE);
    expect(within(dialog).getByText(/is gone/).textContent).toContain("A removed candidate");
    const details = within(dialog).getByRole("region", { name: "Zed Quokka" });
    for (const text of [
      "quokka@example.com",
      "+1 555 010 4242",
      "6",
      "90.0 (A)",
      "70",
      "new",
      "Designer",
    ]) {
      expect(within(details).getByText(text)).toBeTruthy();
    }
    const missing = within(dialog).getByRole("region", { name: "Other Fake" });
    expect(within(missing).getAllByText("Not available").length).toBe(3);
    expect(asked()).toEqual([{ question: "Who is best?", incognito: false }]);
    expect((screen.getByLabelText("Ask a question") as HTMLInputElement).value).toBe("");
  });

  it("shows the server's message when the company has not paid, and keeps the question", async () => {
    answers = [
      {
        error: {
          code: "agent_needs_plan",
          message: "Buy our service to continue. Contact support.",
        },
      },
    ];
    const user = userEvent.setup();
    page();
    const dialog = await ask(user, "Who is best?");
    expect(await within(dialog).findByText(/Buy our service to continue/)).toBeTruthy();
    expect(within(dialog).getAllByText("Who is best?").length).toBeGreaterThan(0);
  });
});

describe("a conversation", () => {
  it("continues the same chat and offers the follow-up suggestions of the last answer only", async () => {
    answers = [
      {
        chat_id: "chat-1",
        answer: "First.",
        refused: false,
        suggestions: ["Next best?"],
        candidates: [],
      },
      {
        chat_id: "chat-1",
        answer: "Second.",
        refused: false,
        suggestions: ["And then?"],
        candidates: [],
      },
    ];
    chats = [{ id: "chat-1", title: "Who is best?", updated_at: "now", mine: true }];
    const user = userEvent.setup();
    page();
    const dialog = await ask(user, "Who is best?");
    await user.click(await within(dialog).findByRole("button", { name: "Next best?" }));
    await within(dialog).findByText("Second.");
    expect(asked()[1]).toEqual({ question: "Next best?", incognito: false, chat_id: "chat-1" });
    expect(within(dialog).queryByRole("button", { name: "Next best?" })).toBeNull();
    expect(within(dialog).getByRole("button", { name: "And then?" })).toBeTruthy();
  });

  it("lists the company's chats, opens one and starts a new one", async () => {
    chats = [
      { id: "old-1", title: "Earlier question", updated_at: "x", mine: false },
      { id: "old-2", title: "Another one", updated_at: "y", mine: true },
    ];
    opened = {
      "old-1": {
        id: "old-1",
        title: "Earlier question",
        messages: [
          { role: "user", text: "Earlier question", suggestions: [], candidates: [] },
          {
            role: "assistant",
            text: "Earlier answer.",
            suggestions: ["Keep going?"],
            candidates: [],
          },
        ],
      },
    };
    const user = userEvent.setup();
    page();
    const dialog = await ask(user, "Fresh question");
    const list = await within(dialog).findByRole("list");
    await user.click(within(list).getByRole("button", { name: "Earlier question" }));
    expect(await within(dialog).findByText("Earlier answer.")).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "Keep going?" })).toBeTruthy();
    await user.type(within(dialog).getByLabelText("Message"), "Continue");
    await user.click(within(dialog).getByRole("button", { name: "Send" }));
    await waitFor(() => expect(asked()).toHaveLength(2));
    expect(asked()[1]).toEqual({ question: "Continue", incognito: false, chat_id: "old-1" });
    await user.click(within(dialog).getByRole("button", { name: "New chat" }));
    expect(within(dialog).queryByText("Earlier answer.")).toBeNull();
    await user.type(within(dialog).getByLabelText("Message"), "Brand new");
    await user.click(within(dialog).getByRole("button", { name: "Send" }));
    await waitFor(() => expect(asked()).toHaveLength(3));
    expect(asked()[2]).toEqual({ question: "Brand new", incognito: false });
  });

  it("asks before deleting a chat, then removes it", async () => {
    chats = [{ id: "old-1", title: "Earlier question", updated_at: "x", mine: false }];
    const user = userEvent.setup();
    page();
    const dialog = await ask(user, "Fresh question");
    await user.click(
      await within(dialog).findByRole("button", { name: "Delete Earlier question" }),
    );
    const popup = await screen.findByRole("dialog", { name: "Delete this chat?" });
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Delete this chat?" })).toBeNull();
    expect(screen.getByRole("dialog", { name: "Assistant" })).toBeTruthy();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
    expect(popup).toBeTruthy();

    await user.click(within(dialog).getByRole("button", { name: "Delete Earlier question" }));
    const again = await screen.findByRole("dialog", { name: "Delete this chat?" });
    await user.click(within(again).getByRole("button", { name: "Delete chat" }));
    await waitFor(() =>
      expect(within(dialog).queryByRole("button", { name: "Earlier question" })).toBeNull(),
    );
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) => url === "/api/company/assistant/chats/old-1/" && init?.method === "DELETE",
      ),
    ).toBe(true);
  });
});

describe("incognito", () => {
  it("brings its own history, saves nothing and adds no chat to the list", async () => {
    answers = [
      {
        chat_id: "chat-1",
        answer: "Nothing to say.",
        refused: false,
        suggestions: [],
        candidates: [],
      },
      { chat_id: null, answer: "Hidden one.", refused: false, suggestions: [], candidates: [card] },
      { chat_id: null, answer: "Hidden two.", refused: false, suggestions: [], candidates: [] },
    ];
    const user = userEvent.setup();
    page();
    const dialog = await ask(user, "Normal first");
    await within(dialog).findByText("Nothing to say.");
    await user.click(within(dialog).getByRole("button", { name: "Incognito chat" }));
    const toggle = within(dialog).getByRole("button", { name: "Incognito on" });
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    expect(within(dialog).queryByText("Nothing to say.")).toBeNull();

    await user.type(within(dialog).getByLabelText("Message"), "Secret question");
    await user.click(within(dialog).getByRole("button", { name: "Send" }));
    await within(dialog).findByText("Hidden one.");
    await user.type(within(dialog).getByLabelText("Message"), "Secret follow-up");
    await user.click(within(dialog).getByRole("button", { name: "Send" }));
    await within(dialog).findByText("Hidden two.");

    expect(asked()[1]).toEqual({
      question: "Secret question",
      incognito: true,
      history: [],
      shown: [],
    });
    expect(asked()[2]).toEqual({
      question: "Secret follow-up",
      incognito: true,
      history: [
        { role: "user", text: "Secret question" },
        { role: "assistant", text: "Hidden one." },
      ],
      shown: [CANDIDATE],
    });
    const lists = fetchMock.mock.calls.filter(([url]) => url === "/api/company/assistant/chats/");
    expect(lists.length).toBeLessThanOrEqual(2); // on opening and after the one saved question

    await user.click(within(dialog).getByRole("button", { name: "Incognito on" }));
    expect(within(dialog).getByRole("button", { name: "Incognito chat" })).toBeTruthy();
    expect(within(dialog).queryByText("Hidden one.")).toBeNull();
  });
});

describe("the window", () => {
  it("closes with the Close button and with Escape", async () => {
    const user = userEvent.setup();
    page();
    await ask(user, "Hello");
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await ask(user, "Again");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
