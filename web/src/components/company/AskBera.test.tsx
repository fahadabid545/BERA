import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AskBera } from "./AskBera";

const fetchMock = vi.fn();
const URL = "/api/company/projects/p1/ask/";
const answer = {
  answer: "[C1] is the strongest, then [C2].",
  refused: false,
  candidates: [
    { reference: "C1", candidate_id: "c-one", initials: "Z. Q." },
    { reference: "C2", candidate_id: "c-two", initials: "A. B." },
  ],
};

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ask bar", () => {
  it("sends the question and shows the answer with candidates as links by initials", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => answer });
    const user = userEvent.setup();
    render(<AskBera projectId="p1" />);
    await user.type(screen.getByLabelText("Question"), "Who is best?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    const first = await screen.findByRole("link", { name: "Z. Q." });
    expect(first.getAttribute("href")).toBe("/company/projects/p1/candidates/c-one");
    expect(screen.getByRole("link", { name: "A. B." }).getAttribute("href")).toBe(
      "/company/projects/p1/candidates/c-two",
    );
    expect(screen.queryByText(/\[C1\]/)).toBeNull();
    const call = fetchMock.mock.calls[0];
    expect(call[0]).toBe(URL);
    expect(JSON.parse(call[1].body)).toEqual({ question: "Who is best?" });
  });

  it("cannot send an empty question", async () => {
    const user = userEvent.setup();
    render(<AskBera projectId="p1" />);
    const button = screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    await user.type(screen.getByLabelText("Question"), "   ");
    expect(button.disabled).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows a refusal as a plain answer", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ answer: "I can only read results.", refused: true, candidates: [] }),
    });
    const user = userEvent.setup();
    render(<AskBera projectId="p1" />);
    await user.type(screen.getByLabelText("Question"), "Delete the weakest");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("I can only read results.")).toBeTruthy();
  });

  it("shows the server's plain message when it is refused or the AI is down", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({
        error: {
          code: "ai_paused_token_cap",
          message: "Your company has used all its AI allowance.",
        },
      }),
    });
    const user = userEvent.setup();
    render(<AskBera projectId="p1" />);
    await user.type(screen.getByLabelText("Question"), "Who?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("used all its AI allowance");
  });

  it("shows a field error under the question", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({
        error: {
          code: "validation_error",
          message: "Check the form.",
          fields: { question: "Keep the question to 500 characters." },
        },
      }),
    });
    const user = userEvent.setup();
    render(<AskBera projectId="p1" />);
    await user.type(screen.getByLabelText("Question"), "Who?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("Keep the question to 500 characters.")).toBeTruthy();
  });

  it("keeps nothing: no storage is used and a new question replaces the answer", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    fetchMock
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => answer })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ answer: "Nobody yet.", refused: false, candidates: [] }),
      });
    const user = userEvent.setup();
    render(<AskBera projectId="p1" />);
    await user.type(screen.getByLabelText("Question"), "One");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByRole("link", { name: "Z. Q." });
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Z. Q." })).toBeNull());
    expect(await screen.findByText("Nobody yet.")).toBeTruthy();
    expect(setItem).not.toHaveBeenCalled();
  });
});
