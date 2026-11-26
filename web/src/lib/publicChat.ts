/** The public chat's history, kept only in this browser and only for a few hours. Nothing is sent
 * to the server except the messages of the chat being written (the server stores none of them). */

export type ChatMessage = { role: "user" | "assistant"; text: string };
export type SavedChat = { id: string; updatedAt: number; messages: ChatMessage[] };

export type WidgetSettings =
  | { enabled: false }
  | {
      enabled: true;
      max_question_length: number;
      max_history_messages: number;
      history_hours: number;
      max_saved_chats: number;
    };

const STORAGE_KEY = "public-chat-history";
const MILLISECONDS_PER_HOUR = 3_600_000;

function isChat(value: unknown): value is SavedChat {
  const chat = value as SavedChat;
  return (
    typeof chat?.id === "string" &&
    typeof chat.updatedAt === "number" &&
    Array.isArray(chat.messages) &&
    chat.messages.every(
      (message) =>
        (message?.role === "user" || message?.role === "assistant") &&
        typeof message.text === "string",
    )
  );
}

/** The chats still within their time, newest first. Anything unreadable is treated as empty:
 * storage can be blocked or cleared at any moment. */
export function loadChats(now: number, hours: number): SavedChat[] {
  try {
    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]");
    if (!Array.isArray(stored)) return [];
    return stored
      .filter(isChat)
      .filter((chat) => now - chat.updatedAt < hours * MILLISECONDS_PER_HOUR)
      .sort((first, second) => second.updatedAt - first.updatedAt);
  } catch {
    return [];
  }
}

export function saveChats(chats: SavedChat[], most: number) {
  try {
    const newest = [...chats].sort((first, second) => second.updatedAt - first.updatedAt);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(newest.slice(0, most)));
  } catch {
    // Storage is full or blocked: the chat still works, it is just not kept.
  }
}

export function clearChats() {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to clear when storage is blocked.
  }
}

export function newChatId(): string {
  return (
    globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`
  );
}

/** A chat is named by what was asked first. */
export function chatTitle(chat: SavedChat): string {
  return chat.messages.find((message) => message.role === "user")?.text ?? "";
}
