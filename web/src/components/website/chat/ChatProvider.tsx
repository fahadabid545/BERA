"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { getJson, postJson } from "@/lib/api";
import {
  loadChats,
  newChatId,
  saveChats,
  type ChatMessage,
  type SavedChat,
  type WidgetSettings,
} from "@/lib/publicChat";

import { ChatWindow } from "./ChatWindow";

type ChatApi = {
  /** False until the server says the chat is on; nothing is shown while it is off. */
  available: boolean;
  maxQuestionLength: number;
  open: (question?: string) => void;
};

const NOT_AVAILABLE: ChatApi = { available: false, maxQuestionLength: 0, open: () => {} };
const ChatContext = createContext<ChatApi>(NOT_AVAILABLE);

export function useChat() {
  return useContext(ChatContext);
}

export type ChatSession = {
  chats: SavedChat[];
  activeId: string | null;
  asking: boolean;
  error: string;
  maxQuestionLength: number;
  select: (id: string) => void;
  startNew: () => void;
  send: (question: string, inNewChat?: boolean) => Promise<void>;
};

export type EnabledSettings = Extract<WidgetSettings, { enabled: true }>;

/** The chats of this browser and the one being written. The browser keeps the conversation and
 * sends the last few messages with each question; the server remembers nothing. */
function useChatSession(settings: EnabledSettings | null) {
  const [chats, setChats] = useState<SavedChat[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  const latest = useRef<SavedChat[]>([]);

  const commit = useCallback(
    (next: SavedChat[]) => {
      latest.current = next;
      setChats(next);
      if (settings) saveChats(next, settings.max_saved_chats);
    },
    [settings],
  );

  const reload = useCallback(() => {
    if (!settings) return;
    const kept = loadChats(Date.now(), settings.history_hours);
    latest.current = kept;
    setChats(kept);
    setActiveId((current) => (kept.some((chat) => chat.id === current) ? current : null));
  }, [settings]);

  const send = useCallback(
    async (text: string, inNewChat = false) => {
      const question = text.trim();
      if (!settings || !question || asking) return;
      setError("");
      const id = inNewChat ? newChatId() : (activeId ?? newChatId());
      const existing = latest.current.find((chat) => chat.id === id);
      const earlier: ChatMessage[] = existing?.messages ?? [];
      const asked: ChatMessage = { role: "user", text: question };
      const withQuestion: SavedChat = {
        id,
        updatedAt: Date.now(),
        messages: [...earlier, asked],
      };
      commit([withQuestion, ...latest.current.filter((chat) => chat.id !== id)]);
      setActiveId(id);
      setAsking(true);
      const most = settings.max_history_messages;
      const reply = await postJson<{ answer: string }>("/api/chatbot/ask/", {
        question,
        history: most > 0 ? earlier.slice(-most) : [],
      });
      setAsking(false);
      if (!reply.ok) {
        setError(reply.error.message);
        return;
      }
      const answered: SavedChat = {
        ...withQuestion,
        updatedAt: Date.now(),
        messages: [...withQuestion.messages, { role: "assistant", text: reply.data.answer }],
      };
      commit([answered, ...latest.current.filter((chat) => chat.id !== id)]);
    },
    [activeId, asking, commit, settings],
  );

  return {
    chats,
    activeId,
    asking,
    error,
    reload,
    maxQuestionLength: settings?.max_question_length ?? 0,
    select: (id: string) => {
      setActiveId(id);
      setError("");
    },
    startNew: () => {
      setActiveId(null);
      setError("");
    },
    send,
  };
}

/** Mounted once on the public pages: asks the server whether the chat is on, and holds the chat
 * window that the home page's search bar and the Chat button open. */
export function ChatProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<EnabledSettings | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const session = useChatSession(settings);
  const { reload, send } = session;

  useEffect(() => {
    let current = true;
    getJson<WidgetSettings>("/api/chatbot/status/").then((reply) => {
      if (current && reply.ok && reply.data.enabled) setSettings(reply.data);
    });
    return () => {
      current = false;
    };
  }, []);

  const open = useCallback(
    (question?: string) => {
      reload();
      setIsOpen(true);
      if (question) void send(question, true);
    },
    [reload, send],
  );

  const api = useMemo<ChatApi>(
    () =>
      settings
        ? { available: true, maxQuestionLength: settings.max_question_length, open }
        : NOT_AVAILABLE,
    [settings, open],
  );

  return (
    <ChatContext.Provider value={api}>
      {children}
      {settings && isOpen ? (
        <ChatWindow session={session} onClose={() => setIsOpen(false)} />
      ) : null}
    </ChatContext.Provider>
  );
}
