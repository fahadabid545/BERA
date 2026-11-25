import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AiChatbotPage from "./page";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AI Chatbot page", () => {
  it("shows the chatbot settings and documents", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        settings: {
          enabled: false,
          model: "",
          prompt_version: 1,
          visitor_questions_per_hour: 20,
          max_question_length: 300,
          max_answer_length: 1500,
          daily_token_cap: 200000,
          models: [],
          prompt_versions: [1],
        },
        documents: [],
      }),
    });
    render(<AiChatbotPage />);
    expect(await screen.findByRole("region", { name: "Documents" })).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/admin/chatbot/");
  });
});
