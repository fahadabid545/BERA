import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { chatTitle, clearChats, loadChats, saveChats, type SavedChat } from "./publicChat";

const HOUR = 3_600_000;
const NOW = 1_000_000_000_000;

function chat(id: string, updatedAt: number, text = "question"): SavedChat {
  return { id, updatedAt, messages: [{ role: "user", text }] };
}

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("kept chats", () => {
  it("keeps chats for the given hours and drops older ones", () => {
    saveChats([chat("new", NOW - HOUR), chat("old", NOW - 3 * HOUR)], 10);
    expect(loadChats(NOW, 2).map((item) => item.id)).toEqual(["new"]);
  });

  it("lists the newest first and keeps only the most allowed", () => {
    saveChats([chat("a", NOW - 3000), chat("b", NOW - 1000), chat("c", NOW - 2000)], 2);
    expect(loadChats(NOW, 2).map((item) => item.id)).toEqual(["b", "c"]);
  });

  it("treats damaged or foreign storage as empty", () => {
    window.localStorage.setItem("public-chat-history", "{not json");
    expect(loadChats(NOW, 2)).toEqual([]);
    window.localStorage.setItem("public-chat-history", JSON.stringify({ a: 1 }));
    expect(loadChats(NOW, 2)).toEqual([]);
    window.localStorage.setItem(
      "public-chat-history",
      JSON.stringify([{ id: "x", updatedAt: NOW, messages: [{ role: "system", text: "hi" }] }]),
    );
    expect(loadChats(NOW, 2)).toEqual([]);
  });

  it("does not fail when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(loadChats(NOW, 2)).toEqual([]);
    expect(() => saveChats([chat("a", NOW)], 5)).not.toThrow();
    expect(() => clearChats()).not.toThrow();
  });

  it("names a chat by the first question", () => {
    const named: SavedChat = {
      id: "a",
      updatedAt: NOW,
      messages: [
        { role: "user", text: "First?" },
        { role: "assistant", text: "Answer" },
        { role: "user", text: "Second?" },
      ],
    };
    expect(chatTitle(named)).toBe("First?");
    expect(chatTitle({ ...named, messages: [] })).toBe("");
  });

  it("can be cleared", () => {
    saveChats([chat("a", NOW)], 5);
    clearChats();
    expect(loadChats(NOW, 2)).toEqual([]);
  });
});
