import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatbotAdmin } from "./ChatbotAdmin";

const fetchMock = vi.fn();
const BASE = "/api/admin/chatbot/";
const settings = {
  enabled: false,
  model: "",
  prompt_version: 1,
  visitor_questions_per_hour: 20,
  max_question_length: 300,
  max_answer_length: 1500,
  daily_token_cap: 200000,
  models: ["chat-model"],
  prompt_versions: [1, 2],
};
const document = (over: object = {}) => ({
  id: 7,
  name: "guide.pdf",
  file_type: "pdf",
  size_bytes: 20480,
  characters: 1200,
  enabled: true,
  updated_at: "2026-11-20T10:00:00Z",
  ...over,
});
const state = (documents: object[] = [document()], over: object = {}) => ({
  settings: { ...settings, ...over },
  documents,
});

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}
const call = (index: number) => ({
  url: fetchMock.mock.calls[index][0] as string,
  init: fetchMock.mock.calls[index][1] as RequestInit,
});
const jsonBody = (index: number) => JSON.parse(call(index).init.body as string);

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function shown(documents?: object[]) {
  reply(200, state(documents));
  render(<ChatbotAdmin />);
  await screen.findByRole("region", { name: "Documents" });
}

describe("chatbot admin page", () => {
  it("shows the settings and the documents with their status", async () => {
    await shown();
    expect(
      (screen.getByLabelText("Questions per visitor per hour") as HTMLInputElement).value,
    ).toBe("20");
    expect((screen.getByLabelText("Chatbot on") as HTMLInputElement).checked).toBe(false);
    const row = within(screen.getByRole("region", { name: "Documents" }))
      .getByText("guide.pdf")
      .closest("tr")!;
    expect(within(row).getByText("On")).toBeTruthy();
    expect(within(row).getByText("20 KB")).toBeTruthy();
  });

  it("saves the settings after a confirmation", async () => {
    const user = userEvent.setup();
    await shown();
    await user.click(screen.getByLabelText("Chatbot on"));
    await user.selectOptions(screen.getByLabelText("Model"), "chat-model");
    await user.selectOptions(screen.getByLabelText("Prompt version"), "2");
    const questions = screen.getByLabelText("Longest question (characters)");
    await user.clear(questions);
    await user.type(questions, "250");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    reply(200, state([], { enabled: true, model: "chat-model" }));
    const dialog = await screen.findByRole("dialog", { name: "Save chatbot settings" });
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(call(1).url).toBe(BASE);
    expect(call(1).init.method).toBe("PUT");
    expect(jsonBody(1)).toEqual({
      enabled: true,
      model: "chat-model",
      prompt_version: 2,
      visitor_questions_per_hour: 20,
      max_question_length: 250,
      max_answer_length: 1500,
      daily_token_cap: 200000,
    });
  });

  it("shows the server's reason when it cannot be switched on", async () => {
    const user = userEvent.setup();
    await shown();
    await user.click(screen.getByLabelText("Chatbot on"));
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    reply(400, {
      error: {
        code: "validation_error",
        message: "Check the form.",
        fields: { enabled: "Choose a model before switching the chatbot on." },
      },
    });
    const dialog = await screen.findByRole("dialog", { name: "Save chatbot settings" });
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Choose a model before switching the chatbot on.")).toBeTruthy();
  });

  it("switches a document off without a popup", async () => {
    const user = userEvent.setup();
    await shown();
    reply(200, state([document({ enabled: false })]));
    await user.click(screen.getByRole("button", { name: "Switch off guide.pdf" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(call(1).url).toBe(`${BASE}documents/7/`);
    expect(call(1).init.method).toBe("PATCH");
    expect(jsonBody(1)).toEqual({ enabled: false });
    expect(await screen.findByRole("button", { name: "Switch on guide.pdf" })).toBeTruthy();
  });

  it("adds a document by file", async () => {
    const user = userEvent.setup();
    await shown([]);
    await user.click(screen.getByRole("button", { name: "Add document" }));
    const dialog = await screen.findByRole("dialog", { name: "Add document" });
    reply(201, state());
    const file = new File(["The product ranks CVs."], "notes.txt", { type: "text/plain" });
    await user.upload(within(dialog).getByLabelText("File"), file);
    await user.click(within(dialog).getByRole("button", { name: "Add" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(call(1).url).toBe(`${BASE}documents/`);
    expect(call(1).init.method).toBe("POST");
    expect((call(1).init.body as FormData).get("file")).toBe(file);
    expect(await screen.findByText("guide.pdf")).toBeTruthy();
  });

  it("asks for a file before adding", async () => {
    const user = userEvent.setup();
    await shown([]);
    await user.click(screen.getByRole("button", { name: "Add document" }));
    const dialog = await screen.findByRole("dialog", { name: "Add document" });
    await user.click(within(dialog).getByRole("button", { name: "Add" }));
    expect(await screen.findByText("Choose a file.")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows why a file is refused", async () => {
    const user = userEvent.setup();
    await shown([]);
    await user.click(screen.getByRole("button", { name: "Add document" }));
    const dialog = await screen.findByRole("dialog", { name: "Add document" });
    reply(400, {
      error: {
        code: "scanned_image",
        message: "This looks like a scanned image.",
        fields: { file: "This looks like a scanned image." },
      },
    });
    await user.upload(within(dialog).getByLabelText("File"), new File(["x"], "scan.pdf"));
    await user.click(within(dialog).getByRole("button", { name: "Add" }));
    expect(await screen.findByText("This looks like a scanned image.")).toBeTruthy();
  });

  it("replaces a document with a new file", async () => {
    const user = userEvent.setup();
    await shown();
    await user.click(screen.getByRole("button", { name: "Replace guide.pdf" }));
    const dialog = await screen.findByRole("dialog", { name: "Replace document" });
    reply(200, state());
    await user.upload(within(dialog).getByLabelText("File"), new File(["New text."], "new.md"));
    await user.click(within(dialog).getByRole("button", { name: "Replace" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(call(1).url).toBe(`${BASE}documents/7/`);
    expect(call(1).init.method).toBe("PUT");
  });

  it("deletes a document only after a confirmation", async () => {
    const user = userEvent.setup();
    await shown();
    await user.click(screen.getByRole("button", { name: "Delete guide.pdf" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const dialog = await screen.findByRole("dialog", { name: "Delete document" });
    reply(200, state([]));
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(call(1).init.method).toBe("DELETE");
    await waitFor(() => expect(screen.queryByText("guide.pdf")).toBeNull());
  });
});
