"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  askAgent,
  deleteChat,
  listChats,
  openChat,
  type AgentMessage,
  type ChatSummary,
} from "@/lib/agentChat";

import { AgentWindow } from "./AgentWindow";

/** The most earlier messages and shown candidates an incognito question may bring along. */
const MOST_BROUGHT_ALONG = 100;

export type AgentSession = {
  chats: ChatSummary[];
  activeId: string | null;
  messages: AgentMessage[];
  incognito: boolean;
  asking: boolean;
  error: string;
  send: (question: string, fresh?: boolean) => Promise<void>;
  select: (id: string) => Promise<void>;
  startNew: (incognito?: boolean) => void;
  remove: (id: string) => Promise<void>;
};

type AgentApi = { open: (question?: string) => void };
const AgentContext = createContext<AgentApi>({ open: () => {} });

export function useAgent() {
  return useContext(AgentContext);
}

function useAgentSession(): AgentSession & { refresh: () => Promise<void> } {
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [incognito, setIncognito] = useState(false);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  // The answer for a chat that was switched away from while waiting must not land in another chat.
  const generation = useRef(0);

  const refresh = useCallback(async () => {
    const reply = await listChats();
    if (reply.ok) setChats(reply.data.chats);
  }, []);

  const send = useCallback(
    async (text: string, fresh = false) => {
      const question = text.trim();
      if (!question || asking) return;
      setError("");
      // A question that starts a chat of its own ignores the chat that is open.
      const chatId = fresh ? null : activeId;
      const isIncognito = fresh ? false : incognito;
      const earlier = (fresh ? [] : messages).filter((message) => !message.problem);
      const asked: AgentMessage = { role: "user", text: question, suggestions: [], candidates: [] };
      setMessages([
        ...(fresh ? [] : messages).map((message) => ({ ...message, suggestions: [] })),
        asked,
      ]);
      setAsking(true);
      const mine = ++generation.current;
      const reply = await askAgent({
        question,
        incognito: isIncognito,
        chat_id: isIncognito ? undefined : (chatId ?? undefined),
        history: isIncognito
          ? earlier.slice(-MOST_BROUGHT_ALONG).map(({ role, text: said }) => ({ role, text: said }))
          : undefined,
        shown: isIncognito
          ? [
              ...new Set(
                earlier.flatMap((message) => message.candidates.map((card) => card.candidate_id)),
              ),
            ].slice(-MOST_BROUGHT_ALONG)
          : undefined,
      });
      if (mine !== generation.current) return;
      setAsking(false);
      if (!reply.ok) {
        setMessages((current) => [
          ...current,
          {
            role: "assistant",
            text: reply.error.message,
            suggestions: [],
            candidates: [],
            problem: true,
          },
        ]);
        return;
      }
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: reply.data.answer,
          suggestions: reply.data.suggestions,
          candidates: reply.data.candidates,
        },
      ]);
      if (!isIncognito) {
        setActiveId(reply.data.chat_id);
        await refresh();
      }
    },
    [activeId, asking, incognito, messages, refresh],
  );

  const select = useCallback(async (id: string) => {
    generation.current += 1;
    setAsking(false);
    setError("");
    setIncognito(false);
    const reply = await openChat(id);
    if (!reply.ok) {
      setError(reply.error.message);
      return;
    }
    const opened = reply.data.messages.map((message, index, all) => ({
      ...message,
      // Only the last answer still offers its follow-up suggestions.
      suggestions: index === all.length - 1 ? message.suggestions : [],
    }));
    setActiveId(id);
    setMessages(opened);
  }, []);

  const startNew = useCallback((incognitoChat = false) => {
    generation.current += 1;
    setAsking(false);
    setError("");
    setActiveId(null);
    setMessages([]);
    setIncognito(incognitoChat);
  }, []);

  const remove = useCallback(
    async (id: string) => {
      const reply = await deleteChat(id);
      if (!reply.ok) {
        setError(reply.error.message);
        return;
      }
      if (id === activeId) startNew();
      await refresh();
    },
    [activeId, refresh, startNew],
  );

  return {
    chats,
    activeId,
    messages,
    incognito,
    asking,
    error,
    send,
    select,
    startNew,
    remove,
    refresh,
  };
}

/** Mounted once in the company panel: holds the agent's window, which the search bar opens. */
export function AgentProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const session = useAgentSession();
  const { refresh, send, startNew } = session;

  const open = useCallback(
    (question?: string) => {
      setIsOpen(true);
      void refresh();
      if (question) {
        startNew();
        void send(question, true);
      }
    },
    [refresh, send, startNew],
  );

  const api = useMemo(() => ({ open }), [open]);
  return (
    <AgentContext.Provider value={api}>
      {children}
      {isOpen ? <AgentWindow session={session} onClose={() => setIsOpen(false)} /> : null}
    </AgentContext.Provider>
  );
}
